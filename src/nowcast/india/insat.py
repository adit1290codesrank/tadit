"""INSAT-3DR / INSAT-3DS imager L1B (MOSDAC, free registration) -> the model's satellite channels.

File layout (MOSDAC L1B_STD HDF5, as read by satpy's `insat3d_img_l1b_h5` reader):
  IMG_TIR1 / IMG_WV          (1, rows, cols) uint16 counts, _FillValue attribute (0)
  IMG_TIR1_TEMP / IMG_WV_TEMP (1024,) lookup table: count -> brightness temperature (K)
  Latitude / Longitude        4 km grid (TIR1); Latitude_WV / Longitude_WV 8 km grid (WV);
                              scaled integers (scale_factor / add_offset / _FillValue attributes)
  attrs["Acquisition_Start_Time"] e.g. "09-Jun-2009T09:00:00"
Channel match with the GOES-16 training data: TIR1 10.3-11.3 um ~ ABI 10.3 um (ir107);
WV 6.5-7.1 um ~ ABI 6.9 um (ir069). Resolution and scan rate are coarser (4/8 km, 15-30 min);
training includes INSAT-like degraded samples (data.dataset.insat_like) for exactly this reason.
"""

from __future__ import annotations

import datetime as dt
import glob
import os

import numpy as np

from ..constants import FRAME_SECONDS, HR
from ..data.hrrr import Regridder
from ..data.sevir import quantize_ir
from .tiles import tile_grid

CHANNELS = {"ir069": ("IMG_WV", "Latitude_WV", "Longitude_WV"),
            "ir107": ("IMG_TIR1", "Latitude", "Longitude")}
MAX_SCAN_AGE_S = 45 * 60  # older than this, the satellite leg counts as missing


def _attr(obj, name, default=None):
    v = obj.attrs.get(name, default)
    if isinstance(v, bytes):
        v = v.decode()
    if isinstance(v, np.ndarray) and v.size == 1:
        v = v.item()
    return v


def _decode(ds) -> np.ndarray:
    x = ds[()].astype(np.float64)
    fill = _attr(ds, "_FillValue")
    bad = (x == fill) if fill is not None else np.zeros(x.shape, bool)
    x = x * float(_attr(ds, "scale_factor", 1.0)) + float(_attr(ds, "add_offset", 0.0))
    x[bad] = np.nan
    return np.squeeze(x)


def scan_time(path: str) -> dt.datetime:
    import h5py

    with h5py.File(path, "r") as f:
        return dt.datetime.strptime(_attr(f, "Acquisition_Start_Time"), "%d-%b-%YT%H:%M:%S")


def read_channel(path: str, channel: str):
    """-> (brightness temperature K, lat, lon), each [rows, cols]; NaN where no data."""
    import h5py

    var, latn, lonn = CHANNELS[channel]
    with h5py.File(path, "r") as f:
        counts = np.squeeze(f[var][()]).astype(np.int64)
        lut = f[var + "_TEMP"][()].astype(np.float64)
        fill = _attr(f[var], "_FillValue", 0)
        bt = lut[np.clip(counts, 0, len(lut) - 1)]
        bt[(counts == fill) | (counts >= len(lut))] = np.nan
        lat, lon = _decode(f[latn]), _decode(f[lonn])
    return bt, lat, lon


def to_tile(bt: np.ndarray, lat: np.ndarray, lon: np.ndarray, tile: dict, n: int = HR) -> np.ndarray:
    """Brightness temperature (K) resampled onto the tile's n x n grid (NaN outside coverage)."""
    tlat, tlon = tile_grid(tile, n)
    pad = 1.0
    m = (np.isfinite(bt) & np.isfinite(lat) & np.isfinite(lon)
         & (lat > tlat.min() - pad) & (lat < tlat.max() + pad)
         & (lon > tlon.min() - pad) & (lon < tlon.max() + pad))
    if m.sum() < 16:
        return np.full((n, n), np.nan, np.float32)
    rg = Regridder(lat[m], lon[m], k=4)
    return Regridder.apply(bt[m][None, None, :], rg.weights(tlat, tlon))[0].astype(np.float32)


def find_scans(folder: str) -> list[tuple[dt.datetime, str]]:
    """All readable imager files under `folder` (MOSDAC names look like 3RIMG_10MAY2024_0900_L1B_STD_V01R00.h5)."""
    out = []
    for p in sorted(glob.glob(os.path.join(folder, "**", "*.h5"), recursive=True)):
        try:
            out.append((scan_time(p), p))
        except (KeyError, OSError, ValueError, TypeError):
            continue  # not an imager L1B file
    return sorted(out)


def insat_frames(scans: list[tuple[dt.datetime, str]], tile: dict, t0: dt.datetime, t_in: int, n: int = HR):
    """Model satellite input [t_in, 2, n, n] uint8 for frames t0-(t_in-1)*5min .. t0, each taken from
    the latest scan at or before that frame time (sample-and-hold, as INSAT scans every 15-30 min).
    Returns (frames or None, provenance list)."""
    frames = np.zeros((t_in, 2, n, n), np.uint8)
    cache, prov = {}, []
    usable = [(t, p) for t, p in scans if t <= t0 and (t0 - t).total_seconds() <= MAX_SCAN_AGE_S + (t_in - 1) * FRAME_SECONDS]
    if not usable or (t0 - usable[-1][0]).total_seconds() > MAX_SCAN_AGE_S:
        return None, [{"t0": t0.isoformat(), "status": "missing", "detail": "no INSAT scan in the last 45 min"}]
    for j in range(t_in):
        ft = t0 - dt.timedelta(seconds=(t_in - 1 - j) * FRAME_SECONDS)
        cands = [(t, p) for t, p in usable if t <= ft]
        t, p = cands[-1] if cands else usable[0]  # before the first scan: hold the earliest one
        if p not in cache:
            chans = []
            for c in ("ir069", "ir107"):
                bt, lat, lon = read_channel(p, c)
                chans.append(quantize_ir(to_tile(bt, lat, lon, tile, n) - 273.15, c))
            cache[p] = np.stack(chans)
            prov.append({"scan": t.isoformat(), "file": os.path.basename(p)})
        frames[j] = cache[p]
    return frames, prov
