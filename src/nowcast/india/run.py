"""0-6 h thunderstorm / lightning forecast for an Indian city or tile from Indian data.

  python -m nowcast.india.run --city Bhubaneswar --time 2024-05-10T09:00 \
      --insat-dir data/insat --tier1 runs/full/final_ema_bf16.pt --tier2 runs/ext/best.pt \
      [--lightning-csv data/illn/strikes.csv] [--radar-npz data/imd/maxz.npz] --out results/india

Sources (each optional except NWP for tier 2; whatever is missing is passed to the model as missing,
which it was trained for with modality dropout):
  satellite  INSAT-3DR/3DS L1B files (MOSDAC)          -> tier 1 IR channels
             or --gk2a: GK2A AMI from NOAA's open bucket (no login), same channels
  radar      IMD DWR reflectivity (dBZ + lat/lon, .npz) -> tier 1 radar channel (approx. VIL)
  lightning  strike CSV (IITM ILLN / IMD / ENTLN)       -> tier 1 lightning channel
  NWP        GFS 0.25 (NOAA, open)                      -> tier 1 NWP + tier 2 input
Every source's status is written to the output JSON (live / missing / approximate).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import os

import numpy as np
import torch

from ..constants import FRAME_SECONDS, LGHT_LOG_SCALE
from ..data.dataset import GFS_MISSING_VARS
from ..metrics import pool_max
from . import gfs, gk2a, insat, lightning, radar
from .tiles import CITIES, city_tile, latlon_to_pixel, make_tile


def _norm(x: np.ndarray, stats: dict) -> np.ndarray:
    mean = np.asarray(stats["mean"], np.float32)[:, None, None]
    std = np.asarray(stats["std"], np.float32)[:, None, None]
    return np.clip(np.nan_to_num((x - mean) / std, nan=0.0, posinf=0.0, neginf=0.0), -10, 10)


def _tod(t: dt.datetime, lon: float) -> np.ndarray:
    h = (t.hour + t.minute / 60 + lon / 15.0) % 24
    return np.array([math.sin(2 * math.pi * h / 24), math.cos(2 * math.pi * h / 24)], np.float32)


class _GFS:
    """Fetch each valid hour once per run; regrid per tile grid size on demand."""

    def __init__(self, issue: dt.datetime, fetch=None):
        self.issue, self.fetch = issue, fetch or gfs.fetch
        self.raw, self.meta = {}, []

    def get(self, valid: dt.datetime, tile: dict, n: int):
        if valid not in self.raw:
            f, lat, lon, meta = self.fetch(valid, self.issue)
            self.raw[valid] = (f, lat, lon)
            self.meta.append(meta)
        f, lat, lon = self.raw[valid]
        return None if f is None else gfs.to_tile(f, lat, lon, tile, n)


def run(args, gfs_fetch=None) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    t0 = dt.datetime.fromisoformat(args.time).replace(tzinfo=None)
    tile = city_tile(args.city) if args.city else make_tile(args.lat, args.lon)
    hr = args.hr
    lr, g2 = hr // 4, hr // 8
    prov = {"issue_time_utc": t0.isoformat(), "tile": {k: tile[k] for k in ("id", "center_lat", "center_lon")}}
    nwp_src = _GFS(t0, gfs_fetch)
    out = {"provenance": prov}

    # ------------------------------------------------------------------ tier 1 (0-3 h)
    if args.tier1:
        from ..evaluate import load_model

        model, ck = load_model(args.tier1, device)
        cfg = ck["model_cfg"]
        hz = ck.get("config", {}).get("data", {})
        t_in, t_out, step = cfg["t_in"], cfg["t_out"], hz.get("out_step", 2)
        frame_times = [t0 - dt.timedelta(seconds=(t_in - 1 - j) * FRAME_SECONDS) for j in range(t_in)]
        frame_unix = np.array([int(t.replace(tzinfo=dt.timezone.utc).timestamp()) for t in frame_times])
        present = {}

        ir = np.zeros((t_in, 2, hr, hr), np.uint8)
        frames, prov["satellite"] = None, {"status": "missing"}
        if args.insat_dir:  # primary Indian source
            frames, p = insat.insat_frames(insat.find_scans(args.insat_dir), tile, t0, t_in, hr)
            prov["satellite"] = {"source": "INSAT-3DR/3DS L1B (MOSDAC)", "status": "live" if frames is not None else "missing", "scans": p}
        if frames is None and getattr(args, "gk2a", False):  # open, no-login fallback
            gk2a.download(t0, t_in, args.gk2a_dir)
            frames, p = gk2a.gk2a_frames(gk2a.find_scans(args.gk2a_dir), tile, t0, t_in, hr)
            prov["satellite"] = {"source": "GK2A AMI L1B (KMA, NOAA open data); stand-in until INSAT is connected",
                                 "status": "live" if frames is not None else "missing", "scans": p}
        present["ir"] = frames is not None
        if frames is not None:
            ir = frames

        vil = np.zeros((t_in, hr, hr), np.uint8)
        if args.radar_npz:
            z = np.load(args.radar_npz)
            vil[:] = radar.dbz_to_tile(z["dbz"], z["lat"], z["lon"], tile, hr)[None]
            present["vil"] = True
            prov["radar"] = {"source": str(z["source"]) if "source" in z.files else "IMD DWR reflectivity", "status": "approximate",
                             "detail": "single composite held over the input window; VIL approximated from dBZ"}
        else:
            present["vil"] = False
            prov["radar"] = {"status": "missing"}

        lg = np.zeros((t_in, lr, lr), np.uint8)
        if args.lightning_csv:
            lg = lightning.grid_strikes(lightning.read_strikes(args.lightning_csv), tile, frame_unix, lr)
            present["lght"] = True
            prov["lightning"] = {"source": os.path.basename(args.lightning_csv), "status": "live",
                                 "strikes_in_window": int(lg.sum())}
        else:
            present["lght"] = False
            prov["lightning"] = {"status": "missing"}

        nh = cfg["nwp_hours"]
        base = t0.replace(minute=0, second=0, microsecond=0)
        nwp = np.zeros((nh, cfg["nwp_vars"], lr, lr), np.float32)
        ok = np.zeros(nh, bool)
        for j in range(nh):
            f = nwp_src.get(base + dt.timedelta(hours=j), tile, lr)
            if f is not None:
                nwp[j], ok[j] = _norm(f, ck["nwp_stats"]), True
        present["nwp"] = bool(ok.any())

        T = lambda a: torch.from_numpy(np.ascontiguousarray(a))[None].to(device)  # noqa: E731
        x = {"vil": T(vil).float() / 255, "ir": T(ir).float().flatten(1, 2) / 255,
             "lght": torch.log1p(T(lg).float()) / LGHT_LOG_SCALE, "nwp": T(nwp).flatten(1, 2),
             "tod": T(_tod(t0, tile["center_lon"])),
             "present": {k: torch.tensor([v], device=device) for k, v in present.items()}}
        with torch.no_grad():
            o = model(x)
        vil_p = o["vil"].float().clamp(0, 1)[0].cpu().numpy()
        lp = torch.sigmoid(o["lght"].float())
        leads = [(k + 1) * step * 5 for k in range(t_out)]
        hours = sorted({(m - 1) // 60 + 1 for m in leads})
        hourly = {h: pool_max(lp[:, [i for i, m in enumerate(leads) if (m - 1) // 60 + 1 == h]].amax(1, keepdim=True), 2)[0, 0].cpu().numpy()
                  for h in hours}
        out["tier1"] = {"lead_minutes": leads, "vil": (vil_p * 255).round().astype(np.uint8),
                        "lght_prob": lp[0].cpu().numpy().astype(np.float16), "hourly_16km": hourly,
                        "inputs_present": present}

    # ------------------------------------------------------------------ tier 2 (hours 1-6)
    if args.tier2:
        from ..extended import load as load_ext

        m2, ck2 = load_ext(args.tier2, device)
        stats = ck2["stats"]
        miss = [stats["vars"].index(v) for v in GFS_MISSING_VARS if v in stats["vars"]]
        res = {}
        for k in range(1, ck2["cfg"]["max_lead"] + 1):
            V = (t0 + dt.timedelta(hours=k)).replace(minute=0, second=0, microsecond=0)
            f1, f0 = nwp_src.get(V, tile, g2), nwp_src.get(V - dt.timedelta(hours=1), tile, g2)
            if f1 is None and f0 is None:
                continue
            f1 = f0 if f1 is None else f1
            f0 = f1 if f0 is None else f0
            xx = np.stack([_norm(f0, stats), _norm(f1, stats)])
            xx[:, miss] = 0.0
            xt = torch.from_numpy(xx.reshape(-1, g2, g2))[None].to(device)
            with torch.no_grad():
                o = m2(xt, torch.tensor([k], device=device), torch.from_numpy(_tod(V, tile["center_lon"]))[None].to(device))
            res[k] = torch.sigmoid(o["lght"].float())[0].cpu().numpy()
        out["tier2"] = {"hourly_16km": res}
    prov["nwp"] = nwp_src.meta

    # ------------------------------------------------------------------ seamless product
    lat, lon = (CITIES[args.city] if args.city else (args.lat, args.lon))
    r, c = latlon_to_pixel(tile, lat, lon, g2)
    r, c = int(np.clip(r, 0, g2 - 1)), int(np.clip(c, 0, g2 - 1))
    summary = []
    for h in range(1, 7):
        src = "tier1" if h <= args.switch_hour else "tier2"
        grid = out.get(src, {}).get("hourly_16km", {}).get(h)
        if grid is None and src == "tier1":
            src, grid = "tier2", out.get("tier2", {}).get("hourly_16km", {}).get(h)
        if grid is None:
            continue
        p_here = float(grid[r, c])
        summary.append({"lead_hour": h, "source": src, "p_lightning_at_location": round(p_here, 3),
                        "p_lightning_max_in_tile": round(float(grid.max()), 3),
                        "risk": "HIGH" if p_here >= 0.5 else "MODERATE" if p_here >= 0.2 else "LOW"})
    out["summary"] = summary

    os.makedirs(args.out, exist_ok=True)
    stem = os.path.join(args.out, f"{tile['id']}_{t0:%Y%m%dT%H%M}")
    arrays = {}
    if "tier1" in out:
        arrays.update(tier1_vil=out["tier1"]["vil"], tier1_lght_prob=out["tier1"]["lght_prob"])
    for tier in ("tier1", "tier2"):
        for h, g in out.get(tier, {}).get("hourly_16km", {}).items():
            arrays[f"{tier}_hour{h}_16km"] = g
    np.savez_compressed(stem + ".npz", **arrays)
    report = {"provenance": prov, "summary": summary, "model_trained_on": "SEVIR (GOES-16/NEXRAD/GLM) + HRRR, US 2018-19, "
              "with INSAT-like and GFS-like input augmentation; skill over India not yet verified against Indian lightning observations"}
    if "tier1" in out:
        report["tier1_inputs_present"] = out["tier1"]["inputs_present"]
    with open(stem + ".json", "w") as f:
        json.dump(report, f, indent=1, default=str)
    print(json.dumps({"summary": summary, "inputs": report.get("tier1_inputs_present")}, default=str))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", choices=sorted(CITIES))
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--time", required=True, help="issue time, UTC, ISO format")
    ap.add_argument("--insat-dir")
    ap.add_argument("--gk2a", action="store_true", help="use GK2A (open, no login) when INSAT is not available")
    ap.add_argument("--gk2a-dir", default="data/gk2a", help="download cache for GK2A scans")
    ap.add_argument("--radar-npz", help=".npz with dbz, lat, lon arrays (+ optional source name), e.g. from scripts/cfradial_to_maxz.py")
    ap.add_argument("--lightning-csv")
    ap.add_argument("--tier1")
    ap.add_argument("--tier2")
    ap.add_argument("--switch-hour", type=int, default=2, help="use tier 1 up to this lead hour (set from crossover.py)")
    ap.add_argument("--hr", type=int, default=192)
    ap.add_argument("--out", default="results/india")
    args = ap.parse_args(argv)
    if not args.city and (args.lat is None or args.lon is None):
        ap.error("give --city or --lat/--lon")
    return run(args)


if __name__ == "__main__":
    main()
