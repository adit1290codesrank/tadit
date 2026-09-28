"""GFS 0.25 deg (NOAA, open: AWS noaa-gfs-bdp-pds, live on NOMADS) -> the model's NWP variables.

Checked against the real GFS pgrb2.0p25 inventory: CAPE (surface and 255-0 mb), CIN, LFTX, PWAT,
HLCY 0-3 km, REFC, TMP 700/500 mb, RH 700 mb, U/V at 500 mb and 10 m are present.
Not in GFS: LTNG, MXUPHL (-> NaN, which becomes 0 after normalisation; training hides these in
50% of samples so the models expect it), VUCSH/VVCSH (0-6 km shear -> |V500 - V10m|, ~0-5.5 km),
DPT 700 mb (-> from TMP and RH, Magnus formula).

GFS runs every 6 h and is complete ~4 h after the cycle, so a forecast issued at time T uses the
newest cycle at or before T - 4 h, exactly like the HRRR latency rule used in training.
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from ..data.hrrr import Regridder, derive

GFS_FIELDS = [
    ("cape_sfc", ":CAPE:surface"),
    ("cape_mu", ":CAPE:255-0 mb above ground"),
    ("cin_sfc", ":CIN:surface"),
    ("lftx", ":LFTX:surface"),
    ("pwat", ":PWAT:entire atmosphere"),
    ("hlcy03", ":HLCY:3000-0 m above ground"),
    ("refc", ":REFC:entire atmosphere"),
    ("tmp700", ":TMP:700 mb"),
    ("rh700", ":RH:700 mb"),
    ("tmp500", ":TMP:500 mb"),
    ("u500", ":UGRD:500 mb"),
    ("v500", ":VGRD:500 mb"),
    ("u10", ":UGRD:10 m above ground"),
    ("v10", ":VGRD:10 m above ground"),
]
LATENCY_H = 4
REGION = (0.0, 42.0, 60.0, 105.0)  # lat_min, lat_max, lon_min, lon_max: India + margin


def dewpoint_k(t_k: np.ndarray, rh_pct: np.ndarray) -> np.ndarray:
    """Magnus formula over water."""
    t = t_k - 273.15
    g = np.log(np.clip(rh_pct, 1e-3, 100) / 100.0) + 17.625 * t / (243.04 + t)
    return 243.04 * g / (17.625 - g) + 273.15


def to_model_fields(g: dict) -> dict:
    """GFS field dict -> the HRRR-named dict `derive()` expects."""
    def get(k):
        return g.get(k)

    out = {k: get(k) for k in ("cape_sfc", "cape_mu", "cin_sfc", "lftx", "pwat", "hlcy03", "refc",
                               "tmp700", "tmp500")}
    if get("u500") is not None and get("u10") is not None:
        out["vucsh06"] = get("u500") - get("u10")
        out["vvcsh06"] = get("v500") - get("v10")
    if get("tmp700") is not None and get("rh700") is not None:
        out["dpt700"] = dewpoint_k(get("tmp700"), get("rh700"))
    out["ltng"] = out["uh25"] = None
    return out


def cycle_for(issue: dt.datetime, latency_h: int = LATENCY_H) -> dt.datetime:
    t = issue - dt.timedelta(hours=latency_h)
    return t.replace(hour=t.hour // 6 * 6, minute=0, second=0, microsecond=0)


def fetch(valid: dt.datetime, issue: dt.datetime, region=REGION, save_dir: str | None = None):
    """Derived NWP fields [V, ny, nx] valid at `valid` from the newest cycle usable at `issue`,
    cropped to `region`. Returns (fields, lat2d, lon2d, meta) or (None, None, None, meta)."""
    from herbie import Herbie

    init = cycle_for(issue)
    fxx = int(round((valid - init).total_seconds() / 3600))
    meta = {"model": "gfs", "init": init.isoformat(), "fxx": fxx, "valid": valid.isoformat()}
    try:
        kw = {"save_dir": save_dir} if save_dir else {}
        H = Herbie(init, model="gfs", product="pgrb2.0p25", fxx=fxx, priority=["aws", "nomads", "google", "azure"],
                   verbose=False, **kw)
        got, lat, lon = {}, None, None
        for name, search in GFS_FIELDS:
            try:
                ds = H.xarray(search, remove_grib=True)
                ds = ds[0] if isinstance(ds, list) else ds
                if lat is None:
                    la, lo = ds.latitude.values, ds.longitude.values
                    lo = np.where(lo > 180, lo - 360, lo)
                    iy = np.where((la >= region[0]) & (la <= region[1]))[0]
                    ix = np.where((lo >= region[2]) & (lo <= region[3]))[0]
                    lon, lat = np.meshgrid(lo[ix], la[iy])
                da = ds[list(ds.data_vars)[0]].values.squeeze()
                got[name] = np.asarray(da[np.ix_(iy, ix)], np.float32)
            except Exception as e:
                meta.setdefault("missing", []).append(f"{name}: {type(e).__name__}")
        if lat is None:
            raise RuntimeError("no GFS field could be read")
        fields = derive(to_model_fields(got), lat.shape)
        meta["status"] = "ok"
        return fields, lat, lon, meta
    except Exception as e:
        meta.update(status="missing", detail=f"{type(e).__name__}: {e}")
        return None, None, None, meta


def to_tile(fields: np.ndarray, lat: np.ndarray, lon: np.ndarray, tile: dict, n: int) -> np.ndarray:
    from .tiles import tile_grid

    tlat, tlon = tile_grid(tile, n)
    rg = Regridder(lat, lon)
    return Regridder.apply(fields, rg.weights(tlat, tlon)).astype(np.float32)
