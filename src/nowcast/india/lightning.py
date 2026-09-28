"""Indian lightning observations -> the model's lightning channel / verification targets.

Accepts any strike list as CSV with a time column and lat/lon columns, e.g. an export from
IITM's Indian Lightning Location Network (ILLN, data on request), IMD's lightning feed, ENTLN/GLD360
(commercial, IMD subscribes) or ISS-LIS flashes. Binning matches training: frame k counts strikes
in (T_k - 5 min, T_k], so no future lightning leaks into an input frame.
"""

from __future__ import annotations

import numpy as np

from ..constants import FRAME_SECONDS, LR
from .tiles import latlon_to_pixel

TIME_COLS = ("time", "datetime", "timestamp", "time_utc", "date_time")
LAT_COLS = ("lat", "latitude")
LON_COLS = ("lon", "longitude", "long", "lng")


def _col(df, names):
    low = {c.lower(): c for c in df.columns}
    for n in names:
        if n in low:
            return low[n]
    raise KeyError(f"none of {names} in columns {list(df.columns)}")


def read_strikes(path: str):
    """-> DataFrame with columns t (unix seconds, UTC), lat, lon."""
    import pandas as pd

    df = pd.read_csv(path)
    t = pd.to_datetime(df[_col(df, TIME_COLS)], utc=True)
    secs = (t - pd.Timestamp("1970-01-01", tz="UTC")) // pd.Timedelta(seconds=1)  # unit-safe across pandas versions
    return pd.DataFrame({"t": secs.astype("int64"), "lat": df[_col(df, LAT_COLS)].astype(float),
                         "lon": df[_col(df, LON_COLS)].astype(float)})


TAI93_TO_UNIX = 725_846_400 - 10  # 1993-01-01T00:00:00 as unix seconds, minus TAI-UTC drift since 1993


def iss_lis_to_csv(paths: list[str], out_csv: str, bbox=(0.0, 40.0, 60.0, 100.0)) -> int:
    """ISS-LIS science files (NASA GHRC, free Earthdata login; netCDF-4) -> strike CSV over India.

    Uses the flash-level variables lightning_flash_lat / _lon / _TAI93_time. ISS-LIS sees any given
    point for only ~90 s per overpass, so these flashes are good for *verifying* hits, not for
    declaring "no lightning": score only cells and minutes inside the instrument's view time.
    """
    import h5py
    import pandas as pd

    rows = []
    for p in paths:
        with h5py.File(p, "r") as f:
            if "lightning_flash_lat" not in f:
                continue
            lat, lon = f["lightning_flash_lat"][()], f["lightning_flash_lon"][()]
            t = f["lightning_flash_TAI93_time"][()] + TAI93_TO_UNIX
            m = (lat >= bbox[0]) & (lat <= bbox[1]) & (lon >= bbox[2]) & (lon <= bbox[3])
            rows.append(pd.DataFrame({"time": pd.to_datetime(t[m], unit="s", utc=True), "lat": lat[m], "lon": lon[m]}))
    df = pd.concat(rows) if rows else pd.DataFrame(columns=["time", "lat", "lon"])
    df.sort_values("time").to_csv(out_csv, index=False)
    return len(df)


def grid_strikes(strikes, tile: dict, frame_times_unix: np.ndarray, n: int = LR) -> np.ndarray:
    """-> [T, n, n] uint8 strike counts on the tile grid."""
    ft = np.asarray(frame_times_unix, np.int64)
    out = np.zeros((len(ft), n, n), np.int32)
    s = strikes[(strikes.t > ft.min() - FRAME_SECONDS) & (strikes.t <= ft.max())]
    if len(s):
        row, col = latlon_to_pixel(tile, s.lat.to_numpy(), s.lon.to_numpy(), n)
        r, c = np.floor(row).astype(int), np.floor(col).astype(int)
        k = np.searchsorted(ft, s.t.to_numpy(), side="left")
        ok = (r >= 0) & (r < n) & (c >= 0) & (c < n) & (k < len(ft))
        np.add.at(out, (k[ok], r[ok], c[ok]), 1)
    return np.minimum(out, 255).astype(np.uint8)
