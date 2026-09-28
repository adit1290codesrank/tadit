"""Intensity-weighted VIL loss (TrajGRU-style B-MSE/B-MAE) + focal BCE for lightning."""

from __future__ import annotations

import torch
import torch.nn.functional as F

from .constants import VIL_THRESHOLDS


def vil_weights(target01: torch.Tensor, thresholds=VIL_THRESHOLDS, weights=(1, 2, 5, 10, 20, 30, 40)):
    """Per-pixel weight by intensity band: weights[0] below thresholds[0], weights[k+1] above thresholds[k]."""
    assert len(weights) == len(thresholds) + 1
    t = target01 * 255.0
    w = torch.full_like(t, float(weights[0]))
    for thr, wt in zip(thresholds, weights[1:]):
        w = torch.where(t >= thr, torch.full_like(t, float(wt)), w)
    return w


def vil_loss(pred: torch.Tensor, target: torch.Tensor, weights=(1, 2, 5, 10, 20, 30, 40)) -> torch.Tensor:
    e = pred - target
    w = vil_weights(target, weights=weights)
    return (w * (e.abs() + e * e)).mean()


def lightning_loss(logits: torch.Tensor, target: torch.Tensor, gamma: float = 2.0, dilate: int = 1,
                   pos_weight: float = 1.0) -> torch.Tensor:
    """Focal BCE. `dilate` cells of spatial tolerance: a flash in a neighbouring 8 km cell also
    counts as positive, which makes the rare-event target learnable."""
    if dilate:
        B, T, H, W = target.shape
        target = F.max_pool2d(target.reshape(B * T, 1, H, W), 2 * dilate + 1, stride=1,
                              padding=dilate).reshape(B, T, H, W)
    pw = torch.tensor(pos_weight, device=logits.device, dtype=logits.dtype)
    bce = F.binary_cross_entropy_with_logits(logits, target, reduction="none", pos_weight=pw)
    if gamma:
        p = torch.sigmoid(logits)
        pt = p * target + (1 - p) * (1 - target)
        bce = bce * (1 - pt).pow(gamma)
    return bce.mean()


def total_loss(out: dict, y: dict, lght_weight: float = 10.0, vil_band_weights=(1, 2, 5, 10, 20, 30, 40),
               focal_gamma: float = 2.0, lght_dilate: int = 1, lght_pos_weight: float = 1.0):
    lv = vil_loss(out["vil"].float(), y["vil"], vil_band_weights)
    ll = lightning_loss(out["lght"].float(), y["lght"], focal_gamma, lght_dilate, lght_pos_weight)
    return lv + lght_weight * ll, {"loss_vil": lv.detach(), "loss_lght": ll.detach()}
