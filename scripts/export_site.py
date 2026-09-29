#!/usr/bin/env python
"""Pipeline outputs -> static files for the website (no model inference on the web host).

Reads what the pipeline already writes:
  results/*.json                 test-set scores (evaluate.py, extended eval)
  results/india/<id>.json        India forecasts (nowcast.india.run)
  results/india/<id>.npz         their maps (optional; on the server, not in git)
  results/india/<id>_gk2a_check.json   storm-location checks (optional)
and writes a self-contained folder the site serves as-is (schema: docs/SITE_DATA.md):
  <out>/manifest.json, scores.json, forecasts/<id>.json, forecasts/<id>/*.png, figures/*.png

  python scripts/export_site.py --results results --figures figures --out site/public/data
  python scripts/export_site.py ... --cases site/cases.json --boundary data/india_bhuvan.geojson

Needs numpy + pyproj only. PNG overlays are written with zlib (no imaging library).
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import shutil
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np  # noqa: E402

HONEST_LABEL = ("Trained on US GLM lightning, adapted to INSAT/GFS, "
                "not yet verified against Indian lightning observations")
METRIC_NOTE = ("Lightning CSI per 16 km cell per lead hour on held-out US storms (Jun-Dec 2019), "
               "scored against real GOES-16 GLM lightning. Higher is better; 1 is perfect.")
IST = dt.timedelta(hours=5, minutes=30)

ADVICE = {
    "HIGH": "Lightning likely. Go indoors now; avoid open fields, trees, water and metal structures.",
    "MODERATE": "Thunderstorms possible. Stay alert and plan how you would reach shelter quickly.",
    "LOW": "Low lightning risk for this hour.",
}

# result file stem -> (group, display label); unknown stems are exported under their own name
RESULT_LABELS = {
    "full": ("tier1", "Tier 1 (all inputs)"),
    "full_india_mode": ("india_mode", "Tier 1 on INSAT-like + GFS-like inputs"),
    "persistence": ("baseline", "Persistence"),
    "no_ir": ("ablation", "No satellite"),
    "no_lght": ("ablation", "No lightning feed"),
    "no_nwp": ("ablation", "No NWP"),
    "no_radar": ("ablation", "No radar"),
    "no_radar_no_ir": ("ablation", "No radar, no satellite"),
    "sat_nwp_only": ("ablation", "Satellite + NWP only"),
    "ext": ("tier2", "Tier 2 (NWP post-processing)"),
    "ext_india_mode": ("tier2_india_mode", "Tier 2, GFS-like fields"),
}


# --------------------------------------------------------------------------- PNG overlays

def write_png(path: str, rgba: np.ndarray) -> None:
    """Minimal RGBA PNG writer. rgba: [H, W, 4] uint8, row 0 = top (north)."""
    h, w, _ = rgba.shape
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


# Sequential ramps (light -> dark), transparent below the first stop. The lightning ramp runs
# yellow -> orange -> red -> purple so intensity reads by lightness, not hue alone.
LGHT_STOPS = [(0.05, (255, 237, 160)), (0.2, (254, 178, 76)), (0.4, (240, 59, 32)),
              (0.6, (189, 0, 38)), (0.8, (84, 39, 143))]
VIL_STOPS = [(16, (199, 233, 192)), (74, (65, 171, 93)), (133, (35, 139, 69)),
             (160, (254, 196, 79)), (181, (236, 112, 20)), (219, (153, 52, 4))]


def colorize(x: np.ndarray, stops, alpha=(110, 220)) -> np.ndarray:
    """Values -> RGBA with piecewise-linear colour between stops; below the first stop is transparent."""
    x = np.nan_to_num(np.asarray(x, np.float32), nan=-1.0)
    v = np.array([s[0] for s in stops], np.float32)
    c = np.array([s[1] for s in stops], np.float32)
    out = np.zeros((*x.shape, 4), np.uint8)
    for k in range(3):
        out[..., k] = np.interp(x, v, c[:, k]).astype(np.uint8)
    frac = np.clip((x - v[0]) / max(v[-1] - v[0], 1e-6), 0, 1)
    out[..., 3] = np.where(x >= v[0], alpha[0] + (alpha[1] - alpha[0]) * frac, 0).astype(np.uint8)
    return out


def grid_png(path: str, grid: np.ndarray, stops) -> None:
    """Model grids have row 0 = SOUTH (SEVIR convention, ROW0_NORTH=False); images need north up."""
    from nowcast.data import sevir

    g = np.asarray(grid, np.float32)
    if not sevir.ROW0_NORTH:
        g = g[::-1]
    write_png(path, colorize(g, stops))


# --------------------------------------------------------------------------- geometry

def tile_corners(center_lat: float, center_lon: float):
    """[[lon, lat] x 4] in MapLibre image-source order: top-left, top-right, bottom-right, bottom-left."""
    import pyproj

    from nowcast.india.tiles import TILE_M, make_tile

    p = pyproj.Proj(make_tile(center_lat, center_lon)["proj"])
    h = TILE_M / 2
    pts = [(-h, h), (h, h), (h, -h), (-h, -h)]
    return [[round(float(v), 5) for v in p(x, y, inverse=True)] for x, y in pts]


def city_pixel(tile_center, city_latlon, n: int):
    from nowcast.india.tiles import latlon_to_pixel, make_tile

    r, c = latlon_to_pixel(make_tile(*tile_center), city_latlon[0], city_latlon[1], n)
    return int(np.clip(r, 0, n - 1)), int(np.clip(c, 0, n - 1))


# --------------------------------------------------------------------------- scores

def export_scores(results_dir: str) -> dict:
    out = {"metric_note": METRIC_NOTE, "honest_label": HONEST_LABEL, "series": {}, "scorecard": []}
    loaded = {}
    for p in sorted(glob.glob(os.path.join(results_dir, "*.json"))):
        stem = Path(p).stem
        try:
            r = json.load(open(p))
        except (ValueError, OSError):
            continue
        if not isinstance(r, dict) or not ({"lght_lead_hour_16km", "lead_hour"} & set(r)):
            continue
        group, label = RESULT_LABELS.get(stem, ("other", stem))
        s = {"group": group, "label": label}
        if "lght_lead_hour_16km" in r:
            s["csi_by_hour"] = {h: round(v["csi"], 4) for h, v in r["lght_lead_hour_16km"].items()}
            s["lead_minutes"] = r.get("lead_minutes")
            s["lightning_csi_per_step"] = [round(x, 4) for x in r["lght"]["tol0"]["csi_per_lead"]]
            s["vil_csi_per_step"] = [round(x, 4) for x in r["vil"]["pool1"]["csi_m_per_lead"]]
            s["summary"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.get("summary", {}).items()}
        else:  # tier-2 eval
            s["csi_by_hour"] = {h: round(v["model"]["csi"], 4) for h, v in r["lead_hour"].items()}
            s["hrrr_ltng_csi_by_hour"] = {h: round(v["hrrr_ltng"]["csi"], 4) for h, v in r["lead_hour"].items()}
            s["hrrr_refc_csi_by_hour"] = {h: round(v["hrrr_refc"]["csi"], 4) for h, v in r["lead_hour"].items()}
        run = r.get("run", {})
        s["run"] = {k: run[k] for k in ("step", "samples", "epoch", "drop", "india_mode") if k in run}
        out["series"][stem] = s
        loaded[stem] = s

    hours = sorted({int(h) for s in loaded.values() for h in s["csi_by_hour"]})
    for h in hours:
        k = str(h)
        row = {"lead_hour": h}
        for name, key in (("tier1", "full"), ("tier2", "ext"), ("persistence", "persistence")):
            if key in loaded and k in loaded[key]["csi_by_hour"]:
                row[name] = loaded[key]["csi_by_hour"][k]
        if "ext" in loaded and k in loaded["ext"].get("hrrr_ltng_csi_by_hour", {}):
            row["hrrr_lightning"] = loaded["ext"]["hrrr_ltng_csi_by_hour"][k]
            row["hrrr_reflectivity"] = loaded["ext"]["hrrr_refc_csi_by_hour"][k]
        out["scorecard"].append(row)
    out["switch_hour"] = switch_hour(out["scorecard"])
    return out


def switch_hour(rows) -> int | None:
    """Last lead hour before tier 2 first beats tier 1 (tier 1 everywhere it is better)."""
    both = [r for r in rows if "tier1" in r and "tier2" in r]
    if not both:
        return max((r["lead_hour"] for r in rows if "tier1" in r), default=None)
    for r in both:
        if r["tier2"] > r["tier1"]:
            return r["lead_hour"] - 1
    return max(r["lead_hour"] for r in rows if "tier1" in r)


# --------------------------------------------------------------------------- forecasts

def _iso(t: dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M")


def _status(block) -> str:
    if isinstance(block, list):  # NWP: one entry per valid hour
        ok = sum(1 for b in block if b.get("status") == "ok")
        return "live" if ok == len(block) and ok else ("partial" if ok else "missing")
    return (block or {}).get("status", "missing")


def _num(v):
    """Round floats for the site; NaN (no deep cells) becomes null, which JSON can carry."""
    if isinstance(v, float):
        return None if v != v else round(v, 3)
    return v


def export_forecast(json_path: str, out_dir: str, cases: dict, suffix: str = "") -> dict | None:
    from nowcast.india.tiles import CITIES

    fid = Path(json_path).stem + suffix
    meta = cases.get(fid, {})
    if meta.get("hide"):
        return None
    r = json.load(open(json_path))
    prov = r.get("provenance", {})
    tile = prov.get("tile", {})
    city = tile.get("id", fid.split("_")[0])
    center = (float(tile["center_lat"]), float(tile["center_lon"]))
    city_ll = CITIES.get(city, center)
    issue = dt.datetime.fromisoformat(prov["issue_time_utc"])
    issue_ist = issue + IST

    hours = []
    for s in r.get("summary", []):
        h = int(s["lead_hour"])
        hours.append({
            "lead_hour": h,
            "window_ist": [_iso(issue_ist + dt.timedelta(hours=h - 1)), _iso(issue_ist + dt.timedelta(hours=h))],
            "source": s.get("source"),
            "p_location": s.get("p_lightning_at_location"),
            "p_tile_max": s.get("p_lightning_max_in_tile"),
            "risk": s.get("risk"),
            "advice": ADVICE.get(s.get("risk"), ""),
        })

    sat = prov.get("satellite", {}) or {}
    inputs = {
        "satellite": {"status": _status(sat), "source": sat.get("source"),
                      "scans_utc": [x["scan"] for x in sat.get("scans", []) if "scan" in x]},
        "radar": {"status": _status(prov.get("radar")), "source": (prov.get("radar") or {}).get("source"),
                  "detail": (prov.get("radar") or {}).get("detail")},
        "lightning": {"status": _status(prov.get("lightning")), "source": (prov.get("lightning") or {}).get("source")},
        "nwp": {"status": _status(prov.get("nwp", [])),
                "runs": [{k: n.get(k) for k in ("model", "init", "fxx", "valid", "status")} for n in prov.get("nwp", [])]},
    }

    doc = {
        "id": fid, "city": city, "lat": city_ll[0], "lon": city_ll[1],
        "title": meta.get("title") or f"{city}, {issue_ist:%d %b %Y %H:%M} IST",
        "description": meta.get("description", ""),
        "kind": meta.get("kind", "case"),
        "issue_utc": _iso(issue), "issue_ist": _iso(issue_ist),
        "valid_until_ist": _iso(issue_ist + dt.timedelta(hours=max([x["lead_hour"] for x in hours], default=0))),
        "tile": {"center": [center[1], center[0]], "corners": tile_corners(*center), "size_km": 384},
        "hours": hours,
        "peak_risk": max((x["risk"] for x in hours), key=["LOW", "MODERATE", "HIGH"].index, default=None),
        "inputs": inputs,
        "model_inputs_used": r.get("tier1_inputs_present"),
        "honest_label": r.get("model_trained_on") or HONEST_LABEL,
        "overlays": {"hourly": {}, "steps": []},
    }

    check_path = json_path[:-5] + "_gk2a_check.json"
    if os.path.exists(check_path):
        c = json.load(open(check_path))
        doc["storm_check"] = {
            "what": "Storm-location check against satellite (GK2A cold cloud tops), a proxy for storms, not lightning",
            "proxy": c.get("proxy"),
            "hours": [{k: _num(v) for k, v in hh.items()} for hh in c.get("hours", [])],
        }

    npz_path = json_path[:-5] + ".npz"
    if os.path.exists(npz_path):
        z = np.load(npz_path)
        fdir = os.path.join(out_dir, "forecasts", fid)
        os.makedirs(fdir, exist_ok=True)
        src = {x["lead_hour"]: x["source"] for x in hours}
        for h in sorted(src):
            key = f"{src[h]}_hour{h}_16km"
            key = key if key in z.files else next((k for k in (f"tier1_hour{h}_16km", f"tier2_hour{h}_16km") if k in z.files), None)
            if key:
                grid_png(os.path.join(fdir, f"hour{h}.png"), z[key], LGHT_STOPS)
                doc["overlays"]["hourly"][str(h)] = f"forecasts/{fid}/hour{h}.png"
        if "tier1_lght_prob" in z.files:
            lp = z["tier1_lght_prob"].astype(np.float32)
            vil = z["tier1_vil"] if "tier1_vil" in z.files else None
            t_out = lp.shape[0]
            step_min = int(round(180 / t_out)) if t_out else 10  # 18 steps over 3 h -> 10 min
            pr, pc = city_pixel(center, city_ll, lp.shape[-1])
            for k in range(t_out):
                m = (k + 1) * step_min
                step = {"minutes": m, "time_ist": _iso(issue_ist + dt.timedelta(minutes=m)),
                        "p_location": round(float(lp[k, pr, pc]), 3),
                        "lightning": f"forecasts/{fid}/lght_{m:03d}.png"}
                grid_png(os.path.join(fdir, f"lght_{m:03d}.png"), lp[k], LGHT_STOPS)
                if vil is not None:
                    grid_png(os.path.join(fdir, f"vil_{m:03d}.png"), vil[k].astype(np.float32), VIL_STOPS)
                    step["vil"] = f"forecasts/{fid}/vil_{m:03d}.png"
                doc["overlays"]["steps"].append(step)

    os.makedirs(os.path.join(out_dir, "forecasts"), exist_ok=True)
    with open(os.path.join(out_dir, "forecasts", f"{fid}.json"), "w") as f:
        json.dump(doc, f, indent=1, allow_nan=False)
    return doc


# --------------------------------------------------------------------------- main

def main(argv=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--figures", help="folder of slide figures to publish too (optional)")
    ap.add_argument("--cases", help="JSON {forecast_id: {title, description, kind, hide}} (optional)")
    ap.add_argument("--boundary", help="India boundary GeoJSON, Survey of India (data/boundaries/india_states.geojson); never Natural Earth")
    ap.add_argument("--out", default="site/public/data")
    args = ap.parse_args(argv)

    out = args.out
    if os.path.isdir(os.path.join(out, "forecasts")):
        shutil.rmtree(os.path.join(out, "forecasts"))  # no stale overlays from earlier exports
    os.makedirs(out, exist_ok=True)
    cases = json.load(open(args.cases)) if args.cases else {}

    scores = export_scores(args.results)
    with open(os.path.join(out, "scores.json"), "w") as f:
        json.dump(scores, f, indent=1, allow_nan=False)

    forecasts = []
    for sub, suffix in (("india", ""), ("india_insat", "_insat")):  # INSAT runs share stems with GK2A ones
        for p in sorted(glob.glob(os.path.join(args.results, sub, "*.json"))):
            if p.endswith("_gk2a_check.json"):
                continue
            d = export_forecast(p, out, cases, suffix)
            if d:
                forecasts.append({k: d[k] for k in ("id", "city", "lat", "lon", "title", "kind", "issue_ist",
                                                     "issue_utc", "peak_risk")}
                                 | {"has_maps": bool(d["overlays"]["hourly"] or d["overlays"]["steps"]),
                                    "file": f"forecasts/{d['id']}.json"})

    figures = []
    if args.figures and os.path.isdir(args.figures):
        os.makedirs(os.path.join(out, "figures"), exist_ok=True)
        for p in sorted(glob.glob(os.path.join(args.figures, "*.png"))):
            shutil.copy(p, os.path.join(out, "figures", os.path.basename(p)))
            figures.append(f"figures/{os.path.basename(p)}")

    boundary = None
    if args.boundary:
        shutil.copy(args.boundary, os.path.join(out, "india_boundary.geojson"))
        boundary = "india_boundary.geojson"

    t1 = scores["series"].get("full", {}).get("run", {})
    t2 = scores["series"].get("ext", {}).get("run", {})
    manifest = {
        "generated_utc": _iso(dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)),
        "honest_label": HONEST_LABEL,
        "switch_hour": scores["switch_hour"],
        "model": {"tier1": t1, "tier2": t2},
        "scores": "scores.json",
        "boundary": boundary,
        "figures": figures,
        "forecasts": sorted(forecasts, key=lambda x: x["issue_utc"], reverse=True),
    }
    with open(os.path.join(out, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1, allow_nan=False)
    size = sum(os.path.getsize(os.path.join(d, x)) for d, _, fs in os.walk(out) for x in fs)
    print(f"exported {len(forecasts)} forecasts, {len(scores['series'])} score series, "
          f"{len(figures)} figures -> {out} ({size / 1e6:.1f} MB)")
    return manifest


if __name__ == "__main__":
    main()
