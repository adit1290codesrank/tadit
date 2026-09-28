"""Torch dataset over event shards: random 25-frame windows, NWP selection, rotation augmentation.

Everything is returned as uint8 / float16 numpy arrays; `prepare_batch` converts on the GPU
(4x less host->device traffic than shipping float32).
"""

from __future__ import annotations

import math

import numpy as np
import torch
from torch.utils.data import Dataset

from ..constants import FRAMES, LGHT_LOG_SCALE, NWP_HOURS, T_IN, T_OUT, WINDOW
from .shards import ShardStore


class NowcastDataset(Dataset):
    def __init__(
        self,
        root: str,
        train: bool,
        windows_per_event: int = 3,
        rotate: bool = True,
        stats: dict | None = None,
    ):
        self.store = ShardStore(root)
        self.train = train
        self.wpe = windows_per_event
        self.rotate = rotate and train
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
        assert self.frames >= WINDOW, f"events have {self.frames} frames < window {WINDOW}"

    def __len__(self) -> int:
        return len(self.store) * self.wpe

    def _start(self, k: int) -> int:
        max_start = self.frames - WINDOW
        if self.train:
            return int(torch.randint(0, max_start + 1, (1,)))
        if self.wpe == 1:
            return max_start // 2
        return round(k * max_start / (self.wpe - 1))

    def _nwp(self, a: dict, t0: int) -> tuple[np.ndarray, np.ndarray]:
        v = len(self.nwp_vars)
        out = np.zeros((NWP_HOURS, v, self.lr, self.lr), np.float16)
        ok = np.zeros(NWP_HOURS, bool)
        if v == 0 or "nwp" not in a:
            return out, ok
        nwp, first_hour = a["nwp"], int(a["nwp_t0"])
        nwp_ok = a["nwp_ok"]
        h0 = (t0 // 3600 * 3600 - first_hour) // 3600
        for j in range(NWP_HOURS):
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
        w = slice(s, s + WINDOW)
        vil, ir, lg = a["vil"][w], a["ir"][w], a["lght"][w]
        t0 = int(a["times"][s + T_IN - 1])
        nwp, nwp_ok = self._nwp(a, t0)

        # local solar time of day at the patch centre
        hour = ((t0 % 86400) / 3600.0 + float(a.get("center_lon", 0.0)) / 15.0) % 24.0
        tod = np.array([math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24)], np.float32)

        if self.rotate:
            # 90-degree rotations only: every stored field is a rotation-invariant scalar
            # (shear magnitude, not u/v). No flips: flips change the sign of helicity.
            r = int(torch.randint(0, 4, (1,)))
            if r:
                vil, ir, lg, nwp = (np.rot90(x, r, axes=(-2, -1)) for x in (vil, ir, lg, nwp))

        c = np.ascontiguousarray
        return {
            "vil_in": c(vil[:T_IN]),
            "vil_out": c(vil[T_IN:]),
            "ir_in": c(ir[:T_IN]),
            "lght_in": c(lg[:T_IN]),
            "lght_out": c(lg[T_IN:]),
            "nwp": c(nwp),
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
