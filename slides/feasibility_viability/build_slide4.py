"""Build the FEASIBILITY AND VIABILITY slide (slide 4) into the SIH idea deck.

Usage: python slides/feasibility_viability/build_slide4.py <in.pptx> <out.pptx>

Safe to re-run on the same deck: everything except the template's title, team oval,
logo and footer is removed first. Facts come from results/RESULTS.md,
docs/PLAN.md and docs/DEPLOY.md.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pptx import Presentation

from deckkit import *  # noqa: F401,F403

COLUMNS = [  # (color, header icon, title, tagline, [(icon, text), ...])
    (BLUE, "cpu", "Technical Feasibility", "Built, trained and tested today", [
        ("layers", "**Working two-tier AI:** 60M-parameter fusion U-Net for 0–3 h plus an NWP post-processor for 3–6 h, "
                   "trained on 3,000 real storm events."),
        ("timer", "**Fast:** a full 0–6 h forecast takes **a few minutes per city**, mostly data download; the model itself "
                  "runs in seconds."),
        ("cpu", "**Light:** trained overnight on **one 16 GB consumer GPU**; the deployed model file is 120 MB."),
        ("code", "**Reliable build:** open-source Python / PyTorch stack, covered by **38 automated tests**."),
    ]),
    (GREEN, "plug", "Operational Feasibility", "Runs on India’s own data", [
        ("sat", "**Indian data readers:** INSAT, IMD radar, GFS and strike feeds; **INSAT and GFS verified on real files**."),
        ("shieldcheck", "**INSAT cross-checked:** our INSAT reader matches the GK2A satellite on the same scene (r = 0.87)."),
        ("wifioff", "**Works with gaps:** runs on whichever sources are live, and every output lists what it used."),
        ("map", "**Easy to plug in:** standard map + JSON outputs for IMD’s nowcast portal and alert apps; "
                "the web viewer needs no backend."),
    ]),
    (AMBER, "rupee", "Economic Viability", "Low cost, scalable, policy-aligned", [
        ("database", "**No new hardware:** reuses radar, satellite and NWP data IMD already collects; open GK2A / GFS as backup."),
        ("cloud", "**Near-zero serving cost:** forecasts are static files served from a free CDN (Cloudflare Pages)."),
        ("trend", "**Scales simply:** ≈30 tiles of 384 km cover India, and one GPU can refresh them all."),
        ("landmark", "**Policy fit:** supports MoES’s **Mission Mausam** (₹2,000 cr) goals of more frequent nowcasts "
                     "and no undetected weather events."),
    ]),
]

RISKS = [  # (icon, challenge, strategy)
    ("search",
     "**Limited access to data:** Indian lightning archives (ILLN / ILDN) and radar volumes are not openly available, "
     "so early findings may be misleading.",
     "**Improves with Indian data:** ILDN (Tripura University) has offered to partner and share lightning data for "
     "SIH-2026; "
     "**as the model gets validated data, it recalibrates and gets more accurate.**"),
    ("globe",
     "**Trained on US storms, used in India:** monsoon storms, terrain and INSAT’s slower scans differ from the "
     "US training data.",
     "**India-mode training:** half of all samples are degraded to INSAT (4 km, 15–30 min scans) and GFS (~24 km) "
     "quality; fine-tune on Indian cases as they come in."),
    ("wifioff",
     "**Sparse radar and sensor outages:** radar does not cover all of India, and feeds drop out during storms.",
     "**Modality dropout:** the model runs on whatever is live. Without radar, hour-1 CSI only dips from **0.613 to 0.592**; "
     "satellite + NWP alone still scores **0.461**."),
    ("sliders",
     "**Calibration and false alarms:** probabilities are tuned to US storm frequency, not Indian climate.",
     "**Regional recalibration** with IMD, and alerts issued as risk levels, not raw numbers. On a dry Delhi day the "
     "forecast stayed at **0.04**."),
    ("rocket",
     "**Adoption into IMD operations:** a new tool must fit forecasters’ workflows and existing alert channels.",
     "**Phased rollout:** pilot at one regional centre (e.g. Bhubaneswar) side by side with current nowcasts, then "
     "scale state by state."),
]


def build(slide):
    S = Slide(slide)
    reset_slide(slide)
    X0, X1 = 0.25, 13.08

    # ---------------- three columns
    ty, th, gap = 1.20, 2.22, 0.12
    cw = (X1 - X0 - 2 * gap) / 3
    for k, (col, hic, title, tag, rows) in enumerate(COLUMNS):
        x = X0 + k * (cw + gap)
        S.box(x, ty, cw, th, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05, shadow=True)
        S.box(x, ty, cw, 0.48, fill=col, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.22)
        S.box(x, ty + 0.3, cw, 0.18, fill=col)  # square off the header's lower corners
        S.icon(hic, x + 0.14, ty + 0.1, 0.28)
        S.text(x + 0.52, ty + 0.03, cw - 0.6, 0.26, title, size=12.5, color=WHITE, font=HEAD, bold=True)
        S.text(x + 0.52, ty + 0.27, cw - 0.6, 0.18, tag, size=8, color="F2F6FB", font=HEAD, italic=True)
        rh = (th - 0.48 - 0.1) / 4
        for j, (ic, txt) in enumerate(rows):
            ry = ty + 0.53 + j * rh
            S.bubble(ic, x + 0.25, ry + rh / 2, 0.3, col, pad=0.2)
            S.text(x + 0.48, ry, cw - 0.58, rh, txt, size=8.5, color=INK2, anchor=MSO_ANCHOR.MIDDLE, spacing=0.93)
            if j < 3:
                S.line([(x + 0.48, ry + rh), (x + cw - 0.12, ry + rh)], "E6ECF3", 0.75)

    # ---------------- challenges -> strategies
    hy = 3.54
    lx, lw = X0, 5.78
    mx = lx + lw           # connector lane
    rx = mx + 1.0
    rw = X1 - rx
    S.box(lx, hy, lw, 0.32, fill=RED, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    S.icon("alert", lx + 0.14, hy + 0.05, 0.22)
    S.text(lx + 0.45, hy, lw - 0.5, 0.32, "Potential Challenges & Risks", size=11.5, color=WHITE, font=HEAD, bold=True,
           anchor=MSO_ANCHOR.MIDDLE)
    S.box(rx, hy, rw, 0.32, fill=GREEN, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    S.icon("shieldcheck", rx + 0.14, hy + 0.05, 0.22)
    S.text(rx + 0.45, hy, rw - 0.5, 0.32, "Strategies to Overcome Them", size=11.5, color=WHITE, font=HEAD, bold=True,
           anchor=MSO_ANCHOR.MIDDLE)
    S.box(mx + 0.1, hy, 0.8, 0.32, fill=NAVY, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    S.icon("arrow", mx + 0.38, hy + 0.04, 0.24)

    rh, rg = 0.5, 0.045
    y0 = hy + 0.4
    for k, (ic, risk, fix) in enumerate(RISKS):
        y = y0 + k * (rh + rg)
        # challenge card
        S.box(lx, y, lw, rh, fill="FDF1F1", line="F2CFCF", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.18)
        S.box(lx + 0.08, y + rh / 2 - 0.16, 0.32, 0.32, fill=RED, shape=MSO_SHAPE.OVAL)
        S.text(lx + 0.08, y + rh / 2 - 0.16, 0.32, 0.32, f"{k + 1:02d}", size=9, color=WHITE, font=HEAD, bold=True,
               align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        S.text(lx + 0.5, y + 0.02, lw - 0.6, rh - 0.04, risk, size=8.6, color=INK2, anchor=MSO_ANCHOR.MIDDLE, spacing=0.93)
        # connector with icon
        cy = y + rh / 2
        S.line([(mx, cy), (rx, cy)], "9AA7B6", 1.25)
        S.bubble(ic, mx + 0.5, cy, 0.38, NAVY, pad=0.21)
        # strategy card
        S.box(rx, y, rw, rh, fill="EEF7EF", line="CFE6D2", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.18)
        S.text(rx + 0.12, y + 0.02, rw - 0.6, rh - 0.04, fix, size=8.6, color=INK2, anchor=MSO_ANCHOR.MIDDLE, spacing=0.93)
        S.box(X1 - 0.4, cy - 0.16, 0.32, 0.32, fill=GREEN, shape=MSO_SHAPE.OVAL)
        S.text(X1 - 0.4, cy - 0.16, 0.32, 0.32, f"{k + 1:02d}", size=9, color=WHITE, font=HEAD, bold=True,
               align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    # highlight the data-access row (the first challenge) with a thin outline
    S.box(lx - 0.03, y0 - 0.03, X1 - lx + 0.06, rh + 0.06, line=BOLT, lw=1.5, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.2)

    S.text(X0 + 0.1, 6.68, X1 - X0 - 0.2, 0.22,
           "CSI = critical success index for lightning (higher is better), on held-out 2019 US storms. Trained on US GLM "
           "lightning, adapted to INSAT/GFS, not yet verified against Indian lightning observations. Tile count is an "
           "estimate from India’s land area.",
           size=6.8, color="7A8594", align=PP_ALIGN.CENTER, spacing=0.95)


def main(src, dst):
    prs = Presentation(src)
    build(find_slide(prs, "FEASIBILITY AND VIABILITY"))
    prs.save(dst)
    print("wrote", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
