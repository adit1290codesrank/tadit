#!/usr/bin/env python
"""ISRO DWR volume scan (CfRadial NetCDF-3, e.g. MOSDAC RSCHR_*_L2B_STD.nc) -> column-max reflectivity (.npz)
that `nowcast.india.run --radar-npz` reads (dbz, lat, lon).

MAX-Z = the highest reflectivity in the column: the maximum over all elevation sweeps for each 1 deg azimuth
x range gate, placed on the ground at range * cos(lowest elevation) from the radar (azimuthal equidistant).
Notes on these files, checked on RSCHR_01APR2021_*:
  - DBZ is stored as raw counts: dBZ = raw * 0.5 - 32, raw 0 = no echo.
  - sweep_start/end_ray_index are unreliable, so rays are grouped by their own elevation angle.
  - the time units are a literal "yyyy-mm-dd" placeholder, so the scan time comes from the file name.
Ground clutter around the hilltop site (first 5 km) and echoes below 18 dBZ (speckle, clear-air returns)
are masked; they add almost nothing to VIL.

  python scripts/cfradial_to_maxz.py data/radar/RSCHR_01APR2021_175606_L2B_STD.nc --out data/radar/maxz_20210401T1756.npz
"""

import argparse
import datetime as dt
import re
import warnings
from pathlib import Path

import numpy as np
import pyproj
from scipy.io import netcdf_file

CLUTTER_M = 5000.0
MIN_DBZ = 18.0


def scan_time(path: str) -> dt.datetime:
    m = re.search(r"_(\d{2}[A-Z]{3}\d{4})_(\d{6})_", Path(path).name)
    return dt.datetime.strptime(m.group(1).title() + m.group(2), "%d%b%Y%H%M%S")


def maxz(path: str):
    f = netcdf_file(path, "r", mmap=False, maskandscale=False)
    v = f.variables
    raw = v["DBZ"].data.astype(np.float32)
    dbz = np.where(raw > 0, raw * 0.5 - 32.0, np.nan)
    az = np.mod(np.round(v["azimuth"].data.astype(float)).astype(int), 360)
    el = v["elevation"].data.astype(float)
    rng = v["range"].data.astype(float)
    lat0, lon0 = float(v["latitude"].data), float(v["longitude"].data)
    f.close()

    grid = np.full((360, rng.size), np.nan, np.float32)
    for a in range(360):
        rays = dbz[az == a]
        if len(rays):
            with warnings.catch_warnings():  # all-NaN columns (no echo) are expected
                warnings.simplefilter("ignore", RuntimeWarning)
                grid[a] = np.nanmax(rays, axis=0)
    ground = rng * np.cos(np.deg2rad(np.nanmin(el)))
    grid[:, ground < CLUTTER_M] = np.nan
    grid[grid < MIN_DBZ] = np.nan
    A, R = np.meshgrid(np.deg2rad(np.arange(360)), ground, indexing="ij")
    p = pyproj.Proj(f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +units=m")
    lon, lat = p(R * np.sin(A), R * np.cos(A), inverse=True)
    return grid, lat.astype(np.float32), lon.astype(np.float32), (lat0, lon0), sorted(set(np.round(el, 1)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("volume", help="CfRadial volume file (the full 10-sweep scan)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--source", default="ISRO DWR Cherrapunji (MOSDAC RSCHR_L2B_STD)")
    args = ap.parse_args()

    dbz, lat, lon, site, sweeps = maxz(args.volume)
    t = scan_time(args.volume)
    np.savez_compressed(args.out, dbz=dbz, lat=lat, lon=lon, time_utc=t.isoformat(), source=args.source)
    ok = np.isfinite(dbz)
    print(f"{Path(args.volume).name}: scan {t:%Y-%m-%d %H:%M:%S} UTC, radar {site[0]:.3f}N {site[1]:.3f}E, "
          f"{len(sweeps)} elevations {sweeps[0]}..{sweeps[-1]} deg, echo in {ok.mean():.1%} of cells, "
          f"max {np.nanmax(dbz):.1f} dBZ, >=35 dBZ in {np.nanmean(dbz >= 35) if ok.any() else 0:.2%} -> {args.out}")


if __name__ == "__main__":
    main()
