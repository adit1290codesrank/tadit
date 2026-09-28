"""Training entry point.

  single GPU:  python -m nowcast.train --config configs/dev.yaml
  DDP:         torchrun --standalone --nproc_per_node=2 -m nowcast.train --config configs/burst.yaml
  continue:    ... --resume runs/overnight/latest.pt          (weights + optimizer + step; LR re-warms)
  warm start:  ... --init-from runs/overnight/latest.pt       (weights only, shape-matched)

With `train.deadline_minutes` set, throughput is measured after warm-up and the cosine schedule
is fitted so the LR reaches its floor exactly when time runs out. Checkpoints are atomic
(tmp + os.replace) and written every `ckpt_every_min`. SIGTERM/SIGINT trigger a final save.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import os
import shutil
import signal
import time
from dataclasses import asdict

import numpy as np
import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.data import DataLoader, DistributedSampler, RandomSampler, Subset

from .config import load_config
from .data.dataset import NowcastDataset, prepare_batch
from .evaluation import model_predictor, run_eval, summary
from .losses import total_loss
from .model.fusion import FusionNowcaster, ModelConfig, count_params

MEASURE_AFTER = 20  # steps after (re)start excluded from throughput (compile, cudnn autotune)


class EMA:
    def __init__(self, model: torch.nn.Module, decay: float):
        self.decay = decay
        self.shadow = copy.deepcopy(model).eval().requires_grad_(False)

    @torch.no_grad()
    def update(self, model: torch.nn.Module, step: int) -> None:
        d = min(self.decay, (1 + step) / (10 + step))  # fast tracking early in short runs
        torch._foreach_lerp_(list(self.shadow.parameters()), [p.detach() for p in model.parameters()], 1 - d)


class Schedule:
    """Linear warm-up from `start`, then cosine to min_ratio * lr at `total`."""

    def __init__(self, lr: float, warmup: int, min_ratio: float, start: int, total: int):
        self.lr, self.warmup, self.min_ratio, self.start, self.total = lr, warmup, min_ratio, start, total

    def __call__(self, step: int) -> float:
        s = step - self.start
        if s < self.warmup:
            return self.lr * (s + 1) / self.warmup
        span = max(1, self.total - self.start - self.warmup)
        p = min(1.0, (s - self.warmup) / span)
        return self.lr * (self.min_ratio + (1 - self.min_ratio) * 0.5 * (1 + math.cos(math.pi * p)))


class Logger:
    def __init__(self, path: str, enabled: bool):
        self.path, self.enabled = path, enabled

    def __call__(self, **kw) -> None:
        if not self.enabled:
            return
        kw = {"time": round(time.time(), 1), **kw}
        line = json.dumps(kw, default=lambda o: float(o) if hasattr(o, "__float__") else str(o))
        print(line, flush=True)
        with open(self.path, "a") as f:
            f.write(line + "\n")


def setup_dist():
    if int(os.environ.get("WORLD_SIZE", "1")) > 1:
        dist.init_process_group("nccl")
        local = int(os.environ["LOCAL_RANK"])
        torch.cuda.set_device(local)
        return True, dist.get_rank(), dist.get_world_size(), torch.device("cuda", local)
    return False, 0, 1, torch.device("cuda" if torch.cuda.is_available() else "cpu")


def infinite(loader, sampler):
    epoch = 0
    while True:
        if hasattr(sampler, "set_epoch"):
            sampler.set_epoch(epoch)
        for b in loader:
            yield b
        epoch += 1


def free_gb(path: str) -> float:
    return shutil.disk_usage(path).free / 1e9


def atomic_save(obj, path: str, min_free_gb: float, log: Logger) -> bool:
    d = os.path.dirname(path) or "."
    for f in os.listdir(d):  # leftovers of an interrupted save
        if f.endswith(".tmp"):
            os.remove(os.path.join(d, f))
    need = min_free_gb + (os.path.getsize(path) / 1e9 if os.path.exists(path) else 1.0)
    if free_gb(d) < need:
        log(event="ckpt_skipped_disk_low", path=path, free_gb=free_gb(d), need_gb=need)
        return False
    tmp = path + ".tmp"
    torch.save(obj, tmp)
    os.replace(tmp, path)
    return True


def load_weights_matching(model: torch.nn.Module, weights: dict) -> tuple[list, list]:
    own = model.state_dict()
    ok = {k: v for k, v in weights.items() if k in own and own[k].shape == v.shape}
    model.load_state_dict(ok, strict=False)
    return sorted(set(own) - set(ok)), sorted(set(weights) - set(ok))


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--set", action="append", default=[], help="override, e.g. train.batch_size=16")
    ap.add_argument("--resume")
    ap.add_argument("--init-from")
    args = ap.parse_args(argv)

    cfg = load_config(args.config, args.set)
    tc = cfg.train
    if not tc.max_steps and not tc.deadline_minutes:
        raise SystemExit("set train.max_steps or train.deadline_minutes")
    is_dist, rank, world, device = setup_dist()
    main_proc = rank == 0
    torch.manual_seed(tc.seed + rank)
    np.random.seed(tc.seed + rank)
    if device.type == "cuda":
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        torch.backends.cudnn.benchmark = True
    os.makedirs(tc.out_dir, exist_ok=True)
    log = Logger(os.path.join(tc.out_dir, "log.jsonl"), main_proc)

    stop_requested = {"flag": False}

    def _on_signal(signum, _frame):
        stop_requested["flag"] = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    # ------------------------------------------------------------------ data
    resume = torch.load(args.resume, map_location="cpu", weights_only=False) if args.resume else None
    dc = cfg.data
    if resume:  # a resumed run keeps the horizon it was trained with
        rd = resume.get("config", {}).get("data", {})
        for k in ("t_in", "t_out", "out_step"):
            if k in rd and rd[k] != getattr(dc, k):
                log(event="warning", msg=f"--resume: using checkpoint {k}={rd[k]} (config had {getattr(dc, k)})")
                setattr(dc, k, rd[k])
    horizon = dict(t_in=dc.t_in, t_out=dc.t_out, out_step=dc.out_step)
    train_ds = NowcastDataset(dc.train_dir, train=True, windows_per_event=dc.windows_per_event,
                              rotate=dc.rotate, **horizon)
    nwp_stats = train_ds.store.stats()
    nw = cfg.data.num_workers
    sampler = (DistributedSampler(train_ds, shuffle=True, seed=tc.seed, drop_last=True) if is_dist
               else RandomSampler(train_ds))
    loader = DataLoader(train_ds, batch_size=tc.batch_size, sampler=sampler, num_workers=nw,
                        pin_memory=device.type == "cuda", drop_last=True, persistent_workers=nw > 0,
                        prefetch_factor=cfg.data.prefetch_factor if nw > 0 else None)
    val_loader = None
    if main_proc and cfg.data.val_dir and os.path.isdir(cfg.data.val_dir):
        val_ds = NowcastDataset(cfg.data.val_dir, train=False, windows_per_event=cfg.data.windows_per_event,
                                stats=nwp_stats, **horizon)
        n = min(len(val_ds), tc.val_batches * tc.batch_size)
        pick = np.random.default_rng(0).permutation(len(val_ds))[:n].tolist()
        val_loader = DataLoader(Subset(val_ds, pick), batch_size=tc.batch_size, num_workers=min(nw, 4),
                                pin_memory=device.type == "cuda")

    # ------------------------------------------------------------------ model
    if resume:
        mkw = dict(resume["model_cfg"])
    else:
        mkw = dict(t_in=dc.t_in, t_out=dc.t_out, nwp_hours=train_ds.nwp_hours,
                   ir_channels=train_ds.ir_channels, nwp_vars=len(train_ds.nwp_vars))
        mkw.update(cfg.model)
    mcfg = ModelConfig(**mkw)
    if "nwp" in mcfg.modalities and mcfg.nwp_vars == 0:
        log(event="warning", msg="nwp requested but shards have no NWP stats; NWP branch disabled")
    model = FusionNowcaster(mcfg).to(device)
    if tc.channels_last:
        model = model.to(memory_format=torch.channels_last)

    step = samples = 0
    if resume:
        model.load_state_dict(resume["model"])
        step, samples = int(resume["step"]), int(resume["samples"])
    elif args.init_from:
        src = torch.load(args.init_from, map_location="cpu", weights_only=False)
        missing, unexpected = load_weights_matching(model, src.get("ema") or src["model"])
        log(event="init_from", path=args.init_from, missing=len(missing), unexpected=len(unexpected))

    ema = EMA(model, tc.ema_decay)
    if resume and "ema" in resume:
        ema.shadow.load_state_dict(resume["ema"])

    decay, no_decay = [], []
    for n_, p in model.named_parameters():
        (no_decay if p.ndim < 2 or "missing" in n_ or "null" in n_ else decay).append(p)
    opt = torch.optim.AdamW([{"params": decay, "weight_decay": tc.weight_decay},
                             {"params": no_decay, "weight_decay": 0.0}],
                            lr=tc.lr, betas=tuple(tc.betas), fused=device.type == "cuda")
    if resume and "opt" in resume:
        opt.load_state_dict(resume["opt"])
    del resume

    net = DDP(model, device_ids=[device.index]) if is_dist else model
    if tc.compile:
        net = torch.compile(net)

    amp_dtype = torch.bfloat16 if tc.amp == "bf16" and device.type == "cuda" else None
    log(event="start", params=count_params(model), step=step, samples=samples, world=world,
        device=str(device), gpu=torch.cuda.get_device_name(device) if device.type == "cuda" else "cpu",
        train_events=len(train_ds.store), model_cfg=asdict(mcfg))

    def state(full: bool = True) -> dict:
        s = {"ema": ema.shadow.state_dict(), "model_cfg": asdict(mcfg), "step": step, "samples": samples,
             "nwp_stats": nwp_stats, "config": cfg.to_dict()}
        if full:
            s.update(model=model.state_dict(), opt=opt.state_dict())
        return s

    # ------------------------------------------------------------------ budget
    start_step = step
    t_start = time.time()
    stop_at = t_start + (tc.deadline_minutes - tc.reserve_minutes) * 60 if tc.deadline_minutes else None
    cap = start_step + tc.max_steps if tc.max_steps else 10**12
    sched = Schedule(tc.lr, tc.warmup_steps, tc.min_lr_ratio, start_step, cap)
    meas_step, meas_t = None, None
    last_ckpt = last_val = time.time()

    # ------------------------------------------------------------------ loop
    model.train()
    it = infinite(loader, sampler)
    acc = {"loss": 0.0, "loss_vil": 0.0, "loss_lght": 0.0, "n": 0}
    t_log, s_log = time.time(), samples
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    while True:
        batch = next(it)
        lr = sched(step)
        for g in opt.param_groups:
            g["lr"] = lr
        x, y = prepare_batch(batch, device)
        with torch.autocast(device_type=device.type, dtype=amp_dtype or torch.float32, enabled=amp_dtype is not None):
            out = net(x, drop_p=tc.drop_p)
        loss, parts = total_loss(out, y, tc.lght_weight, tc.vil_band_weights, tc.focal_gamma,
                                 tc.lght_dilate, tc.lght_pos_weight)
        opt.zero_grad(set_to_none=True)
        loss.backward()
        gnorm = torch.nn.utils.clip_grad_norm_(model.parameters(), tc.grad_clip)
        opt.step()
        ema.update(model, step)
        step += 1
        samples += tc.batch_size * world
        acc["loss"] += loss.detach()
        acc["loss_vil"] += parts["loss_vil"]
        acc["loss_lght"] += parts["loss_lght"]
        acc["n"] += 1

        if step - start_step == MEASURE_AFTER:
            meas_step, meas_t = step, time.time()

        if step % tc.log_every == 0 or step >= sched.total:
            now = time.time()
            stop = step >= sched.total or stop_requested["flag"]
            if stop_at is not None:
                stop |= now >= stop_at
                if meas_step is not None and step > meas_step:
                    sps = (step - meas_step) / (now - meas_t)
                    sched.total = min(cap, step + max(1, int(sps * max(0.0, stop_at - now))))
            ctrl = torch.tensor([int(stop), int(now - last_ckpt >= tc.ckpt_every_min * 60),
                                 int(now - last_val >= tc.val_every_min * 60), sched.total],
                                dtype=torch.int64, device=device)
            if is_dist:
                dist.broadcast(ctrl, 0)
            stop, do_ckpt, do_val, sched.total = bool(ctrl[0]), bool(ctrl[1]), bool(ctrl[2]), int(ctrl[3])

            n = max(acc["n"], 1)
            log(step=step, samples=samples, lr=lr, loss=float(acc["loss"]) / n,
                loss_vil=float(acc["loss_vil"]) / n, loss_lght=float(acc["loss_lght"]) / n,
                grad_norm=float(gnorm), samples_per_s=(samples - s_log) / max(now - t_log, 1e-6),
                total_steps_planned=sched.total, elapsed_min=(now - t_start) / 60,
                peak_mem_gb=torch.cuda.max_memory_allocated(device) / 1e9 if device.type == "cuda" else 0.0,
                free_disk_gb=free_gb(tc.out_dir))
            acc = {"loss": 0.0, "loss_vil": 0.0, "loss_lght": 0.0, "n": 0}
            t_log, s_log = time.time(), samples

            if do_val and val_loader is not None and main_proc and not stop:
                res, _ = run_eval(model_predictor(ema.shadow, amp_dtype), val_loader, device, train_ds.lead_minutes)
                log(event="val", step=step, samples=samples, **summary(res))
                last_val = time.time()
            elif do_val:
                last_val = time.time()
            if do_ckpt and not stop:
                if main_proc:
                    atomic_save(state(), os.path.join(tc.out_dir, "latest.pt"), tc.min_free_gb, log)
                last_ckpt = time.time()
            if stop:
                break

    # ------------------------------------------------------------------ final
    final = {}
    if main_proc:
        atomic_save(state(), os.path.join(tc.out_dir, "latest.pt"), tc.min_free_gb, log)
        light = state(full=False)
        light["ema"] = {k: (v.to(torch.bfloat16) if v.is_floating_point() else v) for k, v in light["ema"].items()}
        atomic_save(light, os.path.join(tc.out_dir, "final_ema_bf16.pt"), 0.2, log)
        if val_loader is not None:
            res, _ = run_eval(model_predictor(ema.shadow, amp_dtype), val_loader, device, train_ds.lead_minutes)
            final = summary(res)
            log(event="final_val", step=step, samples=samples, **final)
        log(event="done", step=step, samples=samples, minutes=(time.time() - t_start) / 60)
    if is_dist:
        dist.barrier()
        dist.destroy_process_group()
    return {"step": step, "samples": samples, **final}


if __name__ == "__main__":
    main()
