#!/usr/bin/env python
"""Step 3: SEVIR events (+ HRRR from step 2) -> compressed shards per split.

Reads SEVIR straight from S3 by default (h5py over s3fs), so no raw files land on disk.
Train is built first; its NWP mean/std are written to every split's nwp_stats.json.

  python scripts/build_shards.py --events work/events.csv --nwp work/nwp --out shards --workers 12
  python scripts/build_shards.py ... --splits train --limit 100      # measure size/speed first
"""

import argparse
import os
import sys
import time
from collections import OrderedDict
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from nowcast.data.hrrr import NWP_VARS, valid_hours  # noqa: E402
from nowcast.data.sevir import DATA_URI, SevirReader, event_arrays  # noqa: E402
from nowcast.data.shards import RunningStats, ShardWriter, write_stats  # noqa: E402

_G = {}


def _init(root, xy_units):
    _G.update(reader=SevirReader(root), xy=xy_units)


def _process(row):
    try:
        return row["id"], event_arrays(_G["reader"], row, _G["xy"]), None
    except Exception as e:  # corrupt/missing event: skip it, report it
        return row["id"], None, f"{type(e).__name__}: {e}"


class NWPHours:
    def __init__(self, root: str, max_open: int = 64):
        self.root, self.max_open = root, max_open
        self.cache: OrderedDict = OrderedDict()

    def get(self, hour: int):
        f = self.cache.get(hour)
        if f is None:
            path = os.path.join(self.root, time.strftime("%Y%m%d%H", time.gmtime(int(hour))) + ".npz")
            f = np.load(path) if os.path.exists(path) else {}
            self.cache[hour] = f
            if len(self.cache) > self.max_open:
                self.cache.popitem(last=False)
        self.cache.move_to_end(hour)
        return f

    def attach(self, eid: str, a: dict) -> None:
        hours = valid_hours(a["times"])
        lr = a["lght"].shape[-1]
        nwp = np.full((len(hours), len(NWP_VARS), lr, lr), np.nan, np.float16)
        ok = np.zeros(len(hours), bool)
        for j, h in enumerate(hours):
            f = self.get(int(h))
            if eid in getattr(f, "files", f):
                nwp[j] = f[eid]
                ok[j] = bool(np.isfinite(nwp[j]).any())
        a.update(nwp=nwp, nwp_t0=np.int64(hours[0]), nwp_ok=ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="work/events.csv")
    ap.add_argument("--nwp", help="dir from fetch_hrrr.py (omit to build without NWP)")
    ap.add_argument("--sevir-root", default=DATA_URI, help="s3://sevir/data or a local mirror")
    ap.add_argument("--out", default="shards")
    ap.add_argument("--splits", default="train,val,test")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--events-per-shard", type=int, default=256)
    ap.add_argument("--level", type=int, default=3)
    ap.add_argument("--lght-xy-units", type=int, default=48, help="48 or 384; see check_alignment.py")
    ap.add_argument("--limit", type=int)
    args = ap.parse_args()

    ev = pd.read_csv(args.events, parse_dates=["time_utc"])
    nwp = NWPHours(args.nwp) if args.nwp else None
    train_stats = None
    stats_path = os.path.join(args.out, "train", "nwp_stats.json")
    if os.path.exists(stats_path):
        import json

        train_stats = json.load(open(stats_path))

    for split in args.splits.split(","):
        rows = ev[ev.split == split].to_dict("records")
        if args.limit:
            rows = rows[: args.limit]
        out_dir = os.path.join(args.out, split)
        rs = RunningStats(NWP_VARS)
        t0, fails = time.time(), 0
        with Pool(args.workers, initializer=_init, initargs=(args.sevir_root, args.lght_xy_units)) as pool, \
                ShardWriter(out_dir, events_per_shard=args.events_per_shard, level=args.level) as w:
            for i, (eid, a, err) in enumerate(pool.imap(_process, rows, chunksize=2), 1):
                if a is None:
                    fails += 1
                    print(f"skip {eid}: {err}")
                    continue
                if nwp is not None:
                    nwp.attach(eid, a)
                    if split == "train":
                        rs.update(a["nwp"][a["nwp_ok"]])
                w.add(eid, int(a["times"][0]), a)
                if i % 50 == 0 or i == len(rows):
                    el = time.time() - t0
                    print(f"[{split}] {i}/{len(rows)}  {w.n_bytes / max(w.n_events, 1) / 1e6:.2f} MB/event "
                          f"compressed  total {w.n_bytes / 1e9:.2f} GB  {el / 60:.1f} min  "
                          f"ETA {(len(rows) - i) * el / i / 60:.1f} min  failed {fails}", flush=True)
        if nwp is not None:
            if split == "train":
                train_stats = rs.result()
            if train_stats is None:
                raise SystemExit("build the train split first (its NWP stats normalise every split)")
            write_stats(out_dir, train_stats)
        print(f"[{split}] done: {w.n_events} events, {w.n_bytes / 1e9:.2f} GB, {fails} failed")


if __name__ == "__main__":
    main()
