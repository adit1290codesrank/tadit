"""Slide 3: TECHNICAL APPROACH (architecture flow, methodology, evidence, tech stack)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckkit import *  # noqa: F401,F403

ASSETS = Path(__file__).resolve().parent.parent / "assets"

INPUTS = [("radar", "Radar", "NEXRAD VIL (training); IMD DWR reader built, not yet on live data", BLUE),
          ("sat", "Satellite", "INSAT-3DR/3DS · GK2A · GOES IR", VIOLET),
          ("zap", "Lightning", "GLM (training); ILDN partnership offered", "E3A000"),
          ("globe", "Weather model", "GFS 0.25° · HRRR", GREEN)]

PREP = ["384 km tiles on one map grid",
        "Radar / satellite at 2 km, lightning at 8 km",
        "Leak-free lightning labels (past 5 min only)",
        "NWP only from runs issued before the forecast",
        "50% of samples degraded to INSAT & GFS quality"]

METHOD = [
    ("database", "Data", "3,000 real US storm events (SEVIR) + HRRR; split by date, so test storms are unseen."),
    ("cpu", "Train", "Intensity-weighted radar loss + focal lightning loss; modality dropout; one night on an RTX 5060 Ti."),
    ("search", "Evaluate", "CSI / POD / FAR per lead hour vs persistence and raw NWP; drop-a-sensor tests."),
    ("pin", "India", "Run on INSAT / GK2A + GFS; checked against FY-4A satellite lightning."),
    ("cloud", "Serve", "Maps + JSON exported to a static web app on Cloudflare Pages."),
]

STACK = [("AI / ML", ["Python", "PyTorch", "NumPy", "bf16"], BLUE),
         ("Data", ["xarray", "h5py", "s3fs", "Herbie", "pyproj", "cfgrib"], GREEN),
         ("Web", ["React", "TypeScript", "Vite", "MapLibre GL"], VIOLET),
         ("Infra", ["AWS Open Data", "Cloudflare Pages", "RTX 5060 Ti (16 GB)"], SAFFRON)]


def build(slide):
    S = Slide(slide)
    reset_slide(slide)
    X0, X1 = 0.25, 13.08

    # ================= architecture band
    at, ab = 1.2, 4.08
    S.box(X0, at, X1 - X0, ab - at, fill=PANEL, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
    S.text(X0 + 0.15, at + 0.06, 6, 0.22, "**System architecture:** from raw observations to a 0–6 h lightning forecast",
           size=10, color=MUTED, bold_color=NAVY, font=HEAD)

    # inputs
    ix, iw, iy = X0 + 0.12, 2.05, at + 0.38
    stage_label(S, ix, iy, iw, "1 · DATA SOURCES", NAVY)
    for k, (ic, t, sub, col) in enumerate(INPUTS):
        y = iy + 0.26 + k * 0.56
        S.box(ix, y, iw, 0.5, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.15, shadow=True)
        S.bubble(ic, ix + 0.26, y + 0.25, 0.34, col, pad=0.2)
        S.text(ix + 0.5, y + 0.03, iw - 0.55, 0.2, t, size=9, color=col, font=HEAD, bold=True)
        S.text(ix + 0.5, y + 0.21, iw - 0.55, 0.28, sub, size=6.3, color=MUTED, spacing=0.85)
    arrow(S, ix + iw + 0.04, iy + 1.35, 0.26)

    # preprocessing
    px, pw = ix + iw + 0.34, 2.0
    stage_label(S, px, iy, pw, "2 · PREPROCESSING", NAVY)
    S.box(px, iy + 0.26, pw, 2.18, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08, shadow=True)
    for k, t in enumerate(PREP):
        y = iy + 0.36 + k * 0.415
        S.bubble("check", px + 0.2, y + 0.14, 0.2, TEAL, pad=0.12)
        S.text(px + 0.36, y, pw - 0.44, 0.38, t, size=7.8, color=INK2, anchor=MSO_ANCHOR.MIDDLE, spacing=0.9)
    arrow(S, px + pw + 0.04, iy + 0.78, 0.26)
    arrow(S, px + pw + 0.04, iy + 2.02, 0.26)

    # models
    mx, mw = px + pw + 0.34, 5.02
    stage_label(S, mx, iy, mw, "3 · AI MODELS", NAVY)
    # tier 1
    t1y, t1h = iy + 0.26, 1.28
    S.box(mx, t1y, mw, t1h, fill="EAF2FC", line=BLUE, lw=1.25, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    S.text(mx + 0.12, t1y + 0.05, mw - 0.2, 0.2, "**TIER 1 · Fusion nowcaster** (0–3 h, 10-min steps)",
           size=9.5, color=BLUE, bold_color=BLUE, font=HEAD)
    S.text(mx + mw - 1.95, t1y + 0.07, 1.85, 0.18, "60M params · modality dropout", size=7, color=MUTED,
           align=PP_ALIGN.RIGHT)
    chips = [("Per-source encoders", "each sensor at native res."),
             ("Gated fusion", "+ ‘missing’ embeddings"),
             ("U-Net + attention", "NWP cross-attn · FiLM"),
             ("18 lead times", "VIL 2 km · lightning 8 km")]
    cw = (mw - 0.24 - 3 * 0.2) / 4
    for k, (a, b) in enumerate(chips):
        x = mx + 0.12 + k * (cw + 0.2)
        S.box(x, t1y + 0.36, cw, 0.8, fill=WHITE, line="B9D1EE", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.14)
        S.text(x + 0.05, t1y + 0.42, cw - 0.1, 0.34, a, size=8.2, color=NAVY, font=HEAD, bold=True, align=PP_ALIGN.CENTER,
               anchor=MSO_ANCHOR.MIDDLE, spacing=0.9)
        S.text(x + 0.05, t1y + 0.78, cw - 0.1, 0.34, b, size=6.8, color=MUTED, align=PP_ALIGN.CENTER, spacing=0.9)
        if k < 3:
            S.icon("arrow_blue", x + cw + 0.02, t1y + 0.68, 0.16)
    # tier 2
    t2y, t2h = t1y + t1h + 0.1, 0.8
    S.box(mx, t2y, mw, t2h, fill="E7F5F5", line=TEAL, lw=1.25, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    S.text(mx + 0.12, t2y + 0.05, mw - 0.2, 0.2, "**TIER 2 · AI-corrected NWP** (lead hours 1–6)", size=9.5,
           color=TEAL, bold_color=TEAL, font=HEAD)
    chips2 = ["GFS / HRRR forecast fields", "Compact U-Net", "Lightning + VIL, 16 km"]
    cw2 = (mw - 0.24 - 2 * 0.2) / 3
    for k, a in enumerate(chips2):
        x = mx + 0.12 + k * (cw2 + 0.2)
        S.box(x, t2y + 0.33, cw2, 0.38, fill=WHITE, line="B5DCDC", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3)
        S.text(x, t2y + 0.33, cw2, 0.38, a, size=7.8, color=NAVY, font=HEAD, bold=True, align=PP_ALIGN.CENTER,
               anchor=MSO_ANCHOR.MIDDLE)
        if k < 2:
            S.icon("arrow_teal", x + cw2 + 0.02, t2y + 0.44, 0.16)
    arrow(S, mx + mw + 0.04, t1y + 0.6, 0.26)
    arrow(S, mx + mw + 0.04, t2y + 0.3, 0.26)

    # blend + outputs
    ox, ow = mx + mw + 0.34, X1 - 0.12 - (mx + mw + 0.34)
    stage_label(S, ox, iy, ow, "4 · SEAMLESS OUTPUT", NAVY)
    S.box(ox, iy + 0.26, ow, 0.92, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1, shadow=True)
    S.text(ox + 0.1, iy + 0.3, ow - 0.2, 0.84,
           ["**Switch at hour 3**", "Tier 1 for hours 1–3, Tier 2 for 4–6: the crossover measured on held-out storms."],
           size=7.8, color="CFE0F5", bold_color="FFD166", anchor=MSO_ANCHOR.MIDDLE, spacing=0.92, space_after=2)
    outs = [("map", "Probability maps"), ("code", "JSON: hourly risk + sources used"), ("users", "Tadit web app & alerts")]
    for k, (ic, t) in enumerate(outs):
        y = iy + 1.26 + k * 0.4
        S.box(ox, y, ow, 0.34, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3)
        S.bubble(ic, ox + 0.18, y + 0.17, 0.24, SAFFRON, pad=0.18)
        S.text(ox + 0.36, y, ow - 0.4, 0.34, t, size=7.6, color=INK, font=HEAD, bold=True, anchor=MSO_ANCHOR.MIDDLE)

    # ================= bottom row
    bt, bb = ab + 0.1, 6.86
    # methodology
    mx0, mw0 = X0, 4.1
    S.box(mx0, bt, mw0, bb - bt, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05, shadow=True)
    panel_head(S, mx0, bt, mw0, "Methodology", BLUE)
    rh = (bb - bt - 0.42) / len(METHOD)
    for k, (ic, t, txt) in enumerate(METHOD):
        y = bt + 0.38 + k * rh
        S.bubble(ic, mx0 + 0.27, y + rh / 2, 0.32, BLUE, pad=0.2)
        S.text(mx0 + 0.52, y, mw0 - 0.62, rh, f"**{t}:** {txt}", size=8, color=INK2, anchor=MSO_ANCHOR.MIDDLE, spacing=0.92)

    # evidence images
    ex, ew = mx0 + mw0 + 0.12, 4.9
    S.box(ex, bt, ew, bb - bt, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05, shadow=True)
    panel_head(S, ex, bt, ew, "Forecasts vs Reality", SAFFRON)
    S.text(ex + 0.12, bt + 0.37, ew - 0.24, 0.3,
           ["**Held-out US storm:** forecast lightning chance (shading) vs observed flashes (o)",
            "**Oklahoma City, 26 Aug 2019:** CSI **0.61 / 0.54 / 0.55** for hours 1–3 vs persistence 0.52 / 0.33 / 0.18"],
           size=7.1, color=MUTED, bold_color=INK, spacing=0.9)
    h1 = (bb - bt - 0.7 - 0.26 - 0.06) / 2
    w1 = h1 * 1810 / 455
    S.image(ASSETS / "fig5_lightning_row.png", ex + (ew - w1) / 2, bt + 0.7, w1, h1)
    y2 = bt + 0.7 + h1 + 0.06
    S.text(ex + 0.12, y2, ew - 0.24, 0.16, "**India, Bhubaneswar 2 Sep 2023:** hours 1–3 from satellite + GFS only (★ city)",
           size=7.3, color=MUTED, bold_color=INK)
    h2 = bb - 0.06 - (y2 + 0.18)
    w2 = h2 * 1675 / 540
    S.image(ASSETS / "fig6_bbsr_h123.png", ex + (ew - w2) / 2, y2 + 0.18, w2, h2)

    # tech stack
    tx, tw = ex + ew + 0.12, X1 - (ex + ew + 0.12)
    S.box(tx, bt, tw, bb - bt, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05, shadow=True)
    panel_head(S, tx, bt, tw, "Technology Stack", GREEN)
    y = bt + 0.42
    for grp, items, col in STACK:
        S.text(tx + 0.12, y, tw - 0.2, 0.16, grp.upper(), size=7, color=col, font=HEAD, bold=True)
        y += 0.18
        x = tx + 0.12
        for it in items:
            wd = 0.16 + 0.056 * len(it)
            if x + wd > tx + tw - 0.1:
                x = tx + 0.12
                y += 0.24
            S.box(x, y, wd, 0.21, fill=tint(col), line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
            S.text(x, y, wd, 0.21, it, size=7.2, color=INK, font=HEAD, bold=True, align=PP_ALIGN.CENTER,
                   anchor=MSO_ANCHOR.MIDDLE)
            x += wd + 0.06
        y += 0.29


TINTS = {BLUE: "E3EEFB", GREEN: "E4F3E6", VIOLET: "ECE6F7", SAFFRON: "FDEBDD"}


def tint(col):
    return TINTS.get(col, "EEF2F7")


def stage_label(S, x, y, w, t, col):
    S.text(x, y, w, 0.2, t, size=7.8, color=col, font=HEAD, bold=True, align=PP_ALIGN.CENTER)


def panel_head(S, x, y, w, t, col):
    S.box(x, y, w, 0.32, fill=col, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3)
    S.box(x, y + 0.18, w, 0.14, fill=col)
    S.text(x + 0.12, y, w - 0.2, 0.32, t, size=11, color=WHITE, font=HEAD, bold=True, anchor=MSO_ANCHOR.MIDDLE)


def arrow(S, x, y, w):
    S.icon("arrow_navy", x, y - w / 2, w)
