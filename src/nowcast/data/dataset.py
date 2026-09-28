"""Torch dataset over event shards: random windows, NWP selection, rotation augmentation.

Horizon = (t_in, t_out, out_step): t_in input frames at 5-min spacing ending at t0, then t_out
targets every `out_step` frames. VIL targets are the instantaneous frame at each lead; lightning
targets count every flash in the interval (lead_{k-1}, lead_k], so a 10-min step asks
"any lightning in this 10 minutes", not "in the last 5 minutes of it".

Everything is returned as uint8 / float16 numpy arrays; `prepare_batch` converts on the GPU
(4x less host->device traffic than shipping float32).
"""

from __future__ import annotations

import math

import numpy as np
import torch
from torch.utils.data import Dataset

from ..constants import FRAMES, LGHT_LOG_SCALE, OUT_STEP, T_IN, T_OUT, horizon_frames, nwp_hours_for
from .shards import ShardStore


class NowcastDataset(Dataset):
    def __init__(
        self,
        root: str,
        train: bool,
        windows_per_event: int = 3,
        rotate: bool = True,
        stats: dict | None = None,
        t_in: int = T_IN,
        t_out: int = T_OUT,
        out_step: int = OUT_STEP,
    ):
        self.store = ShardStore(root)
        self.train = train
        self.rotate = rotate and train
        self.t_in, self.t_out, self.out_step = t_in, t_out, out_step
        self.nwp_hours = nwp_hours_for(t_out, out_step)
        stats = stats or self.store.stats()
        if stats is not None:
            self.nwp_vars = list(stats["vars"])
            self.nwp_mean = np.asarray(stats["mean"], np.float32)[:, None, None]
            self.nwp_std = np.asarray(stats["std"], np.float32)[:, None, None]
        else:
            self.nwp_vars = []
        first = self.store.get(0)
        self.ir_channels = first["ir"].shape[1]
        self.hr = first["vil"].shape[-1]
        self.lr = first["lght"].shape[-1]
        self.frames = first["vil"].shape[0]
        self.max_start = self.frames - horizon_frames(t_in, t_out, out_step)
        if self.max_start < 0:
            raise ValueError(f"horizon t_in={t_in}, t_out={t_out}, out_step={out_step} needs "
                             f"{horizon_frames(t_in, t_out, out_step)} frames; events have {self.frames}")
        self.wpe = min(windows_per_event, self.max_start + 1)

    @property
    def lead_minutes(self) -> list[int]:
        return [(k + 1) * self.out_step * 5 for k in range(self.t_out)]

    def __len__(self) -> int:
        return len(self.store) * self.wpe

    def _start(self, k: int) -> int:
        if self.train:
            return int(torch.randint(0, self.max_start + 1, (1,)))
        if self.wpe == 1:
            return self.max_start // 2
        return round(k * self.max_start / (self.wpe - 1))

    def _nwp(self, a: dict, t0: int) -> tuple[np.ndarray, np.ndarray]:
        v, nh = len(self.nwp_vars), self.nwp_hours
        out = np.zeros((nh, v, self.lr, self.lr), np.float16)
        ok = np.zeros(nh, bool)
        if v == 0 or "nwp" not in a:
            return out, ok
        nwp, first_hour = a["nwp"], int(a["nwp_t0"])
        nwp_ok = a["nwp_ok"]
        h0 = (t0 // 3600 * 3600 - first_hour) // 3600
        for j in range(nh):
            h = h0 + j
            if 0 <= h < len(nwp) and nwp_ok[h]:
                x = (nwp[h].astype(np.float32) - self.nwp_mean) / self.nwp_std
                # sparse fields (LTNG, updraft helicity) have tiny std: clip their rare spikes
                out[j] = np.clip(np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0), -10, 10)
                ok[j] = True
        return out, ok

    def __getitem__(self, i: int) -> dict[str, np.ndarray]:
        ev, k = divmod(i, self.wpe)
        a = self.store.get(ev)
        s = self._start(k)
        i0 = s + self.t_in - 1  # index of t0 (last input frame)
        st = self.out_step
        vil_in, ir_in, lg_in = a["vil"][s : i0 + 1], a["ir"][s : i0 + 1], a["lght"][s : i0 + 1]
        vil_out = a["vil"][i0 + st : i0 + st * self.t_out + 1 : st]
        lg = a["lght"][i0 + 1 : i0 + st * self.t_out + 1].astype(np.uint16)
        lg_out = np.minimum(lg.reshape(self.t_out, st, *lg.shape[1:]).sum(1), 255).astype(np.uint8)
        t0 = int(a["times"][i0])
        nwp, nwp_ok = self._nwp(a, t0)

        # local solar time of day at the patch centre
        hour = ((t0 % 86400) / 3600.0 + float(a.get("center_lon", 0.0)) / 15.0) % 24.0
        tod = np.array([math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24)], np.float32)

        arrs = [vil_in, vil_out, ir_in, lg_in, lg_out, nwp]
        if self.rotate:
            # 90-degree rotations only: every stored field is a rotation-invariant scalar
            # (shear magnitude, not u/v). No flips: flips change the sign of helicity.
            r = int(torch.randint(0, 4, (1,)))
            if r:
                arrs = [np.rot90(x, r, axes=(-2, -1)) for x in arrs]
        vil_in, vil_out, ir_in, lg_in, lg_out, nwp = (np.ascontiguousarray(x) for x in arrs)
        return {
            "vil_in": vil_in,
            "vil_out": vil_out,
            "ir_in": ir_in,
            "lght_in": lg_in,
            "lght_out": lg_out,
            "nwp": nwp,
            "nwp_ok": nwp_ok,
            "tod": tod,
        }


def prepare_batch(batch: dict[str, torch.Tensor], device: torch.device):
    """uint8 batch -> (model inputs, targets) as float tensors on `device`."""
    nb = device.type == "cuda"

    def g(k):
        return batch[k].to(device, non_blocking=nb)

    nwp_ok = g("nwp_ok")
    x = {
        "vil": g("vil_in").float().div_(255.0),
        "ir": g("ir_in").float().div_(255.0).flatten(1, 2),  # [B, T*C, H, W]
        "lght": torch.log1p(g("lght_in").float()).div_(LGHT_LOG_SCALE),
        "nwp": g("nwp").float().flatten(1, 2),  # [B, hours*V, h, w]
        "tod": g("tod").float(),
        "present": {"nwp": nwp_ok.any(1)},
    }
    y = {"vil": g("vil_out").float().div_(255.0), "lght": (g("lght_out") > 0).float()}
    return x, y


__all__ = ["NowcastDataset", "prepare_batch", "FRAMES", "T_IN", "T_OUT"]
