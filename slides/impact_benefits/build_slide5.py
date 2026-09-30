"""Build the IMPACT AND BENEFITS slide (slide 5) into the SIH idea deck.

Usage: python slides/impact_benefits/build_slide5.py <in.pptx> <out.pptx>

Keeps the template's title, team-name oval, SIH logo and footer; replaces the
placeholder body text with native, editable shapes and a native line chart.
Numbers come from results/RESULTS.md (frozen 29 Sep 2026) and NCRB ADSI 2023.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_MARKER_STYLE
from pptx.enum.dml import MSO_LINE_DASH_STYLE
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from deckkit import *  # noqa: F401,F403  (palette, fonts, Slide helpers)


# ---------------------------------------------------------------- content
AUDIENCE = [  # (side, row, color, icon, title, subtitle, body)
    ("l", 0, BLUE, "landmark", "IMD Forecasters", "MoES · forecast centres",
     "Storm and lightning maps in **10-min steps at 2 km**. **Doubles the nowcast window**, 3 h to **6 h**."),
    ("l", 1, RED, "shield", "Disaster Managers", "NDMA · SDMAs · districts",
     "**Earlier, district-level alerts** to clear fields, fairs, beaches and schools **before the first strike**."),
    ("l", 2, GREEN, "sprout", "Farmers & Labourers", "most exposed, out in the open",
     "**Hours, not minutes**, to leave fields and shelter livestock, via **Damini** and **Meghdoot** apps."),
    ("r", 0, VIOLET, "plane", "Aviation & Airports", "AAI · airlines · IAF",
     "Storm hazard maps for **rerouting and safer ground operations**, with fewer diversions and go-arounds."),
    ("r", 1, SAFFRON, "pole", "Power & Telecom", "grid, towers, rail signalling",
     "**Pre-position repair crews** and shield lines, towers and signalling from **lightning and squalls**."),
    ("r", 2, TEAL, "users", "Citizens & Cities", "hyper-local alerts",
     "**Tested on Bhubaneswar, Kolkata and Guwahati storms**, plus a dry-day control in Delhi."),
]

BENEFITS = [  # (color, icon, label, body)
    (RED, "heart", "Social",
     "**Saves lives** where lightning strikes hardest: **MP, Bihar, Odisha, UP and Jharkhand** account for "
     "**59%** of India’s lightning deaths. Timely alerts build **public trust in IMD warnings**."),
    (AMBER, "rupee", "Economic",
     "Cuts losses to **crops, livestock, flights and power grids**. Built on **existing and open data** "
     "(IMD radar, INSAT, GFS): **no new sensors** are needed, and the model runs on a **single GPU**."),
    (GREEN, "leaf", "Environmental",
     "Flags **lightning-prone zones for forest-fire watch**, supports **climate adaptation** as severe "
     "convective weather grows, and helps **solar and grid operators** plan for storms."),
    (BLUE, "sat", "Strategic",
     "**Atmanirbhar:** runs on India’s own **INSAT-3DR/3DS** satellites and GFS, and **keeps forecasting when "
     "radar or lightning feeds drop out**, so it covers districts **beyond radar range**."),
]

KPIS = [  # (color, tint, number, label, detail)
    (BLUE, "EEF4FC", "1.8×", "better than persistence at hour 1", "Lightning CSI 0.613 vs 0.341; the gap grows to 5.5× by hour 3"),
    (AMBER, "FDF5E8", "+70%", "over raw NWP lightning at hour 6", "CSI 0.297 vs 0.175, and ahead of NWP at every hour from 1 to 6"),
    (GREEN, "EEF7EF", "0.461", "hour-1 CSI with no radar", "Satellite + NWP only: the usual case outside Indian radar coverage"),
    (RED, "FCEFEF", "0.71 vs 0.04", "India: storm vs dry day", "Storm probability 1 h ahead: Bhubaneswar outbreak (2 Sep 2023) vs Delhi dry day"),
]

HOURS = ["1 h", "2 h", "3 h", "4 h", "5 h", "6 h"]
OURS = [0.613, 0.497, 0.440, 0.319, 0.305, 0.297]
NWP = [0.266, 0.222, 0.197, 0.186, 0.181, 0.175]
PERSIST = [0.341, 0.133, 0.080, None, None, None]


def build(slide):
    S = Slide(slide)

    reset_slide(slide)  # keep only the template's title, oval, logo and footer

    X0, X1 = 0.25, 13.08

    # ---------------- hazard banner
    by, bh = 1.20, 0.46
    S.box(X0, by, 9.55, bh, grad=("7A0E12", RED), grad_angle=0, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.18, shadow=True)
    S.icon("zap_FFB400", X0 + 0.12, by + 0.08, 0.30)
    S.text(X0 + 0.48, by, 1.7, bh, "2,558 lives", size=19, color="FFD166", font=BLACK, anchor=MSO_ANCHOR.MIDDLE)
    S.text(X0 + 2.12, by + 0.02, 7.3, bh - 0.04,
           "lost to **lightning in India in 2023**: **39.7%** of all deaths from forces of nature, the largest single share "
           "(NCRB). Today’s operational nowcasts look only **3 hours** ahead.",
           size=10, color="FFFFFF", bold_color="FFFFFF", anchor=MSO_ANCHOR.MIDDLE)
    S.box(9.88, by, X1 - 9.88, bh, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.18, shadow=True)
    S.text(10.02, by + 0.03, X1 - 10.14, bh - 0.06,
           ["**PS SIH26072 · MoES / IMD**", "Theme: Disaster Management"],
           size=9, color="CFE0F5", bold_color=WHITE, anchor=MSO_ANCHOR.MIDDLE)

    # ---------------- left panel: target audience
    py, ph = 1.76, 3.26
    lx, lw = X0, 7.37
    S.box(lx, py, lw, ph, fill=PANEL, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    S.bubble("target", lx + 1.93, py + 0.19, 0.26, SAFFRON, pad=0.18)
    S.text(lx + 2.12, py + 0.05, 4.5, 0.3, "Potential Impact on Target Audience", size=13, color=NAVY, font=HEAD, bold=True)

    cw, chh, gap = 2.47, 0.88, 0.08
    top = py + 0.38
    hx, hy, hr = lx + lw / 2, top + (3 * chh + 2 * gap) / 2, 0.78
    for side, row, col, ic, title, sub, body in AUDIENCE:
        cx = lx + 0.12 if side == "l" else lx + lw - 0.12 - cw
        cy = top + row * (chh + gap)
        S.box(cx, cy, cw, chh, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1, shadow=True)
        S.bubble(ic, cx + 0.26, cy + 0.24, 0.34, col)
        S.text(cx + 0.5, cy + 0.06, cw - 0.56, 0.2, title, size=10.5, color=col, font=HEAD, bold=True)
        S.text(cx + 0.5, cy + 0.26, cw - 0.56, 0.15, sub, size=7.5, color=MUTED)
        S.text(cx + 0.1, cy + 0.43, cw - 0.16, 0.42, body, size=8.3, color=INK2, spacing=0.92)
        # connector: card edge -> hub ring
        ex = cx + cw if side == "l" else cx
        ey = cy + chh * (0.78, 0.5, 0.22)[row]
        a = math.atan2(ey - hy, ex - hx)
        rx, ry = hx + (hr + 0.02) * math.cos(a), hy + (hr + 0.02) * math.sin(a)
        if row == 1:
            ry = ey
        S.line([(ex, ey), (rx, ry)], col, 1.5)
        S.dot(ex, ey, col)
        S.dot(rx, ry, col, d=0.07)

    # data-source chips above the hub
    S.text(hx - 1.0, top - 0.02, 2.0, 0.14, "4 DATA SOURCES", size=7, color=MUTED, font=HEAD, bold=True, align=PP_ALIGN.CENTER)
    chips = [("radar", "Radar", BLUE), ("sat", "Satellite", VIOLET), ("zap", "Lightning", "E3A000"), ("globe", "NWP", GREEN)]
    chw, chh2 = 0.86, 0.2
    for k, (ic, lab, col) in enumerate(chips):
        x = hx - chw - 0.04 + (k % 2) * (chw + 0.08)
        y = top + 0.15 + (k // 2) * (chh2 + 0.05)
        S.box(x, y, chw, chh2, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
        S.bubble(ic, x + 0.11, y + chh2 / 2, 0.16, col, pad=0.16)
        S.text(x + 0.23, y, chw - 0.25, chh2, lab, size=7.5, color=NAVY, font=HEAD, bold=True, anchor=MSO_ANCHOR.MIDDLE)

    # hub: radar-style ring + navy core
    S.box(hx - hr, hy - hr, 2 * hr, 2 * hr, grad=("DCE9F7", BLUE), grad_angle=315, shape=MSO_SHAPE.OVAL, shadow=True)
    for k in (0.62, 0.44):
        S.box(hx - hr * k - 0.12, hy - hr * k - 0.12, 2 * (hr * k + 0.12), 2 * (hr * k + 0.12), line="FFFFFF", lw=0.5, shape=MSO_SHAPE.OVAL)
    cr = hr - 0.14
    S.box(hx - cr, hy - cr, 2 * cr, 2 * cr, grad=("173B6B", NAVY), grad_angle=90, line=WHITE, lw=2.25, shape=MSO_SHAPE.OVAL)
    S.icon("cloudbolt_FFB400", hx - 0.14, hy - 0.52, 0.28)
    S.text(hx - 0.6, hy - 0.26, 1.2, 0.38, "0–6 h", size=24, color=WHITE, font=BLACK, align=PP_ALIGN.CENTER)
    S.text(hx - 0.6, hy + 0.14, 1.2, 0.3, ["seamless AI", "lightning nowcast"], size=8, color="CFE0F5", font=HEAD, bold=True,
           align=PP_ALIGN.CENTER, spacing=0.9)

    # tiers under the hub
    tw = 1.98
    for k, (lab, col) in enumerate([("Tier 1 · 0–3 h multimodal fusion", BLUE), ("Tier 2 · 3–6 h AI-corrected NWP", TEAL)]):
        y = hy + hr + 0.07 + k * 0.24
        S.box(hx - tw / 2, y, tw, 0.2, fill=col, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
        S.text(hx - tw / 2, y, tw, 0.2, lab, size=7.5, color=WHITE, font=HEAD, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    S.text(hx - 1.1, hy + hr + 0.55, 2.2, 0.14, "10-min steps to 3 h · hourly to 6 h", size=7, color=MUTED, align=PP_ALIGN.CENTER)

    # ---------------- right panel: benefits
    rx0, rw = 7.74, X1 - 7.74
    S.box(rx0, py, rw, ph, fill=PANEL, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
    S.bubble("gift", rx0 + 1.47, py + 0.19, 0.26, GREEN, pad=0.18)
    S.text(rx0 + 1.66, py + 0.05, 3.4, 0.3, "Benefits of the Solution", size=13, color=NAVY, font=HEAD, bold=True)
    bh2, bgap = 0.65, (2.80 - 4 * 0.65) / 3
    for k, (col, ic, lab, body) in enumerate(BENEFITS):
        y = top + k * (bh2 + bgap)
        x = rx0 + 0.12
        w = rw - 0.24
        S.box(x, y, w, bh2, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12, shadow=True)
        S.box(x, y, 0.98, bh2, fill=col, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
        S.box(x + 0.7, y, 0.28, bh2, fill=col)  # square off the tag's right edge
        S.icon(ic, x + 0.36, y + 0.07, 0.26)
        S.text(x, y + 0.37, 0.98, 0.2, lab, size=8.5, color=WHITE, font=HEAD, bold=True, align=PP_ALIGN.CENTER)
        S.text(x + 1.1, y + 0.04, w - 1.2, bh2 - 0.08, body, size=8.5, color=INK2, anchor=MSO_ANCHOR.MIDDLE, spacing=0.95)

    # ---------------- proof strip
    sy, sh_ = 5.12, 1.10
    S.box(X0, sy, 1.35, sh_, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    S.text(X0 + 0.12, sy + 0.1, 1.15, 0.42, ["Measured,", "not claimed"], size=11.5, color="FFD166", font=BLACK, spacing=0.9)
    S.text(X0 + 0.12, sy + 0.55, 1.15, 0.5, "Held-out 2019 storms scored against real satellite lightning (GLM).",
           size=7.5, color="CFE0F5", spacing=0.95)
    kx = X0 + 1.35 + 0.1
    kw = 1.85
    for col, tint, num, lab, det in KPIS:
        S.box(kx, sy, kw, sh_, fill=tint, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
        S.text(kx + 0.12, sy + 0.05, kw - 0.2, 0.36, num, size=19 if len(num) < 8 else 16, color=col, font=BLACK,
               anchor=MSO_ANCHOR.MIDDLE)
        S.text(kx + 0.12, sy + 0.42, kw - 0.2, 0.28, lab, size=8.5, color=INK, font=HEAD, bold=True, spacing=0.92)
        S.text(kx + 0.12, sy + 0.71, kw - 0.2, 0.36, det, size=7.3, color=MUTED, spacing=0.92)
        kx += kw + 0.1

    # chart card
    cx0, cw0 = kx, X1 - kx
    S.box(cx0, sy, cw0, sh_, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    S.text(cx0 + 0.1, sy + 0.05, cw0 - 0.2, 0.16, "**Lightning CSI by lead hour** (higher is better)", size=8, color=MUTED, bold_color=INK)
    add_chart(S, cx0 + 0.02, sy + 0.2, cw0 - 1.0, sh_ - 0.22)
    # legend column
    lgx, lgy = cx0 + cw0 - 0.96, sy + 0.3
    for k, (name, val, col, dash) in enumerate([("Our nowcast", "0.297 at 6 h", BLUE, False),
                                                ("Raw NWP", "0.175 at 6 h", "E8710A", False),
                                                ("Persistence", "0.080 at 3 h", "8A96A3", True)]):
        y = lgy + k * 0.25
        ln = S.line([(lgx, y + 0.06), (lgx + 0.16, y + 0.06)], col, 2)
        if dash:
            ln.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        S.text(lgx + 0.2, y, 0.76, 0.12, name, size=7, color=INK, font=HEAD, bold=True)
        S.text(lgx + 0.2, y + 0.11, 0.76, 0.12, val, size=6.5, color=MUTED)

    # ---------------- tagline + notes
    ty = 6.30
    S.box(X0, ty, X1 - X0, 0.3, grad=("FFF1E0", "E6F4E8"), grad_angle=0, line="E7D3B8", lw=1,
          shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    S.text(X0, ty, X1 - X0, 0.3,
           "“From a 3-hour to a 6-hour lightning warning: one seamless AI nowcast, built on India’s own satellites.”",
           size=13, color="1B1B1B", font="Times New Roman", bold=True, italic=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    S.icon("zap_F37021", X0 + 1.05, ty + 0.05, 0.2)
    S.icon("zap_138808", X1 - 1.25, ty + 0.05, 0.2)
    S.text(X0 + 0.1, 6.64, X1 - X0 - 0.2, 0.28,
           "CSI = critical success index for lightning in a 16 km cell during each lead hour; Tier 1 is used for hours 1–3 and Tier 2 for "
           "hours 4–6. India probabilities from GK2A satellite + GFS input, no radar. Trained on US GLM lightning, adapted to INSAT/GFS, "
           "not yet verified against Indian lightning observations. Death figures: NCRB, Accidental Deaths & Suicides in India 2023.",
           size=6.8, color="7A8594", align=PP_ALIGN.CENTER, spacing=0.95)


def add_chart(S, x, y, w, h):
    PL, PT, PW, PH = 0.13, 0.05, 0.84, 0.72   # plot-area fractions (inner), set below
    # tier bands behind the plot (the chart itself has no fill)
    px, pw = x + PL * w, PW * w
    ptop, pht = y + PT * h, PH * h
    mid = px + pw / 2
    S.box(px - 0.07, ptop - 0.02, mid - px + 0.07, pht + 0.04, fill="E8F1FB")
    S.box(mid, ptop - 0.02, px + pw + 0.07 - mid, pht + 0.04, fill="E6F4F4")
    S.text(mid - 0.64, ptop - 0.01, 0.6, 0.12, "TIER 1", size=6, color=BLUE, font=HEAD, bold=True, align=PP_ALIGN.RIGHT)
    S.text(px + pw + 0.03 - 0.6, ptop - 0.01, 0.6, 0.12, "TIER 2", size=6, color=TEAL, font=HEAD, bold=True, align=PP_ALIGN.RIGHT)

    cd = CategoryChartData()
    cd.categories = HOURS
    cd.add_series("Persistence", PERSIST)
    cd.add_series("Raw NWP (HRRR)", NWP)
    cd.add_series("Our nowcast", OURS)
    gf = S.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    ch = gf.chart
    ch.has_legend = False
    ch.has_title = False
    ch.font.size = Pt(6.5)
    ch.font.name = BODY
    ch.font.color.rgb = rgb(MUTED)
    styles = {"Persistence": ("8A96A3", 1.5, True, 4), "Raw NWP (HRRR)": ("E8710A", 1.75, False, 4), "Our nowcast": (BLUE, 2.5, False, 5)}
    for s in ch.plots[0].series:
        col, wd, dash, ms = styles[s.name]
        s.smooth = False
        s.format.line.color.rgb = rgb(col)
        s.format.line.width = Pt(wd)
        if dash:
            s.format.line.dash_style = MSO_LINE_DASH_STYLE.DASH
        s.marker.style = XL_MARKER_STYLE.CIRCLE
        s.marker.size = ms
        s.marker.format.fill.solid()
        s.marker.format.fill.fore_color.rgb = rgb(col)
        s.marker.format.line.color.rgb = rgb(WHITE)
    va = ch.value_axis
    va.minimum_scale, va.maximum_scale, va.major_unit = 0, 0.7, 0.2
    va.has_major_gridlines = True
    va.major_gridlines.format.line.color.rgb = rgb("D5DCE5")
    va.major_gridlines.format.line.width = Pt(0.5)
    va.format.line.fill.background()
    va.tick_labels.number_format = "0.0"
    va.tick_labels.number_format_is_linked = False
    ca = ch.category_axis
    ca.format.line.color.rgb = rgb("B8C2CE")
    ca.has_major_gridlines = False

    cs = ch._chartSpace
    C = "http://schemas.openxmlformats.org/drawingml/2006/chart"
    # points on tick marks, so hour 3.5 sits at the middle of the plot
    for cb in cs.iter(f"{{{C}}}crossBetween"):
        cb.set("val", "midCat")
    # no chart/plot fill (tier bands show through)
    for tag in ("chartSpace", "plotArea"):
        el = cs if tag == "chartSpace" else cs.find(f".//{{{C}}}plotArea")
        spPr = el.find(f"{{{C}}}spPr")
        if spPr is None:
            spPr = etree.Element(f"{{{C}}}spPr")
            if tag == "plotArea":  # after the axes
                ext = el.find(f"{{{C}}}extLst")
                ext.addprevious(spPr) if ext is not None else el.append(spPr)
            else:                  # right after c:chart, before c:txPr
                el.find(f"{{{C}}}chart").addnext(spPr)
        for child in list(spPr):
            spPr.remove(child)
        etree.SubElement(spPr, qn("a:noFill"))
        ln = etree.SubElement(spPr, qn("a:ln"))
        etree.SubElement(ln, qn("a:noFill"))
    # fixed inner plot layout
    pa = cs.find(f".//{{{C}}}plotArea")
    lay = pa.find(f"{{{C}}}layout")
    if lay is None:
        lay = etree.Element(f"{{{C}}}layout")
        pa.insert(0, lay)
    for c in list(lay):
        lay.remove(c)
    ml = etree.SubElement(lay, f"{{{C}}}manualLayout")
    for tag, val in (("layoutTarget", "inner"), ("xMode", "edge"), ("yMode", "edge"),
                     ("x", PL), ("y", PT), ("w", PW), ("h", PH)):
        etree.SubElement(ml, f"{{{C}}}{tag}", val=str(val))
    # gaps for missing persistence points
    chart_el = cs.find(f"{{{C}}}chart")
    dba = chart_el.find(f"{{{C}}}dispBlanksAs")
    if dba is None:
        dba = etree.SubElement(chart_el, f"{{{C}}}dispBlanksAs")
    dba.set("val", "gap")


def main(src, dst):
    prs = Presentation(src)
    slide = next(s for s in prs.slides
                 if any(sh.has_text_frame and "IMPACT AND BENEFITS" in sh.text_frame.text for sh in s.shapes))
    build(slide)
    prs.save(dst)
    print("wrote", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
