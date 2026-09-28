#!/usr/bin/env python
"""Verify the two geometry assumptions before building shards:

1. Image row order (ROW0_NORTH): correlate SEVIR VIL with HRRR REFC regridded under both
   conventions. The right one correlates clearly better.
2. Lightning x/y units (48-grid vs 384-grid pixels) and orientation: correlate gridded flashes
   with VIL under each interpretation.

  python scripts/check_alignment.py --events work/events.csv --n 12
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from nowcast.constants import LR  # noqa: E402
from nowcast.data.hrrr import Regridder, fetch_hour  # noqa: E402
from nowcast.data.sevir import (DATA_URI, SevirReader, event_grid_latlon, frame_offsets,  # noqa: E402
                                lightning_to_grid)


def corr(a, b):
    a, b = a.ravel().astype(np.float64), b.ravel().astype(np.float64)
    if a.std() == 0 or b.std() == 0:
        return np.nan
    return float(np.corrcoef(a, b)[0, 1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", default="work/events.csv")
    ap.add_argument("--sevir-root", default=DATA_URI)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--no-hrrr", action="store_true")
    args = ap.parse_args()

    ev = pd.read_csv(args.events, parse_dates=["time_utc"])
    ev = ev[ev.id.str.startswith("S")].head(args.n)
    reader = SevirReader(args.sevir_root)
    rg = None
    res = {k: [] for k in ["refc_north", "refc_south", "lght48", "lght48_flipud", "lght384", "lght384_flipud"]}
    for r in ev.to_dict("records"):
        vil = np.moveaxis(reader.read("vil", r["file_vil"], r["index_vil"], r["id"]), -1, 0).astype(np.float32)
        T, H, _ = vil.shape
        vil48 = vil.reshape(T, LR, H // LR, LR, H // LR).max(axis=(2, 4))
        offs = frame_offsets(pd.Series(r))

        fl = reader.read("lght", r["file_lght"], r["index_lght"], r["id"])
        if len(fl):
            vsum = vil48.sum(0)
            for units in (48, 384):
                g = lightning_to_grid(fl, offs, LR, xy_units=units).astype(np.float32).sum(0)
                res[f"lght{units}"].append(corr(g, vsum))
                res[f"lght{units}_flipud"].append(corr(g[::-1], vsum))

        if not args.no_hrrr:
            t_evt = pd.Timestamp(r["time_utc"])
            valid = t_evt.floor("h")
            fields, lat, lon = fetch_hour(valid, fields=[("refc", ":REFC:entire atmosphere")])
            if lat is not None and fields.get("refc") is not None:
                rg = rg or Regridder(lat, lon)
                k = int(np.argmin(np.abs(offs - (valid - t_evt).total_seconds())))
                for north in (True, False):
                    la, lo = event_grid_latlon(r, LR, row0_north=north)
                    refc = Regridder.apply(fields["refc"], rg.weights(la, lo))
                    res["refc_north" if north else "refc_south"].append(corr(refc, vil48[k]))
        print(r["id"], {k: round(v[-1], 3) for k, v in res.items() if v})

    print("\nmean correlations:")
    for k, v in res.items():
        if v:
            print(f"  {k:16s} {np.nanmean(v):+.3f}  (n={len(v)})")
    if res["refc_north"]:
        north = np.nanmean(res["refc_north"]) > np.nanmean(res["refc_south"])
        print(f"\n-> set ROW0_NORTH = {north} in src/nowcast/data/sevir.py")
    lk = {k: np.nanmean(v) for k, v in res.items() if k.startswith("lght") and v}
    if lk:
        best = max(lk, key=lk.get)
        print(f"-> lightning: best interpretation '{best}'. Use --lght-xy-units "
              f"{384 if '384' in best else 48}; if the best one is *_flipud, the flash y axis runs "
              f"opposite to image rows and lightning_to_grid needs a flip.")


if __name__ == "__main__":
    main()
