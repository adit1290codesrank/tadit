#!/usr/bin/env python
"""Storm-location check of an India run against GK2A cloud tops observed after issue time.

This is a proxy, not lightning verification: a 16 km cell counts as "deep convection" in lead hour k
if any GK2A IR 10.5 um scan in that hour is colder than -52 C. The forecast is taken as "yes" where
the tier-1 hourly probability is >= 0.4. Writes results/india/<case>_gk2a_check.json.

  python scripts/check_india_gk2a.py --city Bhubaneswar --time 2023-09-02T08:00
"""

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

from nowcast.india.gk2a import BUCKET, read_tile  # noqa: E402
from nowcast.india.tiles import CITIES, city_tile, latlon_to_pixel, tile_grid  # noqa: E402

COLD_C = -52.0
P_YES = 0.4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", required=True, choices=sorted(CITIES))
    ap.add_argument("--time", required=True, help="issue time of the India run, UTC")
    ap.add_argument("--results", default="results/india")
    ap.add_argument("--cache", default="data/gk2a_verify")
    args = ap.parse_args()

    t0 = dt.datetime.fromisoformat(args.time)
    stem = os.path.join(args.results, f"{args.city}_{t0:%Y%m%dT%H%M}")
    z = np.load(stem + ".npz")
    os.makedirs(args.cache, exist_ok=True)
    tile, n = city_tile(args.city), 192
    lat0, lon0 = CITIES[args.city]
    r, c = map(int, latlon_to_pixel(tile, lat0, lon0, n))
    lat, lon = tile_grid(tile, n)
    dist = np.hypot((lat - lat0) * 111, (lon - lon0) * 111 * np.cos(np.deg2rad(lat0)))
    cold = {h: np.zeros((24, 24), bool) for h in (1, 2, 3)}
    city_min = {h: np.inf for h in (1, 2, 3)}
    for m in range(20, 181, 20):  # scans every 20 min over the 3 h after issue
        t = t0 + dt.timedelta(minutes=m)
        name = f"gk2a_ami_le1b_ir105_fd020ge_{t:%Y%m%d%H%M}.nc"
        dst = os.path.join(args.cache, name)
        if not os.path.exists(dst):
            try:
                urllib.request.urlretrieve(f"{BUCKET}/AMI/L1B/FD/{t:%Y%m/%d/%H}/{name}", dst + ".part")
                os.replace(dst + ".part", dst)
            except Exception as e:
                print(f"missing scan {t:%H:%M}: {e}")
                continue
        bt = read_tile(dst, 10.5, tile, n) - 273.15
        h = min(3, int(np.ceil(m / 60)))
        cold[h] |= (bt < COLD_C).reshape(24, 8, 24, 8).any(axis=(1, 3))
        city_min[h] = min(city_min[h], float(np.nanmin(np.where(dist <= 16, bt, np.nan))))

    rc, cc = map(int, latlon_to_pixel(tile, lat0, lon0, 24))
    rows = []
    print(f"{args.city} {args.time} UTC")
    print(" hr | P city | coldest top <=16 km | deep-conv cells | fc cells | POD  | FAR  | CSI")
    for h in (1, 2, 3):
        key = f"tier1_hour{h}_16km"
        if key not in z.files:
            continue
        p, obs = z[key], cold[h]
        fc = p >= P_YES
        hit, miss, fa = int((fc & obs).sum()), int((~fc & obs).sum()), int((fc & ~obs).sum())
        pod = hit / (hit + miss) if hit + miss else float("nan")
        far = fa / (hit + fa) if hit + fa else float("nan")
        csi = hit / (hit + miss + fa) if hit + miss + fa else float("nan")
        rows.append(dict(hour=h, p_city=round(float(p[rc, cc]), 3), coldest_city_c=round(city_min[h], 1),
                         deep_cells=int(obs.sum()), fc_cells=int(fc.sum()), hits=hit, pod=pod, far=far, csi=csi))
        print(f"  {h} |  {p[rc, cc]:.2f}  |      {city_min[h]:6.1f} C       |    {obs.sum():4d}         | "
              f"{fc.sum():4d}     | {pod:.2f} | {far:.2f} | {csi:.2f}")
    json.dump({"city": args.city, "issue_utc": args.time,
               "proxy": f"storm-location check: GK2A IR10.5 < {COLD_C:g} C in 16 km cells vs tier-1 P >= {P_YES}; "
                        "not lightning verification", "hours": rows},
              open(stem + "_gk2a_check.json", "w"), indent=1)


if __name__ == "__main__":
    main()
