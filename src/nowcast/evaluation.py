"""Evaluation loop shared by training-time validation, evaluate.py and the baselines.

A predictor maps model inputs (see data.dataset.prepare_batch) to
{"vil": [B, T_out, H, W] in [0, 1], "lght_prob": [B, T_out, h, w] in [0, 1]}.
"""

from __future__ import annotations

import numpy as np
import torch

from .data.dataset import prepare_batch
from .metrics import LightningMetrics, VILMetrics


def model_predictor(model, amp_dtype=torch.bfloat16, force_missing: tuple = ()):
    @torch.no_grad()
    def predict(x):
        dev = x["vil"].device if "vil" in x else next(iter(x.values())).device
        with torch.autocast(device_type=dev.type, dtype=amp_dtype, enabled=amp_dtype is not None and dev.type == "cuda"):
            out = model(x, force_missing=force_missing)
        return {"vil": out["vil"].float().clamp(0, 1), "lght_prob": torch.sigmoid(out["lght"].float())}

    return predict


@torch.no_grad()
def run_eval(predict, loader, device, t_out: int, max_batches: int | None = None, save_examples: int = 0):
    vm, lm = VILMetrics(t_out), LightningMetrics(t_out)
    examples = {"vil_in": [], "vil_true": [], "vil_pred": [], "lght_true": [], "lght_prob": []}
    n_saved = 0
    for i, batch in enumerate(loader):
        if max_batches is not None and i >= max_batches:
            break
        x, y = prepare_batch(batch, device)
        out = predict(x)
        vm.update(out["vil"], y["vil"])
        lm.update(out["lght_prob"], y["lght"])
        if n_saved < save_examples:
            k = min(save_examples - n_saved, y["vil"].shape[0])
            examples["vil_in"].append((x["vil"][:k] * 255).round().byte().cpu().numpy())
            examples["vil_true"].append((y["vil"][:k] * 255).round().byte().cpu().numpy())
            examples["vil_pred"].append((out["vil"][:k] * 255).round().byte().cpu().numpy())
            examples["lght_true"].append(y["lght"][:k].byte().cpu().numpy())
            examples["lght_prob"].append(out["lght_prob"][:k].half().cpu().numpy())
            n_saved += k
    result = {"vil": vm.compute(), "lght": lm.compute()}
    ex = {k: np.concatenate(v) for k, v in examples.items() if v} if n_saved else None
    return result, ex


def summary(result: dict) -> dict:
    """The handful of numbers worth printing in a log line / results table."""
    v, l = result["vil"], result["lght"]
    return {
        "vil_csi_m": v["pool1"]["csi_m"],
        "vil_csi_m_pool16": v.get("pool16", v["pool1"])["csi_m"],
        "vil_csi_74": v["pool1"]["csi_per_threshold"].get("74"),
        "vil_csi_181": v["pool1"]["csi_per_threshold"].get("181"),
        "vil_mse": v["mse"],
        "lght_csi": l["tol0"]["csi"],
        "lght_csi_tol1": l.get("tol1", l["tol0"])["csi"],
        "lght_brier": l["brier"],
    }
