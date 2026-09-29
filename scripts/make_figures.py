#!/usr/bin/env python
"""Step 13: every slide figure from the result files. Figures for missing inputs are skipped.

  fig1_scorecard.png      lightning CSI per lead hour 1-6 at 16 km: tier 1, tier 2, persistence, HRRR
  fig2_csi_vs_lead.png    tier 1 vs persistence per 10-min lead: lightning CSI and VIL CSI-mean
  fig3_ablations.png      lead-hour CSI with inputs removed (--drop runs) and on INSAT/GFS-like inputs
  fig4_india_mode.png     US inputs vs INSAT/GFS-like inputs, tier 1 and tier 2
  fig5_example_<i>.png    forecast panels from results/full_examples.npz (storms with the most lightning)
  fig6_india_<case>.png   India case: hourly lightning probability maps and the risk timeline
  scorecard.md            the fig1 numbers as a table

India maps draw boundaries only from --boundary (Survey of India state GeoJSON). Without it the
map has a lat/lon grid and no boundary lines; Natural Earth is never used.

  python scripts/make_figures.py --results results --out figures --switch-hour 3 \
      --boundary data/boundaries/india_states.geojson
"""

import argparse
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

LABEL = ("Trained on US GLM lightning, adapted to INSAT/GFS, "
         "not yet verified against Indian lightning observations.")

# Chart surface, ink and categorical slots (validated: adjacent CVD dE >= 9.1, normal-vision >= 19.6).
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA, YELLOW, MAGENTA = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"
HOUR_RAMP = ["#86b6ef", "#2a78d6", "#104281"]  # ordinal blue steps 250 / 450 / 650: lead hours 1-3
VIL_CMAP = LinearSegmentedColormap.from_list("vil", [SURFACE, "#b7d3f6", "#5598e7", "#1c5cab", "#0d366b"])
PROB_CMAP = LinearSegmentedColormap.from_list("prob", [SURFACE, "#f8c9b3", "#eb6834", "#b8451a", "#6e2508"])

# Entity -> (label, colour, line style). Colour follows the entity in every figure.
SERIES = {
    "full": ("Tier 1 model", BLUE, "-"),
    "tier2_model": ("Tier 2 model", ORANGE, "-"),
    "persistence": ("Persistence", AQUA, "--"),
    "hrrr_ltng": ("HRRR lightning (raw)", YELLOW, ":"),
    "hrrr_refc": ("HRRR reflectivity (raw)", MAGENTA, ":"),
    "radar": ("Radar-only model", ORANGE, "-."),
}
ABLATIONS = [  # (result file stem, label), top to bottom
    ("full", "All inputs"),
    ("full_india_mode", "INSAT/GFS-like inputs"),
    ("no_ir", "No satellite"),
    ("no_lght", "No lightning feed"),
    ("no_nwp", "No NWP"),
    ("no_radar", "No radar"),
    ("no_radar_no_ir", "No radar, no satellite"),
    ("sat_nwp_only", "Satellite + NWP only"),
    ("persistence", "Persistence baseline"),
]
LEAD_IDX = (2, 5, 11, 17)  # +30, +60, +120, +180 min in the 18 x 10-min output


def style():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.size": 12, "axes.titlesize": 14, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.labelcolor": INK2, "axes.edgecolor": AXIS, "text.color": INK,
        "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelcolor": INK2, "ytick.labelcolor": INK2,
        "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "legend.frameon": False, "lines.linewidth": 2, "lines.markersize": 8,
    })


def load(res_dir, stem):
    p = os.path.join(res_dir, f"{stem}.json")
    return json.load(open(p)) if os.path.exists(p) else None


def hour_csi(r):
    """{lead hour: CSI} at 16 km from a tier-1 result or a tier-2 (ext) result."""
    if r is None:
        return {}
    if "lght_lead_hour_16km" in r:
        return {int(h): v["csi"] for h, v in r["lght_lead_hour_16km"].items()}
    return {int(h): v["model"]["csi"] for h, v in r.get("lead_hour", {}).items()}


def footnote(fig, extra=""):
    fig.text(0.01, -0.01, (extra + "  " if extra else "") + LABEL, fontsize=8.5, color=MUTED, ha="left", va="top")


def save(fig, out, name):
    path = os.path.join(out, name)
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path)


def end_label(ax, x, y, text, color):
    ax.annotate(text, (x, y), xytext=(8, 0), textcoords="offset points", va="center", fontsize=10.5, color=INK2)
    ax.plot([x], [y], "o", color=color, markersize=6, markeredgecolor=SURFACE, markeredgewidth=2, zorder=5)


# ---------------------------------------------------------------------------------------- figures
def scorecard(res, out, switch_hour):
    t1, pers, ext = load(res, "full"), load(res, "persistence"), load(res, "ext")
    if t1 is None and ext is None:
        return None
    rows = {"full": hour_csi(t1), "persistence": hour_csi(pers)}
    if ext:
        rows["tier2_model"] = hour_csi(ext)
        rows["hrrr_ltng"] = {int(h): v["hrrr_ltng"]["csi"] for h, v in ext["lead_hour"].items()}
        rows["hrrr_refc"] = {int(h): v["hrrr_refc"]["csi"] for h, v in ext["lead_hour"].items()}
    radar = load(res, "radar")
    if radar:
        rows["radar"] = hour_csi(radar)
    rows = {k: v for k, v in rows.items() if v}
    hours = sorted({h for v in rows.values() for h in v})

    if switch_hour is None and "tier2_model" in rows:  # first hour where tier 2 beats tier 1, minus one
        both = [h for h in hours if h in rows["full"] and h in rows["tier2_model"]]
        beaten = [h for h in both if rows["tier2_model"][h] > rows["full"][h]]
        switch_hour = beaten[0] - 1 if beaten else max(rows["full"], default=0)

    fig, ax = plt.subplots(figsize=(11, 6))
    if switch_hour:
        ax.axvspan(0.5, switch_hour + 0.5, color="#eef4fc", zorder=0, lw=0)
        ax.text(0.6, 0.03, "Tier 1: radar + satellite + lightning + NWP", transform=ax.get_xaxis_transform(),
                fontsize=10, color=INK2, va="bottom")
        if switch_hour < max(hours):
            ax.text(switch_hour + 0.6, 0.03, "Tier 2: NWP post-processing", transform=ax.get_xaxis_transform(),
                    fontsize=10, color=INK2, va="bottom")
    for key in ("full", "tier2_model", "radar", "persistence", "hrrr_ltng", "hrrr_refc"):
        if key not in rows:
            continue
        label, color, ls = SERIES[key]
        hs = sorted(rows[key])
        ys = [rows[key][h] for h in hs]
        ax.plot(hs, ys, ls, color=color, label=label, zorder=3)
        end_label(ax, hs[-1], ys[-1], label, color)
    ax.set_xticks(hours)
    ax.set_xlim(0.5, max(hours) + 1.6)
    ax.set_ylim(0, None)
    ax.set_xlabel("Lead hour")
    ax.set_ylabel("Lightning CSI (16 km cell, per hour)")
    ax.set_title("0-6 h lightning skill: model vs baselines" + (f" (switch after hour {switch_hour})" if switch_hour else ""))
    ax.legend(loc="upper right", bbox_to_anchor=(1.0, 0.9), fontsize=10)
    footnote(fig, "US held-out test storms (SEVIR, Jun 2019 onward). Higher is better.")
    save(fig, out, "fig1_scorecard.png")

    cols = [k for k in ("full", "tier2_model", "radar", "persistence", "hrrr_ltng", "hrrr_refc") if k in rows]
    lines = ["| lead hour | " + " | ".join(SERIES[c][0] for c in cols) + " |", "|---|" + "---|" * len(cols)]
    for h in hours:
        lines.append(f"| {h} | " + " | ".join(f"{rows[c][h]:.3f}" if h in rows[c] else "-" for c in cols) + " |")
    lines += ["", f"Switch hour: {switch_hour}", "", LABEL]
    Path(out, "scorecard.md").write_text("\n".join(lines) + "\n")
    print("wrote", os.path.join(out, "scorecard.md"))
    return switch_hour


def csi_vs_lead(res, out):
    t1 = load(res, "full")
    if t1 is None:
        return
    lead = t1["lead_minutes"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 5.2))
    for key in ("full", "radar", "persistence"):
        r = load(res, key)
        if r is None:
            continue
        label, color, ls = SERIES[key]
        y1, y2 = r["lght"]["tol0"]["csi_per_lead"], r["vil"]["pool1"]["csi_m_per_lead"]
        a1.plot(lead, y1, ls, color=color, label=label)
        a2.plot(lead, y2, ls, color=color, label=label)
        end_label(a1, lead[-1], y1[-1], label, color)
        end_label(a2, lead[-1], y2[-1], label, color)
    for ax, title, yl in ((a1, "Lightning (8 km cell, per 10 min)", "CSI"),
                          (a2, "Radar VIL (2 km pixel, mean over thresholds)", "CSI-mean")):
        ax.set_title(title)
        ax.set_xlabel("Lead time (min)")
        ax.set_ylabel(yl)
        ax.set_xticks([30, 60, 90, 120, 150, 180])
        ax.set_xlim(0, 235)
        ax.set_ylim(0, None)
    a1.legend(loc="upper right", fontsize=10)
    footnote(fig, "US held-out test storms. Strict per-pixel scores; higher is better.")
    save(fig, out, "fig2_csi_vs_lead.png")


def ablations(res, out):
    have = [(s, lab, hour_csi(load(res, s))) for s, lab in ABLATIONS]
    have = [(s, lab, v) for s, lab, v in have if v]
    if len(have) < 2:
        return
    hours = sorted({h for _, _, v in have for h in v})[:3]
    n, w = len(have), 0.26
    fig, ax = plt.subplots(figsize=(11, 0.62 * n + 1.8))
    y = np.arange(n)[::-1].astype(float)
    for j, h in enumerate(hours):
        vals = [v.get(h, np.nan) for _, _, v in have]
        ax.barh(y + (1 - j) * w, vals, height=w - 0.03, color=HOUR_RAMP[j], label=f"Hour {h}", zorder=3)
    ax.set_yticks(y)
    ax.set_yticklabels([lab for _, lab, _ in have])
    ax.grid(axis="y", visible=False)
    ax.set_xlim(0, None)
    ax.set_xlabel("Lightning CSI (16 km cell, per hour)")
    ax.set_title("Which inputs matter: skill with inputs removed")
    ax.legend(loc="lower right", fontsize=10, ncol=len(hours))
    footnote(fig, "Same trained model, inputs switched off at test time (it was trained with 15% input dropout).")
    save(fig, out, "fig3_ablations.png")


def india_mode(res, out):
    pairs = [("Tier 1", "full", "full_india_mode"), ("Tier 2", "ext", "ext_india_mode")]
    pairs = [(t, hour_csi(load(res, a)), hour_csi(load(res, b))) for t, a, b in pairs]
    pairs = [p for p in pairs if p[1] and p[2]]
    if not pairs:
        return
    fig, axes = plt.subplots(1, len(pairs), figsize=(6.2 * len(pairs), 5), squeeze=False)
    for ax, (tier, us, ind) in zip(axes[0], pairs):
        hs = sorted(us)
        x = np.arange(len(hs), dtype=float)
        ax.bar(x - 0.2, [us[h] for h in hs], 0.38, color=BLUE, label="US inputs (GOES, HRRR)", zorder=3)
        ax.bar(x + 0.2, [ind.get(h, np.nan) for h in hs], 0.38, color=ORANGE, label="INSAT-like + GFS-like inputs", zorder=3)
        ax.set_xticks(x)
        ax.set_xticklabels([f"Hour {h}" for h in hs])
        ax.grid(axis="x", visible=False)
        ax.set_ylim(0, None)
        ax.set_title(f"{tier}: cost of Indian-style inputs")
        ax.set_ylabel("Lightning CSI (16 km cell, per hour)")
    axes[0][0].legend(loc="upper right", fontsize=10)
    footnote(fig, "Coarser satellite (IR 4 km, WV 8 km, 15-30 min scans), GFS-like NWP (no LTNG/UH, ~24 km).")
    save(fig, out, "fig4_india_mode.png")


def examples(res, out, n_show):
    p = os.path.join(res, "full_examples.npz")
    if not os.path.exists(p):
        return
    z = np.load(p)
    strikes = z["lght_true"].reshape(len(z["lght_true"]), -1).sum(1, dtype=np.int64)  # uint8: never negate
    order = np.argsort(strikes)[::-1][:n_show]
    for rank, i in enumerate(order, 1):
        fig, axes = plt.subplots(3, 5, figsize=(15, 9.4))
        panels = [("Observed now", z["vil_in"][i, -1])] + [(f"Truth +{(k + 1) * 10} min", z["vil_true"][i, k]) for k in LEAD_IDX]
        for ax, (t, img) in zip(axes[0], panels):
            ax.imshow(img, origin="lower", cmap=VIL_CMAP, vmin=0, vmax=255)
            ax.set_title(t, fontsize=11)
        for ax, k in zip(axes[1][1:], LEAD_IDX):
            ax.imshow(z["vil_pred"][i, k], origin="lower", cmap=VIL_CMAP, vmin=0, vmax=255)
            ax.set_title(f"Model +{(k + 1) * 10} min", fontsize=11)
        for ax, k in zip(axes[2][1:], LEAD_IDX):
            im = ax.imshow(z["lght_prob"][i, k].astype(np.float32), origin="lower", cmap=PROB_CMAP, vmin=0, vmax=1)
            r, c = np.nonzero(z["lght_true"][i, k])
            ax.plot(c, r, "o", ms=4, mfc="none", mec=INK, mew=1)
            ax.set_title(f"Lightning +{(k + 1) * 10} min", fontsize=11)
        axes[1][0].text(0.5, 0.5, "Radar VIL\n(row 1: truth\nrow 2: model)", ha="center", va="center", fontsize=11, color=INK2)
        axes[2][0].text(0.5, 0.5, "Lightning\nprobability\n(o = observed\nGLM flashes)", ha="center", va="center",
                        fontsize=11, color=INK2)
        for ax in axes.flat:
            ax.set_xticks([])
            ax.set_yticks([])
            ax.grid(False)
            for s in ax.spines.values():
                s.set_visible(False)
        cb = fig.colorbar(im, ax=axes[2].tolist(), fraction=0.02, pad=0.01)
        cb.set_label("P(lightning)", color=INK2)
        fig.suptitle(f"Forecast example {rank}: 384 km tile, US test storm", x=0.01, ha="left", fontsize=14, fontweight="bold")
        footnote(fig, "North is up. VIL 0-255 (SEVIR scale).")
        save(fig, out, f"fig5_example_{rank}.png")


def _boundary_lines(path):
    """Line strings (lon, lat arrays) from a GeoJSON of polygons / lines."""
    gj = json.load(open(path))
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    lines = []
    for f in feats:
        g = f.get("geometry", f)
        t, c = g["type"], g["coordinates"]
        rings = {"LineString": [c], "MultiLineString": c, "Polygon": c,
                 "MultiPolygon": [r for poly in c for r in poly]}.get(t, [])
        lines += [np.asarray(r, float) for r in rings if len(r) > 1]
    return lines


def _provenance_lines(prov):
    """Short 'input: what was used' lines from the provenance block of an India run."""
    out = []
    sat = prov.get("satellite") or {}
    if isinstance(sat, dict) and sat.get("scans"):
        name = str(sat.get("source", "satellite")).split("(")[0].split(";")[0].strip()
        times = [s["scan"][11:16] for s in sat["scans"]]
        when = f"scan at {times[0]}" if len(times) == 1 else f"{len(times)} scans {times[0]}-{times[-1]}"
        out.append(f"Satellite: {name}, {when} UTC")
    else:
        out.append("Satellite: missing")
    for key, label in (("radar", "Radar"), ("lightning", "Lightning")):
        v = prov.get(key) or {}
        status = v.get("status", "missing") if isinstance(v, dict) else str(v)
        out.append(f"{label}: {'none' if status == 'missing' else status}")
    nwp = prov.get("nwp")
    if isinstance(nwp, list) and nwp:
        ok = [r for r in nwp if r.get("status") == "ok"]
        if ok:
            fx = [r["fxx"] for r in ok]
            out.append(f"NWP: {ok[0]['model'].upper()} {ok[0]['init'][11:13]}Z run, +{min(fx)} to +{max(fx)} h")
        else:
            out.append("NWP: missing")
    return out


def india_cases(res, out, boundary):
    from nowcast.india.tiles import CITIES, city_tile, make_tile, tile_grid

    lines = _boundary_lines(boundary) if boundary else []
    for npz in sorted(glob.glob(os.path.join(res, "india", "*.npz"))):
        stem = Path(npz).stem
        meta = json.load(open(npz[:-4] + ".json")) if os.path.exists(npz[:-4] + ".json") else {}
        tile_id, when = stem.rsplit("_", 1)
        if tile_id in CITIES:
            tile, point = city_tile(tile_id), CITIES[tile_id]
        else:
            lat, lon = map(float, tile_id.split("_")[1:3])
            tile, point = make_tile(lat, lon), (lat, lon)
        z = np.load(npz)
        summary = meta.get("summary", [])
        src = {s["lead_hour"]: s["source"] for s in summary}
        maps = {}
        for h in range(1, 7):
            key = f"{src.get(h, 'tier1')}_hour{h}_16km"
            key = key if key in z.files else next((k for k in (f"tier1_hour{h}_16km", f"tier2_hour{h}_16km") if k in z.files), None)
            if key:
                maps[h] = (key.split("_")[0], z[key].astype(np.float32))
        if not maps:
            continue

        hours = sorted(maps)
        n_rows = (len(hours) + 2) // 3
        fig = plt.figure(figsize=(15, 3.6 * n_rows + 3.8))
        gs = fig.add_gridspec(n_rows + 1, 4, height_ratios=[1] * n_rows + [0.85], hspace=0.38, wspace=0.12)
        n = next(iter(maps.values()))[1].shape[0]
        lat, lon = tile_grid(tile, n)
        for j, h in enumerate(hours):
            ax = fig.add_subplot(gs[j // 3, j % 3])
            tier, grid = maps[h]
            im = ax.pcolormesh(lon, lat, grid, cmap=PROB_CMAP, vmin=0, vmax=1, shading="nearest")
            for ln in lines:
                ax.plot(ln[:, 0], ln[:, 1], color=INK2, lw=0.8)
            ax.plot(point[1], point[0], marker="*", ms=13, color=INK, mec=SURFACE, mew=1.2)
            ax.set_xlim(lon.min(), lon.max())
            ax.set_ylim(lat.min(), lat.max())
            ax.set_aspect(1 / np.cos(np.deg2rad(point[0])))
            ax.set_title(f"Hour {h} ({'tier 1' if tier == 'tier1' else 'tier 2'})", fontsize=11)
            ax.tick_params(labelsize=8.5)
        cb = fig.colorbar(im, ax=fig.axes, fraction=0.015, pad=0.01)
        cb.set_label("P(lightning in 16 km cell during the hour)", color=INK2)

        ax = fig.add_subplot(gs[n_rows, :3])
        if summary:
            hs = [s["lead_hour"] for s in summary]
            ps = [s["p_lightning_at_location"] for s in summary]
            cols = [BLUE if s["source"] == "tier1" else ORANGE for s in summary]
            ax.bar(hs, ps, color=cols, width=0.6, zorder=3)
            for thr, name in ((0.5, "HIGH"), (0.2, "MODERATE")):
                ax.axhline(thr, color=MUTED, lw=1, ls="--", zorder=2)
                ax.text(6.45, thr + 0.015, name, va="bottom", fontsize=9.5, color=INK2)
            ax.set_xticks(range(1, 7))
            ax.set_xlim(0.5, 7.1)
            ax.set_ylim(0, 1)
            ax.grid(axis="x", visible=False)
            ax.set_xlabel("Lead hour")
            ax.set_ylabel("P(lightning) at the city")
            used = [t for t in ("tier1", "tier2") if t in {s["source"] for s in summary}]
            ax.legend(handles=[Patch(color=BLUE if t == "tier1" else ORANGE, label=t.replace("tier", "tier "))
                               for t in used], loc="upper right", fontsize=10, ncol=2)
            ax.set_title("Risk timeline at the marked location", fontsize=12)
        info = _provenance_lines(meta.get("provenance", {}))
        fig.text(0.74, 0.3 / (n_rows + 0.85) * 0.85 + 0.02, "Inputs used\n" + "\n".join(info), fontsize=10,
                 color=INK2, va="bottom", linespacing=1.5)
        name = tile_id if tile_id in CITIES else f"{point[0]:.2f}N {point[1]:.2f}E"
        fig.suptitle(f"{name}, issued {when[:4]}-{when[4:6]}-{when[6:8]} {when[9:11]}:{when[11:13]} UTC",
                     x=0.01, ha="left", fontsize=15, fontweight="bold")
        footnote(fig, "Boundaries: Survey of India." if lines else "Boundaries not drawn (pass --boundary).")
        save(fig, out, f"fig6_india_{stem}.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="results")
    ap.add_argument("--out", default="figures")
    ap.add_argument("--switch-hour", type=int, help="default: first hour where tier 2 beats tier 1, minus one")
    ap.add_argument("--boundary", help="GeoJSON of official India boundaries (Survey of India depiction)")
    ap.add_argument("--examples", type=int, default=4, help="forecast example figures to draw")
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    style()
    sh = scorecard(args.results, args.out, args.switch_hour)
    csi_vs_lead(args.results, args.out)
    ablations(args.results, args.out)
    india_mode(args.results, args.out)
    examples(args.results, args.out, args.examples)
    india_cases(args.results, args.out, args.boundary)
    if sh is not None:
        print(f"switch hour used: {sh}")


if __name__ == "__main__":
    main()
