#!/usr/bin/env python
"""Step 1: pick the SEVIR events (all of vil/ir069/ir107/lght present), split by date.

  python scripts/select_events.py --out work/events.csv --n-train 6000 --n-val 500 --n-test 1000

Only ~2.6k complete events are storm ('S') events (1500 train / 431 val / 642 test), so every
storm event is taken and the rest is filled with random ('R') events. The defaults give
7,500 events (2,542 storm), ~21 GB compressed.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd  # noqa: E402

from nowcast.data.sevir import CATALOG_URI, SPLITS, complete_events, load_catalog, select_events, split_mask  # noqa: E402

RAW_MB_PER_EVENT = 5.8  # uint8 VIL 192^2 + 2x IR 192^2 + lightning 48^2 (x49) + fp16 NWP


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default=CATALOG_URI)
    ap.add_argument("--out", default="work/events.csv")
    ap.add_argument("--n-train", type=int, default=6000)
    ap.add_argument("--n-val", type=int, default=500)
    ap.add_argument("--n-test", type=int, default=1000)
    ap.add_argument("--storm-frac", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    ev = complete_events(load_catalog(args.catalog))
    print(f"complete events (vil+ir069+ir107+lght): {len(ev)}")
    parts = []
    for split, n in [("train", args.n_train), ("val", args.n_val), ("test", args.n_test)]:
        sub = ev[split_mask(ev, split)]
        sel = select_events(sub, n, args.storm_frac, args.seed).assign(split=split)
        n_storm = int(sel.id.str.startswith("S").sum())
        print(f"{split:5s} {SPLITS[split]}: available {len(sub):6d}  selected {len(sel):6d} "
              f"(storm {n_storm}, random {len(sel) - n_storm})  ~{len(sel) * RAW_MB_PER_EVENT / 1024:.1f} GB raw")
        parts.append(sel)
    out = pd.concat(parts, ignore_index=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    out.to_csv(args.out, index=False)
    for t in ("vil", "ir069", "ir107", "lght"):
        print(f"distinct {t} files touched: {out[f'file_{t}'].nunique()}")
    print(f"wrote {args.out} ({len(out)} events). Expect roughly 2x zstd compression; measure on 100 events.")


if __name__ == "__main__":
    main()
