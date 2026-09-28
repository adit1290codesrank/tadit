#!/usr/bin/env python
"""Step 2: HRRR NWP for every selected event, regridded to each event's 48 x 48 grid.

Each unique valid hour is downloaded once (byte-range subset via Herbie), regridded for every
event that needs it, and written to work/nwp/<YYYYmmddHH>.npz ({event_id: [V, 48, 48] fp16}).
Nothing raw is kept. Re-running skips finished hours.

  python scripts/fetch_hrrr.py --inventory "2018-06-01 18:00"      # check the field strings first
  python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --workers 12
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
from nowcast.data.hrrr import HRRR_FIELDS, LEAD_H, Regridder, derive, fetch_hour, valid_hours  # noqa: E402
from nowcast.data.sevir import event_grid_latlon, frame_offsets  # noqa: E402

_G = {}


def hour_name(h: int) -> str:
    return time.strftime("%Y%m%d%H", time.gmtime(int(h)))


def _init(out_dir, save_dir):
    _G.update(out=out_dir, save=save_dir, regrid=None, wts={})


def _process(job):
    hour, rows = job
    path = os.path.join(_G["out"], hour_name(hour) + ".npz")
    if os.path.exists(path):
        return hour, "skip", 0.0
    t = time.time()
    fields, lat, lon = fetch_hour(pd.Timestamp(int(hour), unit="s"), save_dir=_G["save"])
    if lat is None:
        return hour, "failed", time.time() - t
    if _G["regrid"] is None:
        _G["regrid"] = Regridder(lat, lon)
    arr = derive(fields, lat.shape)
    out = {}
    for r in rows:
        w = _G["wts"].get(r["id"])
        if w is None:
            elat, elon = event_grid_latlon(r, LR)
            w = _G["regrid"].weights(elat, elon)
            _G["wts"][r["id"]] = w
        out[r["id"]] = Regridder.apply(arr, w).astype(np.float16)
    tmp = path + ".tmp.npz"
    np.savez(tmp, **out)
    os.replace(tmp, path)
    return hour, "ok", time.time() - t


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="work/events.csv")
    ap.add_argument("--out", default="work/nwp")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--limit-hours", type=int)
    ap.add_argument("--inventory", help="print which HRRR_FIELDS match at this valid time, then exit")
    args = ap.parse_args()
    if args.inventory:
        return inventory(args.inventory)

    ev = pd.read_csv(args.events, parse_dates=["time_utc"])
    need = defaultdict(list)
    for r in ev.to_dict("records"):
        times = int(pd.Timestamp(r["time_utc"]).timestamp()) + frame_offsets(pd.Series(r))
        for h in valid_hours(times):
            need[int(h)].append(r)
    jobs = sorted(need.items())
    if args.limit_hours:
        jobs = jobs[: args.limit_hours]
    os.makedirs(args.out, exist_ok=True)
    print(f"{len(ev)} events -> {len(jobs)} unique valid hours ({sum(len(v) for _, v in jobs)} event-hours)")

    save_dir = tempfile.mkdtemp(prefix="herbie_")  # Herbie writes subset GRIBs here, removed after read
    t0, done, failed = time.time(), 0, 0
    with Pool(args.workers, initializer=_init, initargs=(args.out, save_dir)) as pool:
        for hour, status, dt in pool.imap_unordered(_process, jobs):
            done += 1
            failed += status == "failed"
            if status == "failed":
                print(f"FAILED {hour_name(hour)}")
            if done % 25 == 0 or done == len(jobs):
                el = time.time() - t0
                print(f"{done}/{len(jobs)} hours  failed {failed}  {el / 60:.1f} min  "
                      f"ETA {(len(jobs) - done) * el / done / 60:.1f} min", flush=True)


if __name__ == "__main__":
    main()
