"""SEVIR access and per-event preprocessing.

SEVIR layout (s3://sevir, anonymous):
  CATALOG.csv                               one row per (event id, image type)
  data/<img_type>/<year>/SEVIR_*.h5         vil/ir069/ir107: dataset[img_type][file_index] -> (H, W, 49)
                                            lght: dataset[event_id] -> (N, 5) flashes
Lightning columns follow the SEVIR tutorial: [t (s rel. to time_utc), lat, lon, x, y].
"""

from __future__ import annotations

import numpy as np

from ..constants import (
    DEFAULT_FRAME_OFFSETS_S,
    FRAME_SECONDS,
    HR,
    IR_CHANNELS,
    IR_RANGE_C,
    LR,
)

SEVIR_ROOT = "s3://sevir"
CATALOG_URI = f"{SEVIR_ROOT}/CATALOG.csv"
DATA_URI = f"{SEVIR_ROOT}/data"
TYPES = ("vil",) + IR_CHANNELS + ("lght",)

# Earthformer's SEVIR split, so metrics are comparable with published numbers.
SPLITS = {
    "train": (None, "2019-01-01"),
    "val": ("2019-01-01", "2019-06-01"),
    "test": ("2019-06-01", None),
}

# Whether image row 0 is the northern edge. It is NOT: SEVIR arrays are stored south-up.
# Measured with scripts/check_alignment.py on 7 real storm events (VIL vs HRRR REFC):
# corr +0.43 with row 0 = south vs -0.08 with row 0 = north, same sign on every event.
# The same run confirmed lightning x/y are 48-grid pixels in image row order (no flip).
ROW0_NORTH = False


# ----------------------------------------------------------------------------- catalog

def load_catalog(path: str = CATALOG_URI):
    import pandas as pd

    storage = {"anon": True} if path.startswith("s3://") else None
    return pd.read_csv(path, parse_dates=["time_utc"], low_memory=False, storage_options=storage)


def complete_events(cat, types=TYPES):
    """One row per event id that has every image type in `types`.

    Adds file_<type> / index_<type> columns; geometry and time come from the vil row.
    """
    sub = cat[cat.img_type.isin(types)].drop_duplicates(["id", "img_type"])
    n = sub.groupby("id").img_type.nunique()
    sub = sub[sub.id.isin(n[n == len(types)].index)]
    geo_cols = ["time_utc", "episode_id", "event_id", "event_type", "llcrnrlat", "llcrnrlon",
                "urcrnrlat", "urcrnrlon", "proj", "minute_offsets"]
    geo_cols = [c for c in geo_cols if c in sub.columns]
    ev = sub[sub.img_type == "vil"].set_index("id")[geo_cols].copy()
    wide = sub.set_index(["id", "img_type"])[["file_name", "file_index"]].unstack("img_type")
    for t in types:
        ev[f"file_{t}"] = wide[("file_name", t)]
        ev[f"index_{t}"] = wide[("file_index", t)].astype("int64")
    ev.index.name = "id"
    return ev.reset_index().sort_values("time_utc").reset_index(drop=True)


def split_mask(ev, split: str):
    import pandas as pd

    lo, hi = SPLITS[split]
    t = pd.to_datetime(ev.time_utc)
    m = np.ones(len(ev), bool)
    if lo:
        m &= (t >= pd.Timestamp(lo)).to_numpy()
    if hi:
        m &= (t < pd.Timestamp(hi)).to_numpy()
    return m


def select_events(ev, n: int, storm_frac: float = 0.8, seed: int = 0):
    """~storm_frac storm events (ids 'S...') + random/null events ('R...') for negatives."""
    rng = np.random.default_rng(seed)
    storm = ev[ev.id.str.startswith("S")]
    rand = ev[~ev.id.str.startswith("S")]
    n_s = min(len(storm), int(round(n * storm_frac)))
    n_r = min(len(rand), n - n_s)
    pick = [storm.iloc[rng.permutation(len(storm))[:n_s]], rand.iloc[rng.permutation(len(rand))[:n_r]]]
    import pandas as pd

    return pd.concat(pick).sort_values(["file_vil", "index_vil"]).reset_index(drop=True)


def frame_offsets(row) -> np.ndarray:
    """Frame offsets (s) relative to time_utc.

    In the real catalog ~10% of events sit on a shifted 5-min grid (e.g. -118..+122), and ~80 rows
    contain typos ("...:-40:-40:-30:..." or "...:25:27:35:..."). A clean 5-min sequence is used as
    is; a 49-entry row spanning exactly 240 min is repaired from its first value; anything else
    falls back to the standard -120..+120 min grid.
    """
    s = row.get("minute_offsets") if hasattr(row, "get") else None
    if isinstance(s, str) and s:
        try:
            m = np.array([int(float(v)) for v in s.split(":")])
        except ValueError:
            m = np.array([])
        if len(m) > 1 and np.all(np.diff(m) == 5):
            return m * 60
        if len(m) == len(DEFAULT_FRAME_OFFSETS_S) and m[-1] - m[0] == 240:
            return (m[0] + 5 * np.arange(len(m))) * 60
    return DEFAULT_FRAME_OFFSETS_S.copy()


# ----------------------------------------------------------------------------- geometry

def event_grid_latlon(row, n: int, row0_north: bool | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Lat/lon of cell centres of an n x n grid covering the event patch."""
    import pyproj

    row0_north = ROW0_NORTH if row0_north is None else row0_north
    proj = pyproj.Proj(row["proj"])
    x0, y0 = proj(row["llcrnrlon"], row["llcrnrlat"])
    x1, y1 = proj(row["urcrnrlon"], row["urcrnrlat"])
    xs = x0 + (x1 - x0) * (np.arange(n) + 0.5) / n
    ys = y0 + (y1 - y0) * (np.arange(n) + 0.5) / n
    if row0_north:
        ys = ys[::-1]
    xx, yy = np.meshgrid(xs, ys)
    lon, lat = proj(xx, yy, inverse=True)
    return lat, lon


# ----------------------------------------------------------------------------- conversions

def pool2d_mean(x: np.ndarray, f: int) -> np.ndarray:
    *lead, h, w = x.shape
    return x.reshape(*lead, h // f, f, w // f, f).mean(axis=(-3, -1))


def ir_to_celsius(raw: np.ndarray) -> np.ndarray:
    """SEVIR IR is int16. Detect its unit instead of trusting a hard-coded scale:
    |x| > 400 can only be deg C x 100; a median > 150 can only be Kelvin."""
    x = raw.astype(np.float32)
    if np.nanmax(np.abs(x)) > 400:
        return x * 0.01
    if np.nanmedian(x) > 150:
        return x - 273.15
    return x


def quantize_ir(celsius: np.ndarray, channel: str) -> np.ndarray:
    lo, hi = IR_RANGE_C[channel]
    q = (np.clip(celsius, lo, hi) - lo) / (hi - lo) * 255.0
    return np.nan_to_num(np.round(q), nan=255).astype(np.uint8)  # NaN (no data) -> warmest


def dequantize_ir(q: np.ndarray, channel: str) -> np.ndarray:
    lo, hi = IR_RANGE_C[channel]
    return q.astype(np.float32) / 255.0 * (hi - lo) + lo


def lightning_to_grid(
    flashes: np.ndarray,
    offsets_s: np.ndarray,
    size: int = LR,
    xy_units: int = LR,
    time_origin_s: float = 0.0,
) -> np.ndarray:
    """Flash list -> [T, size, size] uint8 counts.

    Frame k counts flashes in (T_k - 5 min, T_k]: only lightning that has already happened at
    frame time. (The SEVIR tutorial's `lght_to_grid` bins [T_k, T_k+5 min), which would leak
    up to 5 minutes of future lightning into the last input frame.)

    xy_units: size of the grid the x/y columns are expressed in (48 per the SEVIR tutorial;
    set 384 if check_alignment.py says they are VIL pixels).
    """
    T = len(offsets_s)
    out = np.zeros((T, size, size), np.int32)
    if flashes is None or len(flashes) == 0:
        return out.astype(np.uint8)
    f = np.asarray(flashes, np.float64)
    t = f[:, 0] - time_origin_s
    if np.nanmax(np.abs(t)) > 1e8:  # absolute unix seconds; caller must pass time_origin_s
        raise ValueError("lightning times look absolute; pass time_origin_s=event unix time")
    scale = size / xy_units
    x = np.floor(f[:, 3] * scale).astype(np.int64)
    y = np.floor(f[:, 4] * scale).astype(np.int64)
    k = np.searchsorted(offsets_s, t, side="left")
    ok = (k < T) & (x >= 0) & (x < size) & (y >= 0) & (y < size)
    ok &= t > offsets_s[np.minimum(k, T - 1)] - FRAME_SECONDS
    np.add.at(out, (k[ok], y[ok], x[ok]), 1)
    return np.minimum(out, 255).astype(np.uint8)


# ----------------------------------------------------------------------------- reading

class SevirReader:
    """Reads single events from local files or straight from S3 (no raw copy on disk).

    Create one per process: h5py/s3fs handles must not cross a fork.
    """

    def __init__(self, root: str = DATA_URI, block_size: int = 16 * 2**20):
        self.root = root.rstrip("/")
        self._files = {}
        self._fs = None
        if self.root.startswith("s3://"):
            import s3fs

            self._fs = s3fs.S3FileSystem(anon=True, default_block_size=block_size)

    def _h5(self, file_name: str):
        import h5py

        f = self._files.get(file_name)
        if f is None:
            path = f"{self.root}/{file_name}"
            fobj = self._fs.open(path, "rb", cache_type="readahead") if self._fs else path
            f = h5py.File(fobj, "r")
            self._files[file_name] = f
        return f

    def read(self, img_type: str, file_name: str, file_index: int, event_id: str) -> np.ndarray:
        f = self._h5(file_name)
        if img_type == "lght":
            return f[event_id][:] if event_id in f else np.zeros((0, 5), np.float32)
        return f[img_type][int(file_index)]

    def close(self) -> None:
        for f in self._files.values():
            f.close()
        self._files = {}


def event_arrays(reader: SevirReader, row, lght_xy_units: int = LR) -> dict[str, np.ndarray]:
    """One SEVIR event -> the arrays stored in a shard (NWP is attached later)."""
    import pandas as pd

    eid = row["id"]
    offsets = frame_offsets(row)
    t_event = int(pd.Timestamp(row["time_utc"]).timestamp())

    vil = reader.read("vil", row["file_vil"], row["index_vil"], eid)  # (384, 384, 49) uint8
    vil = np.moveaxis(vil, -1, 0).astype(np.float32)
    f = vil.shape[-1] // HR
    vil = np.round(pool2d_mean(vil, f)).clip(0, 255).astype(np.uint8) if f > 1 else vil.astype(np.uint8)

    irs = []
    for ch in IR_CHANNELS:
        raw = np.moveaxis(reader.read(ch, row[f"file_{ch}"], row[f"index_{ch}"], eid), -1, 0)
        c = ir_to_celsius(raw)
        g = c.shape[-1] // HR
        if g > 1:
            c = pool2d_mean(c, g)
        irs.append(quantize_ir(c, ch))
    ir = np.stack(irs, axis=1)  # (49, 2, 192, 192)

    flashes = reader.read("lght", row["file_lght"], row["index_lght"], eid)
    lght = lightning_to_grid(flashes, offsets, LR, xy_units=lght_xy_units)

    lat, lon = event_grid_latlon(row, 2)
    return {
        "vil": vil,
        "ir": ir,
        "lght": lght,
        "times": (t_event + offsets).astype(np.int64),
        "center_lat": np.float32(lat.mean()),
        "center_lon": np.float32(lon.mean()),
    }
