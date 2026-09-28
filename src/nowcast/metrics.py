"""Streaming verification metrics.

VIL: CSI per threshold / lead time, at pooling scales 1, 4, 16 (max-pool, kernel = stride), plus MSE.
     Counts are aggregated over the whole set before taking ratios. If you quote Earthformer/PreDiff
     numbers side by side, cross-check pooling details against their code first.
Lightning: CSI / POD / FAR over probability thresholds, strict and with 1-cell (8 km) neighbourhood
     tolerance, plus Brier score and base rate.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F

from .constants import VIL_THRESHOLDS


def _ratio(a, b):
    return torch.where(b > 0, a / b.clamp(min=1e-12), torch.full_like(a, float("nan")))


class VILMetrics:
    def __init__(self, t_out: int, thresholds=VIL_THRESHOLDS, pools=(1, 4, 16)):
        self.thr = tuple(thresholds)
        self.pools = tuple(pools)
        shape = (len(self.pools), t_out, len(self.thr))
        self.hits = torch.zeros(shape, dtype=torch.float64)
        self.misses = torch.zeros(shape, dtype=torch.float64)
        self.fas = torch.zeros(shape, dtype=torch.float64)
        self.se = torch.zeros(t_out, dtype=torch.float64)
        self.n = torch.zeros(t_out, dtype=torch.float64)

    @torch.no_grad()
    def update(self, pred01: torch.Tensor, target01: torch.Tensor) -> None:
        """[B, T, H, W] in [0, 1]"""
        B, T, H, W = pred01.shape
        p, t = pred01.float() * 255.0, target01.float() * 255.0
        self.se += ((pred01.float() - target01.float()) ** 2).mean((2, 3)).sum(0).double().cpu()
        self.n += B
        for i, k in enumerate(self.pools):
            if k > 1:
                pp = F.max_pool2d(p.reshape(B * T, 1, H, W), k).reshape(B, T, -1)
                tt = F.max_pool2d(t.reshape(B * T, 1, H, W), k).reshape(B, T, -1)
            else:
                pp, tt = p.reshape(B, T, -1), t.reshape(B, T, -1)
            for j, thr in enumerate(self.thr):
                ph, th = pp >= thr, tt >= thr
                self.hits[i, :, j] += (ph & th).sum((0, 2)).double().cpu()
                self.misses[i, :, j] += (~ph & th).sum((0, 2)).double().cpu()
                self.fas[i, :, j] += (ph & ~th).sum((0, 2)).double().cpu()

    def compute(self) -> dict:
        out = {"mse_per_lead": (self.se / self.n.clamp(min=1)).tolist()}
        out["mse"] = float((self.se.sum() / self.n.sum().clamp(min=1)))
        for i, k in enumerate(self.pools):
            h, m, f = self.hits[i], self.misses[i], self.fas[i]
            csi_thr = _ratio(h.sum(0), (h + m + f).sum(0))           # per threshold, all leads
            csi_lead_thr = _ratio(h, h + m + f)                       # [T, K]
            key = f"pool{k}"
            out[key] = {
                "csi_per_threshold": dict(zip(map(str, self.thr), csi_thr.tolist())),
                "csi_m": float(torch.nanmean(csi_thr)),
                "csi_m_per_lead": torch.nanmean(csi_lead_thr, dim=1).tolist(),
            }
        return out


class LightningMetrics:
    def __init__(self, t_out: int, prob_thresholds=(0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9),
                 tolerances=(0, 1)):
        self.pt = tuple(prob_thresholds)
        self.tol = tuple(tolerances)
        shape = (len(self.tol), t_out, len(self.pt))
        self.hits = torch.zeros(shape, dtype=torch.float64)
        self.misses = torch.zeros(shape, dtype=torch.float64)
        self.fas = torch.zeros(shape, dtype=torch.float64)
        self.brier = 0.0
        self.pos = 0.0
        self.count = 0.0

    @staticmethod
    def _dilate(x, r):
        if r == 0:
            return x
        B, T, H, W = x.shape
        return F.max_pool2d(x.reshape(B * T, 1, H, W), 2 * r + 1, stride=1, padding=r).reshape(B, T, H, W)

    @torch.no_grad()
    def update(self, prob: torch.Tensor, target: torch.Tensor) -> None:
        """prob, target: [B, T, h, w]; target is binary (>= 1 flash in cell during the frame)."""
        prob, target = prob.float(), target.float()
        self.brier += float(((prob - target) ** 2).sum())
        self.pos += float(target.sum())
        self.count += target.numel()
        for i, r in enumerate(self.tol):
            obs = target > 0.5
            obs_d = self._dilate(target, r) > 0.5
            for j, thr in enumerate(self.pt):
                f = prob >= thr
                f_d = self._dilate(f.float(), r) > 0.5
                self.hits[i, :, j] += (f & obs_d).sum((0, 2, 3)).double().cpu()
                self.misses[i, :, j] += (obs & ~f_d).sum((0, 2, 3)).double().cpu()
                self.fas[i, :, j] += (f & ~obs_d).sum((0, 2, 3)).double().cpu()

    def compute(self) -> dict:
        out = {
            "brier": self.brier / max(self.count, 1),
            "base_rate": self.pos / max(self.count, 1),
        }
        for i, r in enumerate(self.tol):
            h, m, f = self.hits[i].sum(0), self.misses[i].sum(0), self.fas[i].sum(0)
            csi = _ratio(h, h + m + f)
            pod = _ratio(h, h + m)
            far = _ratio(f, h + f)
            best = int(torch.nan_to_num(csi, nan=-1).argmax())
            hl, ml, fl = self.hits[i][:, best], self.misses[i][:, best], self.fas[i][:, best]
            out[f"tol{r}"] = {
                "best_threshold": self.pt[best],
                "csi": float(csi[best]),
                "pod": float(pod[best]),
                "far": float(far[best]),
                "csi_per_lead": _ratio(hl, hl + ml + fl).tolist(),
                "csi_per_threshold": dict(zip(map(str, self.pt), csi.tolist())),
            }
        return out
