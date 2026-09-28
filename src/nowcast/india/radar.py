"""IMD Doppler Weather Radar reflectivity (dBZ) -> the model's radar channel (SEVIR digital VIL).

IMD distributes composite products (e.g. MAX-Z) as images on mausam.imd.gov.in and volume data on
request. Whatever the source, pass a dBZ field with its lat/lon here. The model's radar channel is
Vertically Integrated Liquid; from a 2-D composite we can only approximate it:
  VIL [kg/m^2] = 3.44e-6 * Z^(4/7) * depth   (Greene & Clark 1972, uniform column of `depth` m)
then SEVIR's digital scale (inverse of X<=5: 0; X<=18: (X-2)/90.66; else exp((X-83.9)/38.9)).
The approximation is flagged in the provenance so the dashboard can say so.
"""

from __future__ import annotations

import numpy as np

from ..constants import HR
from ..data.hrrr import Regridder
from .tiles import tile_grid


def vil_kgm2_from_dbz(dbz: np.ndarray, depth_km: float = 6.0) -> np.ndarray:
    z = 10.0 ** (np.nan_to_num(dbz, nan=-30.0) / 10.0)
    return 3.44e-6 * z ** (4.0 / 7.0) * depth_km * 1000.0


def vil_digital(vil: np.ndarray) -> np.ndarray:
    v = np.asarray(vil, np.float64)
    x = np.where(v <= (18 - 2) / 90.66, v * 90.66 + 2, 38.9 * np.log(np.maximum(v, 1e-9)) + 83.9)
    x = np.where(x < 5, 0, x)
    return np.clip(np.round(x), 0, 254).astype(np.uint8)


def vil_kgm2_from_digital(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, np.float64)
    return np.where(x <= 5, 0.0, np.where(x <= 18, (x - 2) / 90.66, np.exp((x - 83.9) / 38.9)))


def dbz_to_tile(dbz: np.ndarray, lat: np.ndarray, lon: np.ndarray, tile: dict, n: int = HR,
                depth_km: float = 6.0) -> np.ndarray:
    """dBZ on any lat/lon grid (NaN = no coverage) -> [n, n] uint8 digital VIL on the tile."""
    tlat, tlon = tile_grid(tile, n)
    m = np.isfinite(lat) & np.isfinite(lon)
    rg = Regridder(lat[m], lon[m], k=4)
    d = Regridder.apply(np.nan_to_num(dbz[m], nan=-30.0)[None, None, :], rg.weights(tlat, tlon))[0]
    return vil_digital(vil_kgm2_from_dbz(d, depth_km))
