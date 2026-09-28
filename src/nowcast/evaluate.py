"""Test-set evaluation, inference-time ablations and baselines.

  python -m nowcast.evaluate --ckpt runs/full/final_ema_bf16.pt --data shards/test --out results/full.json
  python -m nowcast.evaluate --ckpt ... --drop nwp,ir          # sensor-missing ablation (no retraining)
  python -m nowcast.evaluate --baseline persistence --data shards/test --out results/persistence.json
  python -m nowcast.evaluate --baseline pysteps ...
"""

from __future__ import annotations

import argparse
import json
import os

import numpy as np
import torch
from torch.utils.data import DataLoader

from .baselines import persistence_predictor, pysteps_predictor
from .constants import T_OUT
from .data.dataset import NowcastDataset
from .evaluation import model_predictor, run_eval, summary
from .model.fusion import FusionNowcaster, ModelConfig


def load_model(path: str, device, weights: str = "ema"):
    ck = torch.load(path, map_location="cpu", weights_only=False)
    model = FusionNowcaster(ModelConfig(**ck["model_cfg"]))
    sd = ck.get(weights) or ck["ema"]
    model.load_state_dict({k: v.float() if v.is_floating_point() else v for k, v in sd.items()})
    return model.to(device).eval(), ck


def main(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--ckpt")
    ap.add_argument("--baseline", choices=["persistence", "pysteps"])
    ap.add_argument("--weights", default="ema", choices=["ema", "model"])
    ap.add_argument("--drop", default="", help="comma-separated modalities to treat as missing")
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--max-batches", type=int)
    ap.add_argument("--windows-per-event", type=int, default=3)
    ap.add_argument("--save-examples", type=int, default=0)
    args = ap.parse_args(argv)
    if bool(args.ckpt) == bool(args.baseline):
        raise SystemExit("give exactly one of --ckpt / --baseline")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    stats = None
    if args.ckpt:
        model, ck = load_model(args.ckpt, device, args.weights)
        stats = ck.get("nwp_stats")  # always normalise with the training statistics
        drop = tuple(m for m in args.drop.split(",") if m)
        amp = torch.bfloat16 if device.type == "cuda" else None
        predict = model_predictor(model, amp, force_missing=drop)
        name = {"ckpt": args.ckpt, "drop": list(drop), "step": ck.get("step"), "samples": ck.get("samples")}
    elif args.baseline == "persistence":
        predict, name = persistence_predictor(T_OUT), {"baseline": "persistence"}
    else:
        predict, name = pysteps_predictor(T_OUT), {"baseline": "pysteps"}

    ds = NowcastDataset(args.data, train=False, windows_per_event=args.windows_per_event, stats=stats)
    loader = DataLoader(ds, batch_size=args.batch_size, num_workers=args.workers,
                        pin_memory=device.type == "cuda")
    result, examples = run_eval(predict, loader, device, T_OUT, args.max_batches, args.save_examples)
    result = {"run": name, "summary": summary(result), **result}

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump(result, f, indent=1)
    if examples is not None:
        np.savez_compressed(os.path.splitext(args.out)[0] + "_examples.npz", **examples)
    print(json.dumps({"run": name, **result["summary"]}))
    return result


if __name__ == "__main__":
    main()
