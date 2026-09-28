"""Synthetic events in the exact shard format, for tests and for developing the training loop
before real data exists.

Storm cells advect and grow/decay. IR is cold under cells, lightning fires where cells are
intense, and one NWP channel marks where new cells will form, so the fusion path has a signal to find.
"""

from __future__ import annotations

import numpy as np

from ..constants import DEFAULT_FRAME_OFFSETS_S, HR, IR_CHANNELS, LR
from .hrrr import NWP_VARS
from .shards import RunningStats, ShardWriter, write_stats


def _blobs(cells, t, hr):
    yy, xx = np.mgrid[0:hr, 0:hr].astype(np.float32)
    out = np.zeros((hr, hr), np.float32)
    for c in cells:
        if not (c["t_on"] <= t <= c["t_off"]):
            continue
        life = (t - c["t_on"]) / max(c["t_off"] - c["t_on"], 1)
        amp = c["amp"] * np.sin(np.pi * np.clip(life, 0, 1)) ** 0.5
        cx, cy = c["x"] + c["vx"] * t, c["y"] + c["vy"] * t
        out += amp * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * c["s"] ** 2))
    return out


def synthetic_event(rng: np.random.Generator, t_event: int, hr: int = HR, lr: int = LR,
                    frames: int = 49) -> dict[str, np.ndarray]:
    offsets = DEFAULT_FRAME_OFFSETS_S[:frames] if frames <= 49 else np.arange(frames) * 300
    ncell = int(rng.integers(1, 6))
    cells = []
    for _ in range(ncell):
        t_on = int(rng.integers(-10, frames - 5))
        cells.append(dict(
            x=rng.uniform(0.1, 0.9) * hr, y=rng.uniform(0.1, 0.9) * hr,
            vx=rng.normal(0, 0.012) * hr, vy=rng.normal(0, 0.012) * hr,
            s=rng.uniform(0.03, 0.09) * hr, amp=rng.uniform(80, 260),
            t_on=t_on, t_off=t_on + int(rng.integers(12, 40)),
        ))
    vil = np.stack([_blobs(cells, t, hr) for t in range(frames)])
    vil = np.clip(vil + rng.normal(0, 2, vil.shape), 0, 255)

    ir069 = np.clip(210 - 0.5 * vil + rng.normal(0, 3, vil.shape), 0, 255)
    ir107 = np.clip(230 - 0.8 * vil + rng.normal(0, 3, vil.shape), 0, 255)
    ir = np.stack([ir069, ir107], 1).astype(np.uint8)

    f = hr // lr
    vil_lr = vil.reshape(frames, lr, f, lr, f).max(axis=(2, 4))
    rate = 3.0 / (1 + np.exp(-(vil_lr - 170) / 12))
    lght = np.minimum(rng.poisson(rate), 255).astype(np.uint8)

    # NWP: hourly fields; "cape" is high where cells will be active within the next ~2 h.
    t0_hour = (t_event + int(offsets[0])) // 3600 * 3600
    t_last = (t_event + int(offsets[-1])) // 3600 * 3600 + 2 * 3600
    hours = np.arange(t0_hour, t_last + 1, 3600)
    v = len(NWP_VARS)
    nwp = np.zeros((len(hours), v, lr, lr), np.float32)
    for h, hu in enumerate(hours):
        frame = int(np.clip((hu - t_event - offsets[0]) // 300, 0, frames - 1))
        fut = np.stack([_blobs(cells, t, hr) for t in range(frame, min(frame + 24, frames), 4)]).max(0)
        fut = fut.reshape(lr, f, lr, f).mean(axis=(1, 3))
        nwp[h] = rng.normal(0, 0.5, (v, lr, lr))
        nwp[h, 0] = np.log1p(fut * 10) + rng.normal(0, 0.2, (lr, lr))
    return {
        "vil": vil.astype(np.uint8),
        "ir": ir,
        "lght": lght,
        "times": (t_event + offsets).astype(np.int64),
        "center_lat": np.float32(35.0),
        "center_lon": np.float32(-95.0),
        "nwp": nwp.astype(np.float16),
        "nwp_t0": np.int64(hours[0]),
        "nwp_ok": np.ones(len(hours), bool),
    }


def write_synthetic_split(out_dir: str, n_events: int, seed: int = 0, hr: int = HR, lr: int = LR,
                          frames: int = 49, events_per_shard: int = 64, stats: dict | None = None) -> dict:
    """Writes a synthetic split. Returns the NWP stats written (reuse them for val/test)."""
    rng = np.random.default_rng(seed)
    rs = RunningStats(NWP_VARS)
    with ShardWriter(out_dir, events_per_shard=events_per_shard) as w:
        for i in range(n_events):
            t_event = 1_530_000_000 + int(rng.integers(0, 3600 * 24 * 90))
            a = synthetic_event(rng, t_event, hr, lr, frames)
            rs.update(a["nwp"])
            w.add(f"SYN{seed:03d}_{i:06d}", int(a["times"][0]), a)
    stats = stats or rs.result()
    write_stats(out_dir, stats)
    return stats


assert len(IR_CHANNELS) == 2
