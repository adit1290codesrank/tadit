"""Slide 6: RESEARCH AND REFERENCES."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deckkit import *  # noqa: F401,F403

SITE = "https://tadit.pages.dev/"
REPO = "https://github.com/adit1290codesrank/sih2026"

DATA = [  # (status, text)
    ("TRAIN", "**SEVIR** storm events: radar VIL, GOES-16 IR, GLM lightning. Veillette et al., NeurIPS 2020 · "
              "[registry.opendata.aws/sevir](https://registry.opendata.aws/sevir/)"),
    ("TRAIN", "**HRRR** US weather model (NWP input + baseline), NOAA · "
              "[registry.opendata.aws/noaa-hrrr-pds](https://registry.opendata.aws/noaa-hrrr-pds/)"),
    ("INDIA", "**GFS 0.25°** global weather model, NOAA · "
              "[registry.opendata.aws/noaa-gfs-bdp-pds](https://registry.opendata.aws/noaa-gfs-bdp-pds/)"),
    ("INDIA", "**INSAT-3DR Imager L1B** (3RIMG_L1B_STD), ISRO / SAC · [mosdac.gov.in](https://www.mosdac.gov.in)"),
    ("INDIA", "**GK2A AMI L1B** satellite, KMA via NOAA, no login · "
              "[registry.opendata.aws/noaa-gk2a-pds](https://registry.opendata.aws/noaa-gk2a-pds/)"),
    ("VERIFY", "**FY-4A LMI corrected lightning events**, Zhang et al., ESSD 18, 5773–5791 (2026), CC-BY 4.0 · "
               "[doi:10.5194/essd-18-5773-2026](https://doi.org/10.5194/essd-18-5773-2026) · "
               "[data](https://doi.org/10.11888/Atmos.tpdc.303312)"),
    ("TESTED", "**ISRO Cherrapunji DWR** (RSCHR_L2B_STD), tested, not used · [mosdac.gov.in](https://www.mosdac.gov.in)"),
    ("MAPS", "**Survey of India** boundaries (OVSF/1M/7) · "
             "[onlinemaps.surveyofindia.gov.in](https://onlinemaps.surveyofindia.gov.in)"),
    ("PARTNER", "**ILDN** Indian Lightning Detection Network, CeLTS, Tripura University: partnership offered (Sep 2026) · "
              "[ildn.in](https://ildn.in)"),
]
STATUS = {"TRAIN": BLUE, "INDIA": GREEN, "VERIFY": SAFFRON, "TESTED": MUTED, "MAPS": TEAL, "PARTNER": VIOLET}

PAPERS = [  # (group, [entries])
    ("Model design", [
        "Ronneberger et al., **U-Net**, MICCAI 2015 · [arXiv:1505.04597](https://arxiv.org/abs/1505.04597)",
        "Perez et al., **FiLM** conditioning, AAAI 2018 · [arXiv:1709.07871](https://arxiv.org/abs/1709.07871)",
        "Leinonen et al., **Thunderstorm nowcasting with deep learning: multi-hazard data fusion**, GRL 2023 "
        "(closest prior work) · [doi](https://doi.org/10.1029/2022GL101626)",
    ]),
    ("Deep-learning nowcasting", [
        "Shi et al., **ConvLSTM** precipitation nowcasting, NeurIPS 2015 · [arXiv:1506.04214](https://arxiv.org/abs/1506.04214)",
        "Ravuri et al., **Skilful nowcasting with deep generative models**, Nature 597 (2021) · "
        "[doi](https://doi.org/10.1038/s41586-021-03854-z)",
        "Gao et al., **Earthformer** (SEVIR benchmark), NeurIPS 2022 · [arXiv:2207.05833](https://arxiv.org/abs/2207.05833)",
    ]),
    ("Sensors & weather models", [
        "Dowell et al., **HRRR** Part I, Weather & Forecasting 37 (2022) · [doi](https://doi.org/10.1175/WAF-D-21-0151.1)",
        "Goodman et al., **GOES-R GLM**, Atmos. Research 125 (2013) · [doi](https://doi.org/10.1016/j.atmosres.2013.01.006)",
        "NOAA/NASA, **GLM Lightning Cluster-Filter ATBD** (330 ms / 16.5 km flashes) · "
        "[pdf](https://www.star.nesdis.noaa.gov/goesr/documents/ATBDs/Baseline/ATBD_GOES-R_GLM_v3.0_Jul2012.pdf)",
        "Blaylock, **Herbie** NWP download tool, Zenodo · [doi](https://doi.org/10.5281/zenodo.4567540)",
    ]),
    ("Our work", [
        "**Tadit** frozen results and scorecard, [results/RESULTS.md]"
        "(https://github.com/adit1290codesrank/sih2026/blob/main/results/RESULTS.md) · "
        "live site [tadit.pages.dev](https://tadit.pages.dev/)",
    ]),
    ("Verification & physics", [
        "Schaefer, **Critical success index** as a warning-skill score, Weather & Forecasting 1990",
        "Greene & Clark, **Vertically integrated liquid (VIL)** from radar, Monthly Weather Review 1972",
        "Maddox, **Mesoscale convective complexes** (−52 °C cloud-top threshold), BAMS 1980",
    ]),
]

NEWS = [
    "**Bhubaneswar, 2 Sep 2023:** 61,000 lightning strikes in two hours "
    "([Organiser](https://organiser.org/2023/09/05/194084/bharat/odisha-61000-lightning-strikes-hit-bhubaneshwar-in-two-hours-leaving-10-people-dead/)); "
    "10 killed in six districts ([Deccan Herald](https://www.deccanherald.com/india/odisha/10-killed-in-lightning-strikes-in-odisha-2670909))",
    "**Kolkata, 9 May 2024:** thundersquall and hailstorms lash the city "
    "([ThePrint](https://theprint.in/india/thundersquall-hailstorms-lash-kolkata-adjoining-districts-met-forecasts-more-till-may-12/2077151/))",
]

POLICY = [
    "NCRB, **Accidental Deaths & Suicides in India 2023** (lightning deaths) · "
    "[data.gov.in](https://www.data.gov.in/catalog/accidental-deaths-suicides-india-adsi-2023)",
    "IMD **station-wise nowcast** service (3 h horizon) · "
    "[mausam.imd.gov.in](https://mausam.imd.gov.in/imd_latest/contents/stationwise-nowcast-warning.php)",
    "Cabinet approves **Mission Mausam**, 2024 · "
    "[pmindia.gov.in](https://www.pmindia.gov.in/en/news_updates/cabinet-approves-mission-mausam-to-create-a-more-weather-ready-and-climate-smart-bharat-with-an-outlay-of-rs-2000-crore-over-two-years/)",
]


def build(slide):
    S = Slide(slide)
    reset_slide(slide)
    X0, X1 = 0.25, 13.08
    top, bot = 1.2, 6.86

    # ---------------- col 1: data sources
    c1x, c1w = X0, 4.35
    card(S, c1x, top, c1w, bot - top, "Data Sources", BLUE, "database")
    rh = (bot - top - 0.46) / len(DATA)
    for k, (st, txt) in enumerate(DATA):
        y = top + 0.44 + k * rh
        col = STATUS[st]
        S.box(c1x + 0.1, y + rh / 2 - 0.1, 0.62, 0.2, fill=col, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
        S.text(c1x + 0.1, y + rh / 2 - 0.1, 0.62, 0.2, st, size=6.5, color=WHITE, font=HEAD, bold=True, align=PP_ALIGN.CENTER,
               anchor=MSO_ANCHOR.MIDDLE)
        S.text(c1x + 0.8, y + 0.02, c1w - 0.9, rh - 0.04, txt, size=8.2, color=INK2, anchor=MSO_ANCHOR.MIDDLE, spacing=0.92)
        if k < len(DATA) - 1:
            S.line([(c1x + 0.1, y + rh), (c1x + c1w - 0.1, y + rh)], "E6ECF3", 0.75)

    # ---------------- col 2: papers
    c2x, c2w = c1x + c1w + 0.12, 4.75
    card(S, c2x, top, c2w, bot - top, "Methods & Research Papers", VIOLET, "search")
    paras, y = [], top + 0.46
    for grp, items in PAPERS:
        S.text(c2x + 0.14, y, c2w - 0.25, 0.17, grp.upper(), size=7.6, color=VIOLET, font=HEAD, bold=True)
        y += 0.19
        for it in items:
            n_lines = -(-len(_plain(it)) // 100)
            h = 0.15 * n_lines + 0.07
            S.box(c2x + 0.16, y + 0.05, 0.05, 0.05, fill=VIOLET, shape=MSO_SHAPE.OVAL)
            S.text(c2x + 0.28, y, c2w - 0.4, h, it, size=8, color=INK2, spacing=0.92)
            y += h
        y += 0.09

    # ---------------- col 3: our work, evidence, policy
    c3x, c3w = c2x + c2w + 0.12, X1 - (c2x + c2w + 0.12)
    # link buttons
    for k, (lab, url, sub, col) in enumerate([("Live prototype", SITE, "tadit.pages.dev", SAFFRON),
                                              ("Code & results", REPO, "github.com/adit1290codesrank/sih2026", NAVY)]):
        y = top + k * 0.56
        b = S.box(c3x, y, c3w, 0.48, fill=col, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3, shadow=True)
        b.click_action.hyperlink.address = url
        S.icon("users" if k == 0 else "code", c3x + 0.14, y + 0.11, 0.26)
        t = S.text(c3x + 0.5, y + 0.04, c3w - 0.56, 0.4, [f"**{lab}:** click here", sub], size=9, color=WHITE,
                   bold_color=WHITE, font=HEAD, anchor=MSO_ANCHOR.MIDDLE, spacing=0.9)
        t.click_action.hyperlink.address = url
        for r in t.text_frame.paragraphs[1].runs:
            r.font.size = Pt(7)

    # India verification
    vy = top + 1.14
    vh = 1.72
    card(S, c3x, vy, c3w, vh, "India Check vs Real Lightning", GREEN, "shieldcheck")
    S.text(c3x + 0.12, vy + 0.4, c3w - 0.2, 0.32, "FY-4A satellite lightning, CSI for hours 1 / 2 / 3 (persistence in brackets)",
           size=7.2, color=MUTED, spacing=0.9)
    rows = [("Bhubaneswar · GK2A", "0.24 / 0.22 / 0.20", "(0.20 / 0.01 / 0.00)"),
            ("Bhubaneswar · INSAT", "0.24 / 0.16 / 0.13", "(0.20 / 0.01 / 0.00)"),
            ("Guwahati · INSAT", "hour 6: MODERATE risk", "storm hit the city then")]
    for k, (a, b, c) in enumerate(rows):
        y = vy + 0.74 + k * 0.32
        S.box(c3x + 0.1, y, c3w - 0.2, 0.25, fill="EEF7EF", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3)
        S.text(c3x + 0.18, y, 1.2, 0.25, a, size=6.9, color=INK, font=HEAD, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        S.text(c3x + 1.36, y, c3w - 1.5, 0.25, f"**{b}** {c}", size=6.9, color=MUTED, bold_color=GREEN,
               anchor=MSO_ANCHOR.MIDDLE)

    # news evidence
    ny = vy + vh + 0.1
    nh = 1.26
    card(S, c3x, ny, c3w, nh, "Real Storms We Forecast", RED, "alert")
    S.text(c3x + 0.12, ny + 0.42, c3w - 0.2, nh - 0.46, NEWS, size=7.8, color=INK2, spacing=0.92, space_after=3)

    # policy & statistics
    py = ny + nh + 0.1
    card(S, c3x, py, c3w, bot - py, "Government Sources", AMBER, "landmark")
    S.text(c3x + 0.12, py + 0.42, c3w - 0.2, bot - py - 0.46, POLICY, size=7.8, color=INK2, spacing=0.92, space_after=3)


def card(S, x, y, w, h, title, col, ic):
    S.box(x, y, w, h, fill=WHITE, line=LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04, shadow=True)
    S.box(x, y, w, 0.34, fill=col, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3)
    S.box(x, y + 0.2, w, 0.14, fill=col)
    S.icon(ic, x + 0.12, y + 0.06, 0.22)
    S.text(x + 0.42, y, w - 0.5, 0.34, title, size=10.5, color=WHITE, font=HEAD, bold=True, anchor=MSO_ANCHOR.MIDDLE)


def _plain(s):
    import re
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s).replace("**", "")
