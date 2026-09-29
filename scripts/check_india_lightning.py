#!/usr/bin/env python
"""Verify India runs against observed lightning (any strike list: FY-4A LMI, ILDN, Kaggle, ISS-LIS CSV).

For each run in --results and each lead hour k, a 16 km cell is "observed yes" if any strike falls in it
during (issue + (k-1) h, issue + k h]. The forecast is the seamless product (tier 1 up to the switch hour,
tier 2 after), "yes" where P >= a threshold. Scores: POD / FAR / CSI per threshold, Brier score, and
strikes within 16 km of the city. Baseline: persistence = cells with a strike in the 15 min before issue,
forecast for every hour. Writes <run>_ltg_check.json next to each run.

Hours with no strikes anywhere in the wider region (the tile +/- 3 deg) are reported as "no data":
a gap in the lightning record must not be scored as "no lightning".

  python scripts/check_india_lightning.py --strikes data/fy4a_lmi/*.csv --source "FY-4A LMI" \
      --results results/india_insat
"""

import argparse
import datetime as dt
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from nowcast.india.lightning import read_strikes  # noqa: E402
from nowcast.india.tiles import CITIES, city_tile, latlon_to_pixel, tile_grid  # noqa: E402

THRESHOLDS = (0.2, 0.3, 0.4, 0.5)
N = 24  # 16 km cells on the 384 km tile


def _scores(p, obs):
    out = {}
    for t in THRESHOLDS:
        fc = p >= t
        hit, miss, fa = int((fc & obs).sum()), int((~fc & obs).sum()), int((fc & ~obs).sum())
        out[str(t)] = {"pod": hit / (hit + miss) if hit + miss else None,
                       "far": fa / (hit + fa) if hit + fa else None,
                       "csi": hit / (hit + miss + fa) if hit + miss + fa else None}
    return out


def _in_tile(tile, w):
    rr, cc = latlon_to_pixel(tile, w.lat.to_numpy(), w.lon.to_numpy(), N)
    return (rr >= 0) & (rr < N) & (cc >= 0) & (cc < N)


def _cells(tile, w):
    """[N, N] bool: 16 km cells with at least one strike."""
    obs = np.zeros((N, N), bool)
    if len(w):
        rr, cc = latlon_to_pixel(tile, w.lat.to_numpy(), w.lon.to_numpy(), N)
        rr, cc = np.floor(rr).astype(int), np.floor(cc).astype(int)
        ok = (rr >= 0) & (rr < N) & (cc >= 0) & (cc < N)
        obs[rr[ok], cc[ok]] = True
    return obs


def check_run(json_path, strikes, source):
    r = json.load(open(json_path))
    z = np.load(json_path[:-5] + ".npz")
    prov = r["provenance"]
    city = prov["tile"]["id"]
    t0 = dt.datetime.fromisoformat(prov["issue_time_utc"])
    tile = city_tile(city)
    lat0, lon0 = CITIES[city]
    lat, lon = tile_grid(tile, N)
    t0u = int(t0.replace(tzinfo=dt.timezone.utc).timestamp())
    near = strikes[(strikes.lat.between(lat.min() - 3, lat.max() + 3)) & (strikes.lon.between(lon.min() - 3, lon.max() + 3))]
    src = {s["lead_hour"]: s["source"] for s in r["summary"]}
    before = near[(near.t > t0u - 900) & (near.t <= t0u)]
    pers = _cells(tile, before)
    rows = []
    for h in sorted(src):
        key = f"{src[h]}_hour{h}_16km"
        if key not in z.files:
            continue
        p = z[key].astype(np.float32)
        w = near[(near.t > t0u + (h - 1) * 3600) & (near.t <= t0u + h * 3600)]
        row = {"hour": h, "source": src[h], "strikes_region": len(w)}
        if len(w) == 0:
            row["status"] = "no data"  # no strikes anywhere nearby: a record gap or a truly calm hour
            rows.append(row)
            continue
        obs = _cells(tile, w)
        ok = _in_tile(tile, w)
        d = np.hypot((w.lat.to_numpy() - lat0) * 111, (w.lon.to_numpy() - lon0) * 111 * np.cos(np.deg2rad(lat0)))
        pr, pc = map(int, latlon_to_pixel(tile, lat0, lon0, N))
        row.update(status="scored", strikes_tile=int(ok.sum()), cells_observed=int(obs.sum()),
                   strikes_within_16km=int((d <= 16).sum()), p_city=round(float(p[pr, pc]), 3),
                   p_max=round(float(p.max()), 3), brier=round(float(((p - obs) ** 2).mean()), 4),
                   scores=_scores(p, obs),
                   persistence_csi=_scores(pers.astype(np.float32), obs)["0.5"]["csi"])
        rows.append(row)
    out = {"city": city, "issue_utc": prov["issue_time_utc"], "source": source,
           "what": "Forecast vs observed lightning: any strike in a 16 km cell during the lead hour", "hours": rows}
    with open(json_path[:-5] + "_ltg_check.json", "w") as f:
        json.dump(out, f, indent=1)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strikes", nargs="+", required=True, help="CSV strike lists with time, lat, lon columns")
    ap.add_argument("--source", required=True, help="name of the lightning record, e.g. 'FY-4A LMI'")
    ap.add_argument("--results", default="results/india")
    args = ap.parse_args()

    strikes = pd.concat([read_strikes(p) for p in args.strikes], ignore_index=True)
    print(f"{len(strikes):,} strikes from {len(args.strikes)} file(s), "
          f"{pd.to_datetime(strikes.t.min(), unit='s')} .. {pd.to_datetime(strikes.t.max(), unit='s')} UTC")
    for p in sorted(glob.glob(os.path.join(args.results, "*.json"))):
        if p.endswith("_check.json") or not os.path.exists(p[:-5] + ".npz"):
            continue
        c = check_run(p, strikes, args.source)
        print(f"\n{Path(p).stem}  ({args.source})")
        print(" hr | P city | strikes <=16 km | cells obs | CSI@0.2  CSI@0.3  CSI@0.4 | persistence CSI | Brier")
        for h in c["hours"]:
            if h["status"] != "scored":
                print(f"  {h['hour']} | no lightning recorded in the region this hour")
                continue
            s = h["scores"]
            f = lambda t: "  -  " if s[t]["csi"] is None else f"{s[t]['csi']:.2f}"
            print(f"  {h['hour']} |  {h['p_city']:.2f}  |      {h['strikes_within_16km']:6d}     |   {h['cells_observed']:4d}   |"
                  f"  {f('0.2')}    {f('0.3')}    {f('0.4')}   |      "
                  f"{'  -  ' if h['persistence_csi'] is None else format(h['persistence_csi'], '.2f')}       | {h['brier']:.3f}")


if __name__ == "__main__":
    main()
