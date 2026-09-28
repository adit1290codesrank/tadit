"""HRRR NWP context: byte-range fetch with Herbie, KD-tree regrid onto each event's 48 x 48 grid.

Leakage rule: the field valid at hour H comes from the run initialised at H - LEAD_H (f01), i.e.
what an operational forecaster would actually have had at that time.
"""

from __future__ import annotations

import numpy as np

LEAD_H = 1
SOURCES = ("aws", "google", "azure")

# (name, Herbie search regex). All verified present in the wrfsfc f01 files of both the HRRRv2
# (2018-05) and HRRRv3 (2019-06) periods SEVIR covers (`scripts/fetch_hrrr.py --inventory`).
# RH is not in the sfc file at 700 mb, so mid-level dryness is the 700 mb dewpoint depression.
HRRR_FIELDS = [
    ("cape_sfc", ":CAPE:surface"),
    ("cape_mu", ":CAPE:255-0 mb above ground"),
    ("cin_sfc", ":CIN:surface"),
    ("lftx", ":LFTX:500-1000 mb"),
    ("pwat", ":PWAT:entire atmosphere"),
    ("hlcy03", ":HLCY:3000-0 m above ground"),
    ("vucsh06", ":VUCSH:0-6000 m above ground"),
    ("vvcsh06", ":VVCSH:0-6000 m above ground"),
    ("refc", ":REFC:entire atmosphere"),
    ("ltng", ":LTNG:entire atmosphere"),
    ("uh25", ":MXUPHL:5000-2000 m above ground"),
    ("tmp700", ":TMP:700 mb"),
    ("dpt700", ":DPT:700 mb"),
    ("tmp500", ":TMP:500 mb"),
]

# Stored variables. Shear u/v are merged into a magnitude so every field is rotation invariant.
NWP_VARS = ["cape_sfc", "cape_mu", "cin_sfc", "lftx", "pwat", "hlcy03", "shear06", "refc", "ltng",
            "uh25", "dd700", "tmp500"]


def _signed_log1p(x):
    return np.sign(x) * np.log1p(np.abs(x))


def derive(fields: dict[str, np.ndarray | None], shape: tuple[int, int]) -> np.ndarray:
    """Raw HRRR fields -> [V, ny, nx] float32 in model-friendly units (NaN where missing)."""
    nan = np.full(shape, np.nan, np.float32)

    def f(name):
        v = fields.get(name)
        return nan if v is None else v.astype(np.float32)

    out = {
        "cape_sfc": np.log1p(np.clip(f("cape_sfc"), 0, None)),
        "cape_mu": np.log1p(np.clip(f("cape_mu"), 0, None)),
        "cin_sfc": -np.log1p(np.clip(-f("cin_sfc"), 0, None)),
        "lftx": f("lftx"),
        "pwat": f("pwat"),
        "hlcy03": _signed_log1p(f("hlcy03")),
        "shear06": np.hypot(f("vucsh06"), f("vvcsh06")),
        "refc": np.clip(f("refc"), -10, 75),
        "ltng": np.log1p(np.clip(f("ltng"), 0, None)),
        "uh25": np.log1p(np.clip(f("uh25"), 0, None)),
        "dd700": f("tmp700") - f("dpt700"),
        "tmp500": f("tmp500"),
    }
    return np.stack([out[v] for v in NWP_VARS]).astype(np.float32)


def fetch_hour(valid_time, save_dir: str | None = None, fields=HRRR_FIELDS):
    """Download the f01 forecast valid at `valid_time`. Returns (fields, lat, lon)."""
    import pandas as pd
    from herbie import Herbie

    valid = pd.Timestamp(valid_time)
    if valid.tzinfo is not None:
        valid = valid.tz_convert(None)
    valid = valid.floor("h")
    kw = {"save_dir": save_dir} if save_dir else {}
    got, lat, lon = {}, None, None
    try:
        # archives only: NOMADS keeps ~2 days, so for 2018-19 it can only waste time or fail
        H = Herbie(valid - pd.Timedelta(hours=LEAD_H), model="hrrr", product="sfc", fxx=LEAD_H,
                   priority=list(SOURCES), verbose=False, **kw)
        if H.grib is None:
            raise FileNotFoundError("not found in any archive")
    except Exception as e:
        print(f"[hrrr] {valid}: {type(e).__name__}: {e}")
        return {name: None for name, _ in fields}, None, None
    for name, search in fields:
        try:
            ds = H.xarray(search, remove_grib=True)
            if isinstance(ds, list):
                ds = ds[0]
            da = ds[list(ds.data_vars)[0]]
            got[name] = np.asarray(da.values, np.float32).squeeze()
            if lat is None:
                lat = np.asarray(ds.latitude.values, np.float64)
                lon = np.asarray(ds.longitude.values, np.float64)
        except Exception as e:  # missing field in this HRRR version, or transient fetch error
            print(f"[hrrr] {valid} {name}: {type(e).__name__}: {e}")
            got[name] = None
    if lon is not None:
        lon = np.where(lon > 180, lon - 360, lon)
    return got, lat, lon


def _xyz(lat, lon):
    la, lo = np.deg2rad(lat), np.deg2rad(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], -1)


class Regridder:
    """Inverse-distance weighting over the k nearest source points (no ESMF dependency)."""

    def __init__(self, src_lat: np.ndarray, src_lon: np.ndarray, k: int = 4):
        from scipy.spatial import cKDTree

        self.shape = src_lat.shape
        self.k = k
        self.tree = cKDTree(_xyz(src_lat.ravel(), src_lon.ravel()))

    def weights(self, lat: np.ndarray, lon: np.ndarray):
        d, i = self.tree.query(_xyz(lat.ravel(), lon.ravel()), k=self.k)
        w = 1.0 / np.maximum(d, 1e-9)
        w /= w.sum(-1, keepdims=True)
        return i, w.astype(np.float32), lat.shape

    @staticmethod
    def apply(field: np.ndarray, wts) -> np.ndarray:
        """field: [..., ny, nx] -> [..., h, w]"""
        i, w, shape = wts
        flat = field.reshape(*field.shape[:-2], -1)
        return (flat[..., i] * w).sum(-1).reshape(*field.shape[:-2], *shape).astype(np.float32)


def valid_hours(times_unix: np.ndarray, extra_h: int = 2) -> np.ndarray:
    """Unix times of the NWP valid hours an event needs: floor(first) .. floor(last) + extra_h."""
    first = int(times_unix.min()) // 3600 * 3600
    last = int(times_unix.max()) // 3600 * 3600 + extra_h * 3600
    return np.arange(first, last + 1, 3600, dtype=np.int64)
