"""Reference forecasts: persistence and pySTEPS optical-flow extrapolation."""

from __future__ import annotations

import numpy as np
import torch


def persistence_predictor(t_out: int):
    @torch.no_grad()
    def predict(x):
        vil = x["vil"][:, -1:].expand(-1, t_out, -1, -1).clamp(0, 1)
        lg = (x["lght"][:, -1:] > 0).float().expand(-1, t_out, -1, -1)
        return {"vil": vil.contiguous(), "lght_prob": lg.contiguous()}

    return predict


def pysteps_predictor(t_out: int, n_frames: int = 4):
    """Lucas-Kanade motion on the last `n_frames` VIL frames + semi-Lagrangian extrapolation.
    Lightning is advected with the same (rescaled) motion field. CPU-bound: run it on spare cores."""
    from pysteps import extrapolation, motion

    oflow = motion.get_method("LK")
    extrap = extrapolation.get_method("semilagrangian")

    @torch.no_grad()
    def predict(x):
        vil = x["vil"].float().cpu().numpy()
        lg = (x["lght"] > 0).float().cpu().numpy()
        B, _, H, W = vil.shape
        h = lg.shape[-1]
        r = H // h
        out_v = np.zeros((B, t_out, H, W), np.float32)
        out_l = np.zeros((B, t_out, h, h), np.float32)
        for b in range(B):
            v = oflow(vil[b, -n_frames:])
            fv = extrap(vil[b, -1], v, t_out)
            out_v[b] = np.nan_to_num(fv, nan=0.0)
            vl = v[:, r // 2 :: r, r // 2 :: r] / r
            fl = extrap(lg[b, -1], vl, t_out)
            out_l[b] = np.nan_to_num(fl, nan=0.0)
        dev = x["vil"].device
        return {"vil": torch.from_numpy(out_v).clamp(0, 1).to(dev),
                "lght_prob": torch.from_numpy(out_l).clamp(0, 1).to(dev)}

    return predict
