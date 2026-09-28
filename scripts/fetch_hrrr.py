#!/usr/bin/env python
"""Step 2: HRRR NWP for every selected event, regridded to each event's grid.

Tier 1 (default): f01 fields on the 48 x 48 (8 km) grid for every hour the event spans
  -> work/nwp/<YYYYmmddHH>.npz
Tier 2 (--mode ext): longer forecasts (run init = valid - fxx) on the 24 x 24 (16 km) grid, for the
  hourly target windows inside each event and the hour before them
  -> work/nwp/f<fxx>_g24/<YYYYmmddHH>.npz
  Lead hour k (target window (V-1h, V]) uses fxx = k+1 at V and fxx = k at V-1h, both from the run
  initialised at V-(k+1)h: the newest run a forecaster has 1 h after issue time V-k h.
  f01 on the 24 grid is not needed: build_extended.py pools it from the tier-1 cache.

Each (valid hour, fxx) is downloaded once (byte-range subset via Herbie), regridded for every event
that needs it; nothing raw is kept. Re-running skips finished files.

  python scripts/fetch_hrrr.py --inventory "2018-06-01 18:00"      # check the field strings first
  python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --workers 12
  python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --mode ext --fxx 2,3,4,5,6,7
"""

import argparse
import os
import sys
import tempfile
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from nowcast.constants import LR  # noqa: E402
from nowcast.data.hrrr import (HRRR_FIELDS, LEAD_H, Regridder, derive, fetch_hour, nwp_path,  # noqa: E402
                               valid_hours, window_end_hours)
from nowcast.data.sevir import event_grid_latlon, frame_offsets  # noqa: E402

EXT_GRID = 24
_G = {}


def hour_name(h: int) -> str:
    return time.strftime("%Y%m%d%H", time.gmtime(int(h)))


def _init(out_dir, save_dir):
    _G.update(out=out_dir, save=save_dir, regrid=None, wts={})


def _process(job):
    hour, fxx, grid, rows = job
    path = nwp_path(_G["out"], hour, fxx, grid)
    if os.path.exists(path):
        return hour, fxx, "skip", 0.0
    t = time.time()
    fields, lat, lon = fetch_hour(pd.Timestamp(int(hour), unit="s"), save_dir=_G["save"], fxx=fxx)
    if lat is None:
        return hour, fxx, "failed", time.time() - t
    if _G["regrid"] is None:
        _G["regrid"] = Regridder(lat, lon)
    arr = derive(fields, lat.shape)
    out = {}
    for r in rows:
        key = (r["id"], grid)
        w = _G["wts"].get(key)
        if w is None:
            elat, elon = event_grid_latlon(r, grid)
            w = _G["regrid"].weights(elat, elon)
            _G["wts"][key] = w
        out[r["id"]] = Regridder.apply(arr, w).astype(np.float16)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp.npz"
    np.savez(tmp, **out)
    os.replace(tmp, path)
    return hour, fxx, "ok", time.time() - t


def inventory(when: str):
    from herbie import Herbie

    valid = pd.Timestamp(when).floor("h")
    H = Herbie(valid - pd.Timedelta(hours=LEAD_H), model="hrrr", product="sfc", fxx=LEAD_H, verbose=False)
    inv = H.inventory()
    print(f"{len(inv)} GRIB messages in {H.grib}")
    for name, search in HRRR_FIELDS:
        m = inv[inv.search_this.str.contains(search, regex=True)]
        status = "OK " if len(m) == 1 else ("MISSING" if len(m) == 0 else f"{len(m)} MATCHES")
        print(f"{status:10s} {name:10s} {search:35s} {'; '.join(m.search_this.tolist())[:120]}")


def plan_jobs(ev: pd.DataFrame, mode: str, fxx_list: list[int]):
    need = defaultdict(list)  # (hour, fxx, grid) -> rows
    for r in ev.to_dict("records"):
        times = int(pd.Timestamp(r["time_utc"]).timestamp()) + frame_offsets(pd.Series(r))
        if mode == "event":
            for h in valid_hours(times):
                need[(int(h), LEAD_H, LR)].append(r)
        else:
            ends = window_end_hours(times)
            hours = sorted(set(ends.tolist()) | set((ends - 3600).tolist()))
            for h in hours:
                for f in fxx_list:
                    need[(int(h), f, EXT_GRID)].append(r)
    return [(h, f, g, rows) for (h, f, g), rows in sorted(need.items())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="work/events.csv")
    ap.add_argument("--out", default="work/nwp")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--mode", choices=["event", "ext"], default="event")
    ap.add_argument("--fxx", default="2,3,4,5,6,7", help="ext mode: forecast hours (lead hour k needs k and k+1)")
    ap.add_argument("--limit-jobs", type=int)
    ap.add_argument("--inventory", help="print which HRRR_FIELDS match at this valid time, then exit")
    args = ap.parse_args()
    if args.inventory:
        return inventory(args.inventory)

    ev = pd.read_csv(args.events, parse_dates=["time_utc"])
    jobs = plan_jobs(ev, args.mode, [int(f) for f in args.fxx.split(",") if f])
    if args.limit_jobs:
        jobs = jobs[: args.limit_jobs]
    os.makedirs(args.out, exist_ok=True)
    print(f"{len(ev)} events -> {len(jobs)} downloads ({args.mode} mode, "
          f"{sum(len(j[3]) for j in jobs)} event-fields)")

    save_dir = tempfile.mkdtemp(prefix="herbie_")  # Herbie writes subset GRIBs here, removed after read
    t0, done, failed = time.time(), 0, 0
    with Pool(args.workers, initializer=_init, initargs=(args.out, save_dir)) as pool:
        for hour, fxx, status, dt in pool.imap_unordered(_process, jobs):
            done += 1
            failed += status == "failed"
            if status == "failed":
                print(f"FAILED {hour_name(hour)} f{fxx:02d}")
            if done % 25 == 0 or done == len(jobs):
                el = time.time() - t0
                print(f"{done}/{len(jobs)}  failed {failed}  {el / 60:.1f} min  "
                      f"ETA {(len(jobs) - done) * el / done / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
