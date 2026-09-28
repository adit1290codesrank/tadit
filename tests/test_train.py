import json
import os

import torch

from nowcast import evaluate, train
from nowcast.data.dataset import NowcastDataset, prepare_batch
from nowcast.losses import total_loss
from nowcast.model import FusionNowcaster

from conftest import tiny_model_cfg

TINY = [
    "model.stem_ch=16", "model.chs=[16,32,48,64]", "model.enc_blocks=1", "model.dec_blocks=1",
    "model.attn_depth=1", "model.heads=2", "model.cond_dim=32",
    "train.batch_size=2", "train.amp=fp32", "train.channels_last=false", "train.log_every=4",
    "train.warmup_steps=2", "train.val_batches=2", "train.min_free_gb=0", "data.num_workers=0",
    "data.windows_per_event=2",
]


def test_overfit_one_batch(tiny_shards):
    torch.manual_seed(0)
    ds = NowcastDataset(f"{tiny_shards}/train", train=False, windows_per_event=1)
    batch = torch.utils.data.default_collate([ds[i] for i in range(2)])
    x, y = prepare_batch(batch, torch.device("cpu"))
    m = FusionNowcaster(tiny_model_cfg(nwp_vars=len(ds.nwp_vars)))
    opt = torch.optim.AdamW(m.parameters(), lr=3e-3)
    first = None
    for _ in range(40):
        loss, _ = total_loss(m(x), y)
        opt.zero_grad()
        loss.backward()
        opt.step()
        first = first if first is not None else loss.item()
    assert loss.item() < 0.5 * first, (first, loss.item())


def _run(tiny_shards, out_dir, extra=(), argv_extra=()):
    sets = TINY + [f"data.train_dir={tiny_shards}/train", f"data.val_dir={tiny_shards}/val",
                   f"train.out_dir={out_dir}", *extra]
    argv = [a for s in sets for a in ("--set", s)] + list(argv_extra)
    return train.main(argv)


def test_train_resume_and_evaluate(tiny_shards, tmp_path):
    out = tmp_path / "run"
    r = _run(tiny_shards, out, ["train.max_steps=8"])
    assert r["step"] == 8 and r["samples"] == 16
    assert (out / "latest.pt").exists() and (out / "final_ema_bf16.pt").exists()
    logs = [json.loads(line) for line in open(out / "log.jsonl")]
    assert any(l.get("event") == "final_val" for l in logs)

    # continue the run: step/sample counters carry over
    r2 = _run(tiny_shards, tmp_path / "run2", ["train.max_steps=4"], ["--resume", str(out / "latest.pt")])
    assert r2["step"] == 12 and r2["samples"] == 24

    # radar-only control warm-started from the full model's weights (shape-matched subset)
    r3 = _run(tiny_shards, tmp_path / "radar", ["train.max_steps=4", "model.modalities=[vil]"],
              ["--init-from", str(out / "latest.pt")])
    assert r3["step"] == 4

    res = evaluate.main(["--ckpt", str(out / "final_ema_bf16.pt"), "--data", f"{tiny_shards}/val",
                         "--out", str(tmp_path / "res.json"), "--workers", "0", "--batch-size", "2",
                         "--drop", "nwp,ir", "--save-examples", "2"])
    assert 0.0 <= res["summary"]["vil_mse"] < 1.0
    assert os.path.exists(tmp_path / "res_examples.npz")

    base = evaluate.main(["--baseline", "persistence", "--data", f"{tiny_shards}/val",
                          "--out", str(tmp_path / "pers.json"), "--workers", "0"])
    assert "vil_csi_m" in base["summary"]


def test_deadline_mode_stops(tiny_shards, tmp_path):
    r = _run(tiny_shards, tmp_path / "dl", ["train.deadline_minutes=0.05", "train.reserve_minutes=0"])
    assert r["step"] > 0
