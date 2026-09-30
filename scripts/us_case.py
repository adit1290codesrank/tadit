#!/usr/bin/env python
"""A US city case for the site, next to the India ones: a held-out SEVIR test storm (after 1 Jun 2019, never
seen in training) with the real inputs the model was built for (GOES-16 IR, NEXRAD VIL, GLM, HRRR), and the
GLM lightning that actually followed.

The storm is picked on observed lightning near one of the cities below (most GLM flashes within 40 km of the
city in the 3 h after issue), not on forecast skill. Cities sit near the SEVIR projection centre (98 W), so the
patch lines up with the site's map tile. SEVIR events are 4 h long, so the case covers tier 1 (hours 1-3) only.

Writes, like nowcast.india.run + check_india_lightning.py:
  <out>/<City>_<time>.json / .npz / _ltg_check.json
  <out>/<City>_<time>_glm.csv   GLM flashes at 8 km cell centres, for export_site.py --observed

  python scripts/us_case.py --ckpt runs/snaps/latest_0611.pt --shards shards/test --events work/events.csv --out results/us
"""

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyproj  # noqa: E402
import torch  # noqa: E402
from torch.utils.data import default_collate  # noqa: E402

from check_india_lightning import _scores  # noqa: E402
from nowcast.data.dataset import NowcastDataset, prepare_batch  # noqa: E402
from nowcast.data.sevir import event_grid_latlon  # noqa: E402
from nowcast.evaluate import load_model  # noqa: E402
from nowcast.metrics import pool_max  # noqa: E402

CITIES = {
    "Oklahoma City": (35.468, -97.516), "Tulsa": (36.154, -95.993), "Wichita": (37.687, -97.330),
    "Dallas": (32.777, -96.797), "Fort Worth": (32.755, -97.331), "Austin": (30.267, -97.743),
    "San Antonio": (29.424, -98.494), "Houston": (29.760, -95.370), "Omaha": (41.257, -95.935),
    "Lincoln": (40.814, -96.702), "Kansas City": (39.100, -94.579), "Topeka": (39.048, -95.678),
    "Sioux Falls": (43.545, -96.731),
}
NEAR_KM = 40.0
MARGIN = 6  # city at least 6 lightning cells (48 km) inside the patch


def patch_xy(row, lat, lon, n):
    """Fractional (row, col) on the n x n patch grid (row 0 = south, as stored)."""
    p = pyproj.Proj(row["proj"])
    x0, y0 = p(row["llcrnrlon"], row["llcrnrlat"])
    x1, y1 = p(row["urcrnrlon"], row["urcrnrlat"])
    x, y = p(lon, lat)
    return (y - y0) / (y1 - y0) * n, (x - x0) / (x1 - x0) * n


def patch_corners(row):
    """[[lon, lat] x 4], MapLibre order: top-left, top-right, bottom-right, bottom-left."""
    p = pyproj.Proj(row["proj"])
    x0, y0 = p(row["llcrnrlon"], row["llcrnrlat"])
    x1, y1 = p(row["urcrnrlon"], row["urcrnrlat"])
    return [[round(float(v), 5) for v in p(x, y, inverse=True)] for x, y in ((x0, y1), (x1, y1), (x1, y0), (x0, y0))]


def km(lat, lon, lat0, lon0):
    return np.hypot((lat - lat0) * 111.0, (lon - lon0) * 111.0 * np.cos(np.deg2rad(lat0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ckpt", required=True)
    ap.add_argument("--shards", default="shards/test")
    ap.add_argument("--events", default="work/events.csv")
    ap.add_argument("--out", default="results/us")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model, ck = load_model(args.ckpt, device)
    hz = ck.get("config", {}).get("data", {})
    horizon = {k: hz[k] for k in ("t_in", "t_out", "out_step") if k in hz}
    ds = NowcastDataset(args.shards, train=False, windows_per_event=10**6, stats=ck.get("nwp_stats"), **horizon)
    wpe, t_in, t_out, st = ds.wpe, ds.t_in, ds.t_out, ds.out_step  # wpe = max_start + 1: window k starts at frame k
    cat = pd.read_csv(args.events).set_index("id")

    # ---------------------------------------------------------------- pick the storm (on observed lightning only)
    best = None
    for ev in range(len(ds.store)):
        eid = str(ds.store.index[ev]["event_id"])
        if eid not in cat.index:
            continue
        row = cat.loc[eid]
        near = []
        for name, (la, lo) in CITIES.items():
            r, c = patch_xy(row, la, lo, 48)
            if MARGIN <= r < 48 - MARGIN and MARGIN <= c < 48 - MARGIN:
                near.append(name)
        if not near:
            continue
        lg = ds.store.get(ev)["lght"]
        lat, lon = event_grid_latlon(row, lg.shape[-1])
        for name in near:
            close = km(lat, lon, *CITIES[name]) <= NEAR_KM
            for s in range(wpe):
                i0 = s + t_in - 1
                n = int(lg[i0 + 1: i0 + st * t_out + 1][:, close].sum())
                if best is None or n > best[0]:
                    best = (n, ev, s, name, eid)
    if best is None:
        raise SystemExit("no test event covers any of the cities")
    n_near, ev, s, city, eid = best
    row = cat.loc[eid]
    a = ds.store.get(ev)
    i0 = s + t_in - 1
    t0 = dt.datetime.fromtimestamp(int(a["times"][i0]), dt.timezone.utc).replace(tzinfo=None)
    print(f"{eid}: {city}, issue {t0:%Y-%m-%d %H:%M} UTC, {n_near} GLM flashes within {NEAR_KM:.0f} km in the next 3 h")

    # ---------------------------------------------------------------- forecast
    item = ds[ev * wpe + s]
    x, _ = prepare_batch(default_collate([item]), device)
    with torch.no_grad():
        o = model(x)
    vil = (o["vil"].float().clamp(0, 1)[0].cpu().numpy() * 255).round().astype(np.uint8)
    lp = torch.sigmoid(o["lght"].float())
    leads = [(k + 1) * st * 5 for k in range(t_out)]
    hourly = {h: pool_max(lp[:, [i for i, m in enumerate(leads) if (m - 1) // 60 + 1 == h]].amax(1, keepdim=True), 2)[0, 0].cpu().numpy()
              for h in sorted({(m - 1) // 60 + 1 for m in leads})}
    g2 = next(iter(hourly.values())).shape[-1]
    pr, pc = (int(np.clip(v, 0, g2 - 1)) for v in patch_xy(row, *CITIES[city], g2))

    summary = []
    for h, grid in hourly.items():
        p = float(grid[pr, pc])
        summary.append({"lead_hour": h, "source": "tier1", "p_lightning_at_location": round(p, 3),
                        "p_lightning_max_in_tile": round(float(grid.max()), 3),
                        "risk": "HIGH" if p >= 0.5 else "MODERATE" if p >= 0.2 else "LOW"})

    # ---------------------------------------------------------------- what actually happened (GLM)
    lg = a["lght"]
    lat, lon = event_grid_latlon(row, lg.shape[-1])
    rows = []
    for k in range(len(lg)):
        rr, cc = np.nonzero(lg[k])
        t = dt.datetime.fromtimestamp(int(a["times"][k]) - 150, dt.timezone.utc)  # frame k bins (T_k - 5 min, T_k]
        for r_, c_ in zip(rr, cc):
            rows += [(t.strftime("%Y-%m-%dT%H:%M:%SZ"), round(float(lat[r_, c_]), 4), round(float(lon[r_, c_]), 4))] * int(lg[k, r_, c_])
    flashes = pd.DataFrame(rows, columns=["time", "lat", "lon"])

    def cells(frames):  # [24, 24] bool: 16 km cells with any flash
        return pool_max(torch.from_numpy((frames.sum(0) > 0).astype(np.float32))[None, None], 2)[0, 0].numpy() > 0

    pers = cells(lg[i0 - 2: i0 + 1])  # the last 15 min before issue
    close = km(lat, lon, *CITIES[city]) <= 16
    check = []
    for h, grid in hourly.items():
        f = lg[i0 + 1 + (h - 1) * 12: i0 + 1 + h * 12]
        obs = cells(f)
        p = grid.astype(np.float32)
        check.append({"hour": h, "source": "tier1", "strikes_region": int(f.sum()), "status": "scored",
                      "strikes_tile": int(f.sum()), "cells_observed": int(obs.sum()),
                      "strikes_within_16km": int(f[:, close].sum()), "p_city": round(float(p[pr, pc]), 3),
                      "p_max": round(float(p.max()), 3), "brier": round(float(((p - obs) ** 2).mean()), 4),
                      "scores": _scores(p, obs), "persistence_csi": _scores(pers.astype(np.float32), obs)["0.5"]["csi"]})

    # ---------------------------------------------------------------- write, in the India run format
    frame_times = [dt.datetime.fromtimestamp(int(t), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") for t in a["times"][s: i0 + 1]]
    base = int(a["times"][i0]) // 3600 * 3600
    prov = {
        "issue_time_utc": t0.isoformat(),
        "tile": {"id": city, "center_lat": float(lat.mean()), "center_lon": float(lon.mean()),
                 "city_lat": CITIES[city][0], "city_lon": CITIES[city][1], "corners": patch_corners(row), "sevir_id": eid},
        "satellite": {"source": "GOES-16 ABI 6.9 / 10.7 um (SEVIR)", "status": "live", "scans": [{"scan": t} for t in frame_times]},
        "radar": {"source": "NEXRAD VIL mosaic (SEVIR)", "status": "live"},
        "lightning": {"source": "GOES-16 GLM (SEVIR)", "status": "live", "strikes_in_window": int(lg[s: i0 + 1].sum())},
        "nwp": [{"model": "hrrr", "valid": dt.datetime.fromtimestamp(base + 3600 * j, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
                 "status": "ok" if ok else "missing"} for j, ok in enumerate(item["nwp_ok"])],
    }
    os.makedirs(args.out, exist_ok=True)
    stem = os.path.join(args.out, f"{city.replace(' ', '')}_{t0:%Y%m%dT%H%M}")
    arrays = {"tier1_vil": vil, "tier1_lght_prob": lp[0].cpu().numpy().astype(np.float16)}
    arrays.update({f"tier1_hour{h}_16km": g for h, g in hourly.items()})
    np.savez_compressed(stem + ".npz", **arrays)
    report = {"provenance": prov, "summary": summary, "observed_source": "GOES-16 GLM satellite lightning (flashes)",
              "model_trained_on": "Trained on US storms before 2019 (SEVIR: GOES-16, NEXRAD, GLM, HRRR). This storm is from the "
                                  "held-out test period (after 1 Jun 2019), which the model never saw.",
              "tier1_inputs_present": {"ir": True, "vil": True, "lght": True, "nwp": bool(x["present"]["nwp"].item())}}
    json.dump(report, open(stem + ".json", "w"), indent=1)
    json.dump({"city": city, "issue_utc": t0.isoformat(), "source": "GOES-16 GLM (SEVIR)",
               "what": "Forecast vs observed lightning: any flash in a 16 km cell during the lead hour", "hours": check},
              open(stem + "_ltg_check.json", "w"), indent=1)
    flashes.to_csv(stem + "_glm.csv", index=False)

    print(" hr | P city | flashes <=16 km | cells obs | CSI@0.2 CSI@0.4 | persistence")
    for c in check:
        print(f"  {c['hour']} |  {c['p_city']:.2f}  | {c['strikes_within_16km']:6d}          | {c['cells_observed']:4d}      |"
              f"  {c['scores']['0.2']['csi'] or 0:.2f}    {c['scores']['0.4']['csi'] or 0:.2f}  |  {c['persistence_csi'] or 0:.2f}")
    print("wrote", stem + ".{json,npz}", "+ _ltg_check.json + _glm.csv")


if __name__ == "__main__":
    main()
