"""Slide 2: IDEA TITLE (proposed solution, how it addresses the problem, innovation)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckkit import *  # noqa: F401,F403

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SITE = "https://tadit.pages.dev/"

SOLUTION = [  # (icon, text)
    ("layers", "**Multimodal AI fusion:** one model reads Doppler radar, INSAT / GK2A satellite imagery, lightning strikes "
               "and GFS weather-model fields together."),
    ("clock", "**Seamless 0–6 h:** Tier 1 deep-learning nowcast in 10-min steps for 0–3 h, then Tier 2 AI-corrected "
              "NWP hourly for hours 4–6, switching at the measured crossover hour."),
    ("map", "**What it delivers:** lightning probability per 16 km cell, radar-like storm intensity at 2 km, and "
            "LOW / MODERATE / HIGH risk with plain advice for each city."),
    ("wifioff", "**Built for India’s gaps:** keeps working without radar or a lightning feed; runs today on "
                "INSAT-3DR/3DS or GK2A satellite + GFS."),
    ("users", "**Working prototype:** the Tadit web app shows an animated India map and hourly city risk, live at "
              f"[tadit.pages.dev]({SITE})."),
]

ADDRESSES = [  # (headline, text)
    ("3 h → 6 h", "IMD’s nowcasts look 3 h ahead. Tadit forecasts **6 h**: 10-min steps to 3 h, then hourly."),
    ("No radar? Still works", "Large parts of India lack radar. Satellite + NWP alone reaches **0.461** CSI at hour 1."),
    ("From maps to action", "City-level hourly risk with advice (“go indoors now”) for officials and the public."),
]

INNOVATION = [
    "**Mid-fusion U-Net** with NWP cross-attention + FiLM: all 18 lead times in one pass.",
    "**Modality dropout:** robust to any missing sensor, with free drop-a-sensor tests.",
    "**Measured tier crossover** stitches nowcast and NWP into one 0–6 h product.",
    "**India-adapted in training** (INSAT / GFS-like inputs) with leak-free lightning labels.",
]

FLOW = [("sat", "Observe", "radar, satellite, lightning, NWP", BLUE),
        ("layers", "Fuse", "one multimodal AI model", VIOLET),
        ("zap", "Forecast", "10-min steps to 3 h, hourly to 6 h", SAFFRON),
        ("alert", "Alert", "city risk + advice", RED)]


def build(slide):
    S = Slide(slide)
    reset_slide(slide)
    set_title(slide, "TADIT: AI LIGHTNING NOWCASTING", size=32)
    X0, X1 = 0.25, 13.08

    # ---------------- tagline bar
    S.box(X0, 1.2, X1 - X0, 0.44, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5, shadow=True)
    S.icon("zap_FFB400", X0 + 0.14, 1.27, 0.3)
    S.text(X0 + 0.52, 1.2, 9.4, 0.44,
           "**Tadit** (तड़ित = lightning) fuses **radar, satellite, lightning and weather-model** data "
           "into one AI that forecasts **where lightning will strike**, in 10-min steps to 3 h and hourly to 6 h.",
           size=10, color="DCE6F2", bold_color="FFD166", anchor=MSO_ANCHOR.MIDDLE)
    S.box(10.2, 1.27, 2.78, 0.3, fill=BOLT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    S.text(10.2, 1.27, 2.78, 0.3, f"[Live prototype: tadit.pages.dev]({SITE})", size=9.5, font=HEAD, bold=True,
           align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    # the link run inherits LINK colour; make it navy on the yellow pill
    for r in slide.shapes[-1].text_frame.paragraphs[0].runs:
        r.font.color.rgb = rgb(NAVY)

    top, bot = 1.74, 6.86
    # ---------------- col 1: proposed solution
    c1x, c1w = X0, 4.05
    S.box(c1x, top, c1w, bot - top, fill=PANEL, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
    header(S, c1x, top, c1w, "Proposed Solution", BLUE, "cpu")
    rh = (bot - top - 0.5) / len(SOLUTION)
    for k, (ic, txt) in enumerate(SOLUTION):
        y = top + 0.46 + k * rh
        S.box(c1x + 0.1, y, c1w - 0.2, rh - 0.07, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
        S.bubble(ic, c1x + 0.36, y + (rh - 0.07) / 2, 0.36, BLUE, pad=0.2)
        S.text(c1x + 0.62, y + 0.04, c1w - 0.8, rh - 0.15, txt, size=9.3, color=INK2, anchor=MSO_ANCHOR.MIDDLE, spacing=0.93)

    # ---------------- col 2: prototype + flow + proof
    c2x, c2w = 4.42, 4.95
    img = ASSETS / "site_bhubaneswar_city.png"
    fh = c2w * 900 / 1600
    S.box(c2x, top, c2w, 0.24 + fh, fill="1C2430", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04, shadow=True)
    for k, col in enumerate(("FF5F57", "FEBC2E", "28C840")):
        S.box(c2x + 0.12 + k * 0.13, top + 0.075, 0.09, 0.09, fill=col, shape=MSO_SHAPE.OVAL)
    S.box(c2x + 0.58, top + 0.045, 2.2, 0.15, fill="2E3846", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    S.text(c2x + 0.58, top + 0.045, 2.2, 0.15, "tadit.pages.dev", size=6.5, color="C9D3E0", align=PP_ALIGN.CENTER,
           anchor=MSO_ANCHOR.MIDDLE)
    pic = S.image(img, c2x + 0.03, top + 0.24, c2w - 0.06, fh - 0.03)
    pic.click_action.hyperlink.address = SITE
    cy = top + 0.24 + fh + 0.05
    S.text(c2x, cy, c2w, 0.2, "Working prototype: Bhubaneswar lightning outbreak, 2 Sep 2023, forecast issued 13:30 IST "
           "(satellite + GFS, no radar)", size=7.3, color=MUTED, italic=True, align=PP_ALIGN.CENTER)

    fy = cy + 0.3
    fw = (c2w - 3 * 0.26) / 4
    for k, (ic, t, sub, col) in enumerate(FLOW):
        x = c2x + k * (fw + 0.26)
        S.box(x, fy, fw, 0.92, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12, shadow=True)
        S.bubble(ic, x + fw / 2, fy + 0.25, 0.36, col, pad=0.2)
        S.text(x, fy + 0.46, fw, 0.18, t, size=9.5, color=col, font=HEAD, bold=True, align=PP_ALIGN.CENTER)
        S.text(x + 0.04, fy + 0.64, fw - 0.08, 0.26, sub, size=7, color=MUTED, align=PP_ALIGN.CENTER, spacing=0.9)
        if k < 3:
            S.bubble("arrow", x + fw + 0.13, fy + 0.46, 0.2, NAVY, pad=0.18)

    py = fy + 1.02
    S.box(c2x, py, c2w, bot - py, fill="EEF4FC", line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    stats = [("0.613", "lightning CSI at hour 1, 1.8× persistence"),
             ("6 / 6", "lead hours beating raw NWP lightning"),
             ("India", "beats persistence vs FY-4A satellite lightning")]
    sw = c2w / 3
    for k, (n, lab) in enumerate(stats):
        x = c2x + k * sw
        S.text(x + 0.08, py + 0.05, sw - 0.16, 0.3, n, size=15, color=BLUE, font=BLACK, align=PP_ALIGN.CENTER)
        S.text(x + 0.1, py + 0.36, sw - 0.2, 0.3, lab, size=7.2, color=INK2, align=PP_ALIGN.CENTER, spacing=0.9)

    # ---------------- col 3: addresses + innovation
    c3x, c3w = 9.49, X1 - 9.49
    a_bot = 4.36
    S.box(c3x, top, c3w, a_bot - top, fill=PANEL, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    header(S, c3x, top, c3w, "How It Addresses the Problem", GREEN, "target")
    ah = (a_bot - top - 0.5) / 3
    for k, (hd, txt) in enumerate(ADDRESSES):
        y = top + 0.46 + k * ah
        S.box(c3x + 0.1, y, c3w - 0.2, ah - 0.07, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.14)
        S.bubble("check", c3x + 0.3, y + 0.2, 0.24, GREEN, pad=0.14)
        S.text(c3x + 0.48, y + 0.07, c3w - 0.62, 0.2, hd, size=9.5, color=GREEN, font=HEAD, bold=True)
        S.text(c3x + 0.2, y + 0.31, c3w - 0.36, ah - 0.36, txt, size=8.3, color=INK2, spacing=0.9)

    i_top = a_bot + 0.1
    S.box(c3x, i_top, c3w, bot - i_top, fill=PANEL, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    header(S, c3x, i_top, c3w, "Innovation & Uniqueness", SAFFRON, "gift")
    ih = (bot - i_top - 0.5) / 4
    for k, txt in enumerate(INNOVATION):
        y = i_top + 0.46 + k * ih
        S.box(c3x + 0.1, y + ih / 2 - 0.14, 0.28, 0.28, fill=SAFFRON, shape=MSO_SHAPE.OVAL)
        S.text(c3x + 0.1, y + ih / 2 - 0.14, 0.28, 0.28, str(k + 1), size=9, color=WHITE, font=HEAD, bold=True,
               align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        S.text(c3x + 0.46, y, c3w - 0.56, ih, txt, size=8.3, color=INK2, anchor=MSO_ANCHOR.MIDDLE, spacing=0.92)


def header(S, x, y, w, title, col, ic):
    S.box(x, y, w, 0.38, fill=col, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3)
    S.box(x, y + 0.22, w, 0.16, fill=col)
    S.icon(ic, x + 0.13, y + 0.07, 0.24)
    S.text(x + 0.46, y, w - 0.5, 0.38, title, size=12, color=WHITE, font=HEAD, bold=True, anchor=MSO_ANCHOR.MIDDLE)
