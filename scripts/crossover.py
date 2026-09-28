#!/usr/bin/env python
"""Seamless 0-6 h scorecard: lightning CSI per lead hour on the common 16 km grid.

Tier-1 runs (fusion model, baselines) report `lght_lead_hour_16km`; the tier-2 eval reports
`lead_hour`. Both answer "lightning in this 16 km cell during lead hour k?". The hour where tier 2
overtakes tier 1 is where the operational product should switch source.

  python scripts/crossover.py --tier1 results/full.json results/radar.json results/persistence.json \
      --tier2 results/ext.json
"""

import argparse
import json
import os


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tier1", nargs="*", default=[])
    ap.add_argument("--tier2")
    args = ap.parse_args()

    cols, table = [], {}
    for path in args.tier1:
        r = json.load(open(path))
        name = os.path.splitext(os.path.basename(path))[0]
        cols.append(name)
        for h, v in r.get("lght_lead_hour_16km", {}).items():
            table.setdefault(int(h), {})[name] = v["csi"]
    if args.tier2:
        r = json.load(open(args.tier2))
        for c in ("tier2_model", "hrrr_ltng", "hrrr_refc"):
            cols.append(c)
        for h, v in r["lead_hour"].items():
            row = table.setdefault(int(h), {})
            row["tier2_model"] = v["model"]["csi"]
            row["hrrr_ltng"] = v["hrrr_ltng"]["csi"]
            row["hrrr_refc"] = v["hrrr_refc"]["csi"]
            row["base_rate"] = v["base_rate"]

    print("| lead hour | " + " | ".join(cols) + " | best |")
    print("|---|" + "---|" * (len(cols) + 1))
    for h in sorted(table):
        row = table[h]
        vals = {c: row.get(c) for c in cols}
        best = max((c for c in cols if vals[c] is not None), key=lambda c: vals[c], default="-")
        cells = [f"{vals[c]:.3f}" if vals[c] is not None else "-" for c in cols]
        print(f"| {h} | " + " | ".join(cells) + f" | {best} |")


if __name__ == "__main__":
    main()
