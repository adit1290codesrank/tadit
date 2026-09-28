"""GK2A AMI (KMA, 128.2 E) L1B from NOAA's open AWS bucket: satellite imagery over India with no login.

Why: INSAT L1B needs a MOSDAC account; GK2A is downloadable right now (s3://noaa-gk2a-pds, 2023-02
onwards, full disk every 10 min, IR 2 km) and its channels match the GOES-16 training data almost
exactly: WV069 (6.94 um) ~ ABI 6.9 um, IR105 (10.35 um) ~ ABI 10.3 um. Viewing angles are good over
eastern and north-eastern India (Odisha, West Bengal, Jharkhand, Bihar, Assam - the lightning
hotspots) and oblique over the far west; tiles with poor coverage are reported as missing.
INSAT-3DR/3DS stays the primary Indian source (india/insat.py); GK2A is the no-credentials path.

Calibration and navigation follow satpy's `ami_l1b` reader (file coefficients, CGMS geostationary
formulas), implemented here with numpy + pyproj only.
"""

from __future__ import annotations

import datetime as dt
import glob
import os
import re
import urllib.request

import numpy as np

from ..constants import FRAME_SECONDS, HR
from ..data.sevir import quantize_ir
from .insat import to_tile
from .tiles import tile_grid

BUCKET = "https://noaa-gk2a-pds.s3.amazonaws.com"
CHANNELS = {"ir069": ("wv069", 6.94), "ir107": ("ir105", 10.35)}  # model channel -> (AMI band, um)
MAX_SCAN_AGE_S = 30 * 60
MIN_COVERAGE = 0.5


def _a(f, k):
    v = f.attrs[k]
    return float(np.ravel(v)[0]) if not isinstance(v, (bytes, str)) else v


def scan_time(path: str) -> dt.datetime:
    m = re.search(r"_(\d{12})\.nc$", os.path.basename(path))
    return dt.datetime.strptime(m.group(1), "%Y%m%d%H%M")


def _geos(f):
    import pyproj

    a, b = _a(f, "earth_equatorial_radius"), _a(f, "earth_polar_radius")
    h = _a(f, "nominal_satellite_height") - a
    lon0 = np.rad2deg(_a(f, "sub_longitude"))
    return pyproj.Proj(f"+proj=geos +h={h} +lon_0={lon0} +a={a} +b={b} +sweep=y"), h


def _window(f, tile, pad_px=40):
    """Pixel window (rows, cols) of the full disk covering the tile."""
    p, h = _geos(f)
    tlat, tlon = tile_grid(tile, 16)
    x, y = p(tlon.ravel(), tlat.ravel())
    ok = np.isfinite(x) & np.isfinite(y) & (np.abs(x) < 1e20)
    if not ok.any():
        return None
    cfac, lfac, coff, loff = (_a(f, k) for k in ("cfac", "lfac", "coff", "loff"))
    col = np.rad2deg(x[ok] / h) * cfac / 2**16 + coff - 1
    row = np.rad2deg(y[ok] / h) * lfac / 2**16 + loff - 1
    n = f["image_pixel_values"].shape
    r0, r1 = int(max(row.min() - pad_px, 0)), int(min(row.max() + pad_px, n[0]))
    c0, c1 = int(max(col.min() - pad_px, 0)), int(min(col.max() + pad_px, n[1]))
    return (r0, r1, c0, c1) if r1 > r0 and c1 > c0 else None


def read_tile(path: str, band_um: float, tile: dict, n: int = HR) -> np.ndarray:
    """Brightness temperature (K) of one AMI channel file on the tile grid (NaN = no coverage)."""
    import h5py

    with h5py.File(path, "r") as f:
        win = _window(f, tile)
        if win is None:
            return np.full((n, n), np.nan, np.float32)
        r0, r1, c0, c1 = win
        ds = f["image_pixel_values"]
        raw = ds[r0:r1, c0:c1].astype(np.int64)
        bits = int(np.ravel(ds.attrs["number_of_valid_bits_per_pixel"])[0])
        good = (raw & 0b1100000000000000) == 0
        dn = (raw & (2**bits - 1)).astype(np.float64)
        rad = _a(f, "DN_to_Radiance_Gain") * dn + _a(f, "DN_to_Radiance_Offset")
        c, k, hp = _a(f, "light_speed"), _a(f, "Boltzmann_constant_k"), _a(f, "Plank_constant_h")
        wn = (10000 / band_um) * 100  # m^-1
        e1 = 2 * hp * c * c * wn**3
        with np.errstate(invalid="ignore", divide="ignore"):
            t_eff = (hp * c / k) * wn / np.log(e1 / (rad * 1e-5) + 1)
        bt = _a(f, "Teff_to_Tbb_c0") + _a(f, "Teff_to_Tbb_c1") * t_eff + _a(f, "Teff_to_Tbb_c2") * t_eff**2
        bt[~good | ~np.isfinite(bt) | (rad <= 0)] = np.nan

        p, h = _geos(f)
        cfac, lfac, coff, loff = (_a(f, kk) for kk in ("cfac", "lfac", "coff", "loff"))
        cc, rr = np.meshgrid(np.arange(c0, c1) + 1, np.arange(r0, r1) + 1)
        x = np.deg2rad((cc - coff) * 2**16 / cfac) * h
        y = np.deg2rad((rr - loff) * 2**16 / lfac) * h
        lon, lat = p(x, y, inverse=True)
    lat = np.where(np.abs(lat) > 90, np.nan, lat)
    lon = np.where(np.abs(lon) > 360, np.nan, lon)
    return to_tile(bt, lat, lon, tile, n)


def find_scans(folder: str) -> list[tuple[dt.datetime, dict]]:
    """Scans with both bands present: [(time, {"wv069": path, "ir105": path})]."""
    by_t: dict = {}
    for pth in glob.glob(os.path.join(folder, "**", "gk2a_ami_le1b_*_fd*_*.nc"), recursive=True):
        band = os.path.basename(pth).split("_")[3]
        by_t.setdefault(scan_time(pth), {})[band] = pth
    return sorted((t, d) for t, d in by_t.items() if {"wv069", "ir105"} <= set(d))


def download(t0: dt.datetime, t_in: int, folder: str, extra_min: int = 10) -> list[str]:
    """Fetch the 10-min full-disk WV069 + IR105 scans covering (t0 - input window - extra, t0]."""
    os.makedirs(folder, exist_ok=True)
    start = t0 - dt.timedelta(seconds=(t_in - 1) * FRAME_SECONDS, minutes=extra_min)
    t = start.replace(minute=start.minute // 10 * 10, second=0, microsecond=0)
    got = []
    while t <= t0:
        for band in ("wv069", "ir105"):
            name = f"gk2a_ami_le1b_{band}_fd020ge_{t:%Y%m%d%H%M}.nc"
            dst = os.path.join(folder, name)
            if not os.path.exists(dst):
                try:
                    urllib.request.urlretrieve(f"{BUCKET}/AMI/L1B/FD/{t:%Y%m/%d/%H}/{name}", dst + ".part")
                    os.replace(dst + ".part", dst)
                except Exception:
                    continue
            got.append(dst)
        t += dt.timedelta(minutes=10)
    return got


def gk2a_frames(scans, tile: dict, t0: dt.datetime, t_in: int, n: int = HR):
    """Model satellite input [t_in, 2, n, n] uint8 (sample-and-hold of 10-min scans) or None."""
    usable = [(t, d) for t, d in scans if t <= t0 and (t0 - t).total_seconds() <= MAX_SCAN_AGE_S + (t_in - 1) * FRAME_SECONDS]
    if not usable or (t0 - usable[-1][0]).total_seconds() > MAX_SCAN_AGE_S:
        return None, [{"t0": t0.isoformat(), "status": "missing", "detail": "no GK2A scan in the last 30 min"}]
    frames = np.zeros((t_in, 2, n, n), np.uint8)
    cache, prov = {}, []
    for j in range(t_in):
        ft = t0 - dt.timedelta(seconds=(t_in - 1 - j) * FRAME_SECONDS)
        cands = [(t, d) for t, d in usable if t <= ft]
        t, d = cands[-1] if cands else usable[0]
        if t not in cache:
            chans, cov = [], 1.0
            for ch, (band, um) in CHANNELS.items():
                bt = read_tile(d[band], um, tile, n)
                cov = min(cov, float(np.isfinite(bt).mean()))
                chans.append(quantize_ir(bt - 273.15, ch))
            if cov < MIN_COVERAGE:
                return None, [{"scan": t.isoformat(), "status": "missing", "detail": f"GK2A covers only {cov:.0%} of this tile"}]
            cache[t] = np.stack(chans)
            prov.append({"scan": t.isoformat(), "coverage": round(cov, 3)})
        frames[j] = cache[t]
    return frames, prov
