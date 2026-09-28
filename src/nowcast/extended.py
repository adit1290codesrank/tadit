"""Tier 2: lead hours 1-6 by ML post-processing of HRRR forecasts (cf. MetNet-2 "Postprocess").

Why: beyond ~2 h, radar/satellite extrapolation loses to NWP, and a 384 km SEVIR patch cannot see
storms that will form or enter later. So for longer leads we learn a calibrated map from the HRRR
forecast to *observed* lightning (GLM) and radar (VIL), trained on the SEVIR events.

Sample = (event, target hour window (V-1h, V], lead hour k):
  input  HRRR fields valid at V-1h (fxx=k) and V (fxx=k+1), both from the run initialised at
         V-(k+1)h, i.e. the newest run available 1 h after issue time V-k h. No observations.
  target any GLM flash in each 16 km cell during (V-1h, V]; max VIL in the cell during the hour.
Grid 24 x 24 (16 km over the 384 km patch). Tier 1 is scored on the same question at the same grid
(evaluation.LeadHourLightning), so the two tiers can be compared hour by hour (scripts/crossover.py).

  python -m nowcast.extended build --shards shards --nwp work/nwp --out ext
  python -m nowcast.extended train --data ext --out runs/ext --epochs 20
  python -m nowcast.extended eval  --ckpt runs/ext/best.pt --data ext/test --out results/ext.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import time
from collections import OrderedDict
from dataclasses import asdict, dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader, Dataset

from .data.dataset import GFS_MISSING_VARS
from .data.hrrr import NWP_VARS, nwp_path, window_end_hours
from .data.shards import STATS_FILE, ShardStore
from .losses import lightning_loss, vil_loss
from .metrics import LightningMetrics, VILMetrics
from .model.fusion import ResBlock, _groups

GRID = 24
LEADS = (1, 2, 3, 4, 5, 6)


# =============================================================================== build

class _NWPCache:
    def __init__(self, root: str, grid: int, max_open: int = 256):
        self.root, self.grid, self.max_open = root, grid, max_open
        self.files: OrderedDict = OrderedDict()

    def _load(self, path):
        f = self.files.get(path)
        if f is None:
            f = np.load(path) if os.path.exists(path) else None
            self.files[path] = f
            if len(self.files) > self.max_open:
                self.files.popitem(last=False)
        return f

    def get(self, hour: int, fxx: int, eid: str) -> np.ndarray | None:
        f = self._load(nwp_path(self.root, hour, fxx, self.grid))
        if f is not None and eid in f.files:
            return f[eid].astype(np.float32)
        if fxx == 1:  # tier-1 cache holds f01 on the 48 grid: mean-pool it down
            f = self._load(nwp_path(self.root, hour, 1, 48))
            if f is not None and eid in f.files:
                x = f[eid].astype(np.float32)
                r = x.shape[-1] // self.grid
                return x.reshape(x.shape[0], self.grid, r, self.grid, r).mean(axis=(2, 4))
        return None


def _pool(x: np.ndarray, r: int, op: str) -> np.ndarray:
    h = x.shape[-1] // r
    y = x.reshape(*x.shape[:-2], h, r, h, r)
    return y.sum(axis=(-3, -1)) if op == "sum" else y.max(axis=(-3, -1))


def build_split(shard_dir: str, nwp_root: str, out_dir: str, leads=LEADS, grid: int = GRID) -> int:
    store = ShardStore(shard_dir)
    cache = _NWPCache(nwp_root, grid)
    X, YL, YV, LEAD, TOD, EID, VEND = [], [], [], [], [], [], []
    missing = 0
    for i in range(len(store)):
        a = store.get(i)
        eid = str(store.index[i]["event_id"])
        times = a["times"]
        lon = float(a.get("center_lon", 0.0))
        for V in window_end_hours(times):
            m = (times > V - 3600) & (times <= V)
            yl = _pool(a["lght"][m].sum(0, dtype=np.int64), a["lght"].shape[-1] // grid, "sum")
            yv = _pool(a["vil"][m].max(0), a["vil"].shape[-1] // grid, "max")
            hour = ((V % 86400) / 3600.0 + lon / 15.0) % 24.0
            tod = [math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24)]
            for k in leads:
                f1 = cache.get(int(V), k + 1, eid)          # valid at V
                f0 = cache.get(int(V) - 3600, k, eid)       # valid at V-1h, same run
                if f1 is None and f0 is None:
                    missing += 1
                    continue
                f1 = f0 if f1 is None else f1
                f0 = f1 if f0 is None else f0
                X.append(np.stack([f0, f1]).astype(np.float16))
                YL.append(np.minimum(yl, 255).astype(np.uint8))
                YV.append(yv.astype(np.uint8))
                LEAD.append(k)
                TOD.append(tod)
                EID.append(eid)
                VEND.append(int(V))
    os.makedirs(out_dir, exist_ok=True)
    if not X:
        raise SystemExit(f"{shard_dir}: no samples (is the NWP cache for fxx {min(leads)}..{max(leads) + 1} there?)")
    np.save(os.path.join(out_dir, "x.npy"), np.stack(X))
    np.save(os.path.join(out_dir, "y_lght.npy"), np.stack(YL))
    np.save(os.path.join(out_dir, "y_vil.npy"), np.stack(YV))
    np.save(os.path.join(out_dir, "lead.npy"), np.asarray(LEAD, np.int8))
    np.save(os.path.join(out_dir, "tod.npy"), np.asarray(TOD, np.float32))
    np.savez(os.path.join(out_dir, "meta.npz"), event_id=np.asarray(EID), valid_end=np.asarray(VEND))
    print(f"{out_dir}: {len(X)} samples from {len(store)} events "
          f"({missing} (event, hour, lead) skipped for missing NWP)")
    return len(X)


# =============================================================================== data

class ExtDataset(Dataset):
    def __init__(self, root: str, stats: dict, train: bool = False, rotate: bool = True, gfs_p: float = 0.0):
        self.x = np.load(os.path.join(root, "x.npy"), mmap_mode="r")      # [N, 2, V, g, g] fp16
        self.yl = np.load(os.path.join(root, "y_lght.npy"), mmap_mode="r")
        self.yv = np.load(os.path.join(root, "y_vil.npy"), mmap_mode="r")
        self.lead = np.load(os.path.join(root, "lead.npy"))
        self.tod = np.load(os.path.join(root, "tod.npy"))
        self.mean = np.asarray(stats["mean"], np.float32)[None, :, None, None]
        self.std = np.asarray(stats["std"], np.float32)[None, :, None, None]
        self.vars = list(stats["vars"])
        self.train = train
        self.rotate = rotate and train
        self.i_ltng, self.i_refc = self.vars.index("ltng"), self.vars.index("refc")
        # GFS (India) has no LTNG / updraft helicity: hide them in a fraction of samples (and always
        # in --india-mode) so the model is trained for the fields it will actually get there
        self.gfs_p = gfs_p
        self.gfs_missing = [self.vars.index(v) for v in GFS_MISSING_VARS if v in self.vars]

    def __len__(self):
        return len(self.lead)

    def __getitem__(self, i):
        raw = np.asarray(self.x[i], np.float32)
        x = np.clip(np.nan_to_num((raw - self.mean) / self.std, nan=0.0, posinf=0.0, neginf=0.0), -10, 10)
        if self.gfs_p and (torch.rand(1).item() if self.train else ((i * 2654435761) % 1000) / 1000) < self.gfs_p:
            x[:, self.gfs_missing] = 0.0
        x = x.reshape(-1, *x.shape[-2:])
        yl = (np.asarray(self.yl[i]) > 0).astype(np.float32)
        yv = np.asarray(self.yv[i], np.float32) / 255.0
        # raw HRRR at V for the baselines (LTNG stored as log1p(rate); REFC in dBZ)
        base = np.stack([np.expm1(np.nan_to_num(raw[1, self.i_ltng])), np.nan_to_num(raw[1, self.i_refc], nan=-10)])
        if self.rotate:
            r = int(torch.randint(0, 4, (1,)))
            if r:
                x, yl, yv, base = (np.rot90(a, r, axes=(-2, -1)) for a in (x, yl, yv, base))
        c = np.ascontiguousarray
        return {"x": c(x), "y_lght": c(yl), "y_vil": c(yv), "lead": int(self.lead[i]),
                "tod": self.tod[i], "base": c(base.astype(np.float32))}


# =============================================================================== model

@dataclass
class ExtConfig:
    in_ch: int = 2 * len(NWP_VARS)
    max_lead: int = max(LEADS)
    chs: tuple = (64, 128, 256)
    blocks: int = 2
    cond_dim: int = 64


class ExtNet(nn.Module):
    """Small U-Net on the 24 x 24 grid, FiLM-conditioned on lead hour and time of day."""

    def __init__(self, cfg: ExtConfig):
        super().__init__()
        self.cfg = cfg
        chs, cd = tuple(cfg.chs), cfg.cond_dim
        self.cond = nn.Sequential(nn.Linear(cfg.max_lead + 2, cd), nn.SiLU(), nn.Linear(cd, cd))
        self.stem = nn.Conv2d(cfg.in_ch, chs[0], 3, padding=1)
        self.enc = nn.ModuleList([nn.ModuleList([ResBlock(c, c, cd) for _ in range(cfg.blocks)]) for c in chs])
        self.down = nn.ModuleList([nn.Conv2d(chs[i], chs[i + 1], 3, stride=2, padding=1) for i in range(len(chs) - 1)])
        self.up = nn.ModuleList([nn.Sequential(nn.Upsample(scale_factor=2, mode="nearest"),
                                               nn.Conv2d(chs[i + 1], chs[i], 3, padding=1)) for i in range(len(chs) - 1)])
        self.dec = nn.ModuleList([nn.ModuleList([ResBlock(2 * c, c, cd)] + [ResBlock(c, c, cd) for _ in range(cfg.blocks - 1)])
                                  for c in chs[:-1]])
        self.head = nn.Sequential(nn.GroupNorm(_groups(chs[0]), chs[0]), nn.SiLU(), nn.Conv2d(chs[0], 2, 3, padding=1))
        nn.init.constant_(self.head[-1].bias, 0.0)
        with torch.no_grad():
            self.head[-1].bias[0] = -3.0  # lightning logit starts near the base rate

    def forward(self, x, lead, tod):
        onehot = F.one_hot((lead - 1).clamp(0, self.cfg.max_lead - 1), self.cfg.max_lead).to(x.dtype)
        cond = self.cond(torch.cat([onehot, tod.to(x.dtype)], 1))
        h = self.stem(x)
        skips = []
        for i, blocks in enumerate(self.enc):
            if i > 0:
                h = self.down[i - 1](h)
            for b in blocks:
                h = b(h, cond)
            skips.append(h)
        for i in reversed(range(len(self.dec))):
            h = torch.cat([self.up[i](h), skips[i]], 1)
            for b in self.dec[i]:
                h = b(h, cond)
        out = self.head(h)
        return {"lght": out[:, 0], "vil": out[:, 1]}


# =============================================================================== eval

class _ThresholdCSI:
    """CSI/POD/FAR of a raw score against a binary target over a list of thresholds."""

    def __init__(self, thresholds):
        self.thr = list(thresholds)
        self.h = np.zeros(len(self.thr))
        self.m = np.zeros(len(self.thr))
        self.f = np.zeros(len(self.thr))

    def update(self, score: torch.Tensor, target: torch.Tensor):
        obs = target > 0.5
        for j, t in enumerate(self.thr):
            fc = score >= t
            self.h[j] += float((fc & obs).sum())
            self.m[j] += float((~fc & obs).sum())
            self.f[j] += float((fc & ~obs).sum())

    def compute(self):
        csi = self.h / np.maximum(self.h + self.m + self.f, 1)
        j = int(csi.argmax())
        return {"best_threshold": self.thr[j], "csi": float(csi[j]),
                "pod": float(self.h[j] / max(self.h[j] + self.m[j], 1)),
                "far": float(self.f[j] / max(self.h[j] + self.f[j], 1))}


@torch.no_grad()
def evaluate(model, loader, device, amp=True, max_batches=None) -> dict:
    per = {}
    for bi, b in enumerate(loader):
        if max_batches is not None and bi >= max_batches:
            break
        x = b["x"].to(device, non_blocking=True)
        lead = b["lead"].to(device)
        yl, yv = b["y_lght"].to(device), b["y_vil"].to(device)
        with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=amp and device.type == "cuda"):
            out = model(x, lead, b["tod"].to(device))
        p = torch.sigmoid(out["lght"].float())
        v = out["vil"].float().clamp(0, 1)
        base = b["base"].to(device)
        for k in lead.unique().tolist():
            s = lead == k
            d = per.setdefault(k, {"model": LightningMetrics(1, tolerances=(0,)),
                                   "vil": VILMetrics(1, thresholds=(74, 133), pools=(1,)),
                                   "hrrr_ltng": _ThresholdCSI([1e-3, 3e-3, 0.01, 0.03, 0.1, 0.3, 1.0]),
                                   "hrrr_refc": _ThresholdCSI([20, 25, 30, 35, 40, 45, 50])})
            d["model"].update(p[s][:, None], yl[s][:, None])
            d["vil"].update(v[s][:, None], yv[s][:, None])
            d["hrrr_ltng"].update(base[s][:, 0], yl[s])
            d["hrrr_refc"].update(base[s][:, 1], yl[s])
    res = {}
    for k in sorted(per):
        d = per[k]
        lm = d["model"].compute()
        res[str(k)] = {
            "model": {**lm["tol0"], "brier": lm["brier"]},
            "base_rate": lm["base_rate"],
            "vil_csi": d["vil"].compute()["pool1"]["csi_per_threshold"],
            "hrrr_ltng": d["hrrr_ltng"].compute(),
            "hrrr_refc": d["hrrr_refc"].compute(),
        }
    return {"lead_hour": res}


def _mean_csi(res: dict) -> float:
    v = [r["model"]["csi"] for r in res["lead_hour"].values() if not math.isnan(r["model"]["csi"])]
    return float(np.mean(v)) if v else 0.0


# =============================================================================== train

def train(args) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(args.seed)
    with open(os.path.join(args.data, STATS_FILE)) as f:
        stats = json.load(f)
    tr = ExtDataset(os.path.join(args.data, "train"), stats, train=True, gfs_p=args.gfs_p)
    va = ExtDataset(os.path.join(args.data, "val"), stats) if os.path.isdir(os.path.join(args.data, "val")) else None
    dl = DataLoader(tr, batch_size=args.batch_size, shuffle=True, num_workers=args.workers, drop_last=True,
                    pin_memory=device.type == "cuda", persistent_workers=args.workers > 0)
    vl = DataLoader(va, batch_size=args.batch_size, num_workers=args.workers) if va else None
    cfg = ExtConfig(in_ch=tr.x.shape[1] * tr.x.shape[2], max_lead=int(tr.lead.max()))
    model = ExtNet(cfg).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    total = args.epochs * len(dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=args.lr, total_steps=max(total, 1), pct_start=0.05)
    os.makedirs(args.out, exist_ok=True)
    best, t0, step = -1.0, time.time(), 0
    log = open(os.path.join(args.out, "log.jsonl"), "a")
    amp = device.type == "cuda"
    for ep in range(args.epochs):
        model.train()
        tot = n = 0.0
        for b in dl:
            x = b["x"].to(device, non_blocking=True)
            with torch.autocast(device_type=device.type, dtype=torch.bfloat16, enabled=amp):
                out = model(x, b["lead"].to(device), b["tod"].to(device))
            ll = lightning_loss(out["lght"].float()[:, None], b["y_lght"].to(device)[:, None], dilate=0)
            lv = vil_loss(out["vil"].float(), b["y_vil"].to(device))
            loss = args.lght_weight * ll + lv
            opt.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sched.step()
            step += 1
            tot += float(loss.detach())
            n += 1
        rec = {"epoch": ep + 1, "step": step, "loss": tot / max(n, 1), "minutes": (time.time() - t0) / 60}
        if vl is not None:
            model.eval()
            res = evaluate(model, vl, device, max_batches=args.val_batches)
            rec["val_lght_csi_mean"] = _mean_csi(res)
            rec["val_lght_csi"] = {k: r["model"]["csi"] for k, r in res["lead_hour"].items()}
            rec["val_hrrr_ltng_csi"] = {k: r["hrrr_ltng"]["csi"] for k, r in res["lead_hour"].items()}
        score = rec.get("val_lght_csi_mean", -rec["loss"])
        state = {"model": model.state_dict(), "cfg": asdict(cfg), "stats": stats, "epoch": ep + 1, "val": rec}
        torch.save(state, os.path.join(args.out, "last.pt.tmp"))
        os.replace(os.path.join(args.out, "last.pt.tmp"), os.path.join(args.out, "last.pt"))
        if score > best:
            best = score
            shutil.copyfile(os.path.join(args.out, "last.pt"), os.path.join(args.out, "best.pt"))
        line = json.dumps(rec)
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()
        if args.deadline_minutes and (time.time() - t0) / 60 > args.deadline_minutes:
            break
    return {"best": best, "epochs": ep + 1}


def load(path: str, device):
    ck = torch.load(path, map_location="cpu", weights_only=False)
    m = ExtNet(ExtConfig(**ck["cfg"]))
    m.load_state_dict(ck["model"])
    return m.to(device).eval(), ck


def main(argv=None):
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--shards", default="shards")
    b.add_argument("--nwp", default="work/nwp")
    b.add_argument("--out", default="ext")
    b.add_argument("--splits", default="train,val,test")
    b.add_argument("--leads", default="1,2,3,4,5,6")
    b.add_argument("--grid", type=int, default=GRID)
    t = sub.add_parser("train")
    t.add_argument("--data", default="ext")
    t.add_argument("--out", default="runs/ext")
    t.add_argument("--epochs", type=int, default=20)
    t.add_argument("--batch-size", type=int, default=128)
    t.add_argument("--lr", type=float, default=1e-3)
    t.add_argument("--lght-weight", type=float, default=10.0)
    t.add_argument("--workers", type=int, default=6)
    t.add_argument("--val-batches", type=int, default=100)
    t.add_argument("--deadline-minutes", type=float)
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--gfs-p", type=float, default=0.5, help="fraction of samples with GFS-missing fields hidden")
    e = sub.add_parser("eval")
    e.add_argument("--ckpt", required=True)
    e.add_argument("--data", required=True)
    e.add_argument("--out", required=True)
    e.add_argument("--batch-size", type=int, default=256)
    e.add_argument("--workers", type=int, default=4)
    e.add_argument("--india-mode", action="store_true", help="hide HRRR-only fields, as with GFS in India")
    args = ap.parse_args(argv)

    if args.cmd == "build":
        leads = tuple(int(k) for k in args.leads.split(","))
        for split in args.splits.split(","):
            build_split(os.path.join(args.shards, split), args.nwp, os.path.join(args.out, split), leads, args.grid)
        shutil.copyfile(os.path.join(args.shards, "train", STATS_FILE), os.path.join(args.out, STATS_FILE))
        return None
    if args.cmd == "train":
        return train(args)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, ck = load(args.ckpt, device)
    ds = ExtDataset(args.data, ck["stats"], gfs_p=1.0 if args.india_mode else 0.0)
    res = evaluate(model, DataLoader(ds, batch_size=args.batch_size, num_workers=args.workers), device)
    res["run"] = {"ckpt": args.ckpt, "epoch": ck.get("epoch"), "samples": len(ds)}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(res, f, indent=1)
    for k, r in res["lead_hour"].items():
        print(f"lead hour {k}: model CSI {r['model']['csi']:.3f} | HRRR LTNG {r['hrrr_ltng']['csi']:.3f} "
              f"| HRRR REFC {r['hrrr_refc']['csi']:.3f} | base rate {r['base_rate']:.4f}")
    return res


if __name__ == "__main__":
    main()
