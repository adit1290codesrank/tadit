# Website brief: SIH26072 thunderstorm & lightning nowcasting

This is input for the design pass. It lists what the website can show, where each piece comes from,
and the rules it has to keep. It covers content and features, not visuals.
Every number here is copied from the repo, with its source file named. **Don't invent or round
numbers in the design; use the data files.**

> **Scope and structure are set by `web/FRAME.md`** (decisions of 29 Sep 2026). Where the two differ, FRAME
> wins. This file remains the inventory of data and content. Sections marked *not on the site* are kept for
> slides and reference.

---

## 1. What the site is

- **Main audience:** SIH judges (MoES / IMD). They need the problem, the method and the measured skill, plus a
  working India forecast demo.
- **Second audience:** the public and IMD forecasters, who need a readable forecast: risk per hour, a map and what to do.
- **Static site** (Cloudflare Pages / Vercel). The site never runs a model.
  - The pipeline runs on our server.
  - `scripts/export_site.py` writes static JSON and PNG files.
  - The site only reads those files.
- **Where things live:**
  - the website code lives in `web/`;
  - the data it reads is exported to `site/public/data/`;
  - the schema is in `docs/SITE_DATA.md`;
  - `site/` and everything outside `web/` belong to the pipeline; don't edit them from the web branch.

## 2. Non-negotiable rules

1. **The honest label** goes on every forecast view, word for word:
   > Trained on US GLM lightning, adapted to INSAT/GFS, not yet verified against Indian lightning observations
2. **`metric_note`** goes under every score chart:
   > Lightning CSI per 16 km cell per lead hour on held-out US storms (Jun-Dec 2019), scored against real GOES-16 GLM lightning. Higher is better; 1 is perfect.
3. **Times are shown in IST**, always with both the issue time and the valid-until time.
4. **Input badges:** show every source's status (`live` / `approximate` / `partial` / `missing`). A missing source is shown as missing, never hidden.
5. **India maps use Survey of India boundaries.**
   - The source file is `data/boundaries/india_states.geojson` (SoI state boundaries), exported as `india_boundary.geojson`.
   - Never use Natural Earth, and never use the country borders built into a basemap (OSM, Mapbox and so on).
   - Bhuvan only serves boundaries as images, so it isn't used.
6. **The storm check** is labelled as a *satellite storm proxy (GK2A cold cloud tops)*, never as lightning verification.
7. **Numbers are shown as measured.** No rounding up, and no hiding a bad case.

## 3. Data inventory

Everything is under `data/` (as exported to `site/public/data/`). All paths inside the JSONs are relative to `data/`.

| File | Key fields | Feeds |
|---|---|---|
| `manifest.json` | `honest_label`, `switch_hour` (=3), `model.tier1/tier2` (step, samples, epoch), `forecasts[]` (`id, city, lat, lon, title, kind, issue_ist, issue_utc, peak_risk, has_maps, file`), `figures[]`, `boundary` | Site bootstrap, case picker, model facts, figure gallery |
| `scores.json` | `scorecard[]` (`lead_hour, tier1, tier2, persistence, hrrr_lightning, hrrr_reflectivity`), `switch_hour`, `metric_note`, `series.<name>` (`label, group, csi_by_hour`; tier-1 runs also have `lead_minutes, lightning_csi_per_step, vil_csi_per_step, summary`) | Scorecard table/chart, 10-min skill curves, ablations, India-mode comparison |
| `forecasts/<id>.json` | `title, description, kind, issue_ist, valid_until_ist, lat, lon, tile.corners, peak_risk, honest_label`, `hours[]` (`lead_hour, window_ist, source, p_location, p_tile_max, risk, advice`), `inputs.{satellite,radar,lightning,nwp}.status`, `storm_check`, `overlays.hourly`, `overlays.steps[]` (`minutes, time_ist, p_location, lightning, vil`) | Forecast viewer, risk cards, animation, 10-min risk curve, badges, storm-check table |
| `forecasts/<id>/hour<h>.png` | Lightning probability per lead hour, **h = 1–6**, 16 km, RGBA, north-up. Hours 1–3 come from tier 1, hours 4–6 from tier 2 (per `hours[].source`). | Map overlay (hour slider) |
| `forecasts/<id>/lght_<mmm>.png`, `vil_<mmm>.png` | Tier 1 only: 18 steps × 10 min (010…180), lightning probability and storm intensity (VIL). **Nothing at 10-min steps beyond 3 h.** | Map animation, lightning/VIL toggle |
| `figures/*.png` | Slide figures: scorecard, CSI vs lead, ablations, India mode, example panels, India case maps (`figures/insat/` holds the INSAT versions) | Optional gallery / fallback images |
| `india_boundary.geojson` | Survey of India state boundaries, only if exported with `--boundary` | Map boundary layer |

**Two quirks of `forecasts/<id>.json`:**
- **`honest_label` differs from the manifest's.** In a forecast file it is the run's longer `model_trained_on` sentence. `manifest.honest_label` is the exact rule-1 sentence, so that is the one to show.
- **`storm_check.hours` covers hours 1–3 only.**

**Colour ramps.** The same ramps must appear in the legend.
- **Lightning probability:** transparent below 0.05; from 0.05 to 0.8 it runs pale yellow → orange → red → deep red → purple.
- **VIL:** transparent below 16; greens, then orange, then brown at the SEVIR thresholds 16, 74, 133, 160, 181 and 219.

**Map placement:**
- `tile.corners` is already in MapLibre image-source order (top-left, top-right, bottom-right, bottom-left).
- Tiles are 384 km.
- The PNGs are already north-up; don't flip them.

## 4. Pages and features

### 4.1 Home / hero
- **The problem:**
  - lightning is a major weather killer in India;
  - IMD's operational nowcasts cover the next 3 h.
  - A sourced death statistic is needed before any number is shown; the repo doesn't have one.
*Not on the site* (FRAME: product-first, no story page). Kept for slides.
- **What we built:** a seamless nowcast of thunderstorms and lightning from radar, satellite, lightning and NWP, 0–6 h in two tiers.
- **Headline number** (`results/RESULTS.md`): lightning CSI by lead hour, tier 1 against persistence.

  | lead hour | tier 1 | persistence |
  |---|---|---|
  | 1 | 0.613 | 0.341 |
  | 2 | 0.497 | 0.133 |
  | 3 | 0.440 | 0.080 |

  - At hour 3, tier 1 is about 5.5× persistence.
  - The `metric_note` sits under this number.
- **Calls to action:** "See India forecasts" and "See the scores".

### 4.2 India forecast viewer (the demo)
- **Case picker** from `manifest.forecasts[]`: title, city, issue time in IST, peak-risk chip.
- **Map (MapLibre):**
  - the Bhuvan boundary, the city marker and the tile outline;
  - the overlay placed by `tile.corners`.
- **Lead-hour slider, hours 1–6:** switches `overlays.hourly[h]` and shows each hour's `window_ist` and `source`.
  - Hours 1–3 are tier 1 (finer detail); hours 4–6 are tier 2 (a coarser outlook).
- **10-minute animation, 0–3 h only:**
  - play/pause/scrub over `overlays.steps[]`, 18 steps, 10 → 180 min;
  - after 3 h only the hourly maps exist;
  - a toggle between **lightning probability** and **storm intensity (VIL)**;
  - the `time_ist` label is shown for each step.
- **Hourly risk cards:**
  - LOW / MODERATE / HIGH, with thresholds of 0.2 and 0.5 on `p_location`;
  - the probability at the city, and the tile maximum;
  - the `advice` sentence.
- **10-min risk curve:** `p_location` against time, with bands at 0.2 and 0.5.
- **Input badges:** satellite, radar, lightning and NWP, each with a status and detail on hover or tap (e.g. "INSAT-3DR/3DS L1B (MOSDAC)"; "GFS").
- **Storm check panel** (if `storm_check` is present):
  - POD, FAR and CSI per hour against GK2A deep-convection cells;
  - labelled as a proxy.
- **Legend** with both colour ramps.
- **Always visible:** the honest label, the issue time, and valid-until.

### 4.3 Cases (the runs in the run picker)
The runs come from `site/cases.json` and `results/india/*` (GK2A) or `results/india_insat/*` (INSAT). Every run has:
- satellite `live` (GK2A or INSAT-3DR);
- NWP: GFS, `live`;
- radar and lightning: `missing`.

On the site, **INSAT is the primary input and GK2A is the cross-check** (FRAME). Tier 2 (hours 4–6) uses only GFS, so it is identical on both.

**Hourly risk at the city, p at the location**:

| Case | INSAT, h1–3 (tier 1) | GK2A, h1–3 (tier 1) | h4–6 (tier 2, both) |
|---|---|---|---|
| **Odisha lightning outbreak**, Bhubaneswar, 2 Sep 2023 13:30 IST | MOD 0.469 / HIGH 0.629 / MOD 0.462 | HIGH 0.708 / HIGH 0.724 / MOD 0.427 | MOD 0.438 / 0.423 / 0.413 |
| **Kolkata hailstorm**, 9 May 2024 11:30 IST | HIGH 0.566 / 0.691 / 0.647 | HIGH 0.616 / 0.695 / 0.645 | HIGH 0.504 / MOD 0.495 / 0.411 |
| **Delhi heatwave control**, 28 May 2024 13:30 IST | LOW 0.025 / 0.023 / 0.023 | LOW 0.039 / 0.037 / 0.031 | LOW 0.133 / 0.113 / 0.096 |
| **Bhubaneswar partial miss**, 10 May 2024 14:30 IST | MOD 0.416 / 0.442 / 0.418 | HIGH 0.563 / 0.602 / MOD 0.461 | MOD 0.452 / 0.479 / 0.469 |

**Storm check CSI, h1/h2/h3** (tier 1 only, both against GK2A cloud tops):

| Case | INSAT input | GK2A input | Story |
|---|---|---|---|
| Odisha outbreak | 0.47 / 0.16 / 0.03 | 0.43 / 0.10 / 0.05 | The hit: elevated for all 6 h on a severe lightning day |
| Kolkata hailstorm | 0.01 / 0.04 / 0.00 | 0.01 / 0.05 / 0.00 | Warned about 1 h before the storm reached the city |
| Delhi control | n/a (no deep cells) | n/a (no deep cells) | No false alarm on a hot, dry day |
| Bhubaneswar partial miss | 0.29 / 0.32 / 0.07 | 0.29 / 0.25 / 0.01 | Shown on purpose: the storm formed about 157 km north |

- **INSAT runs through a different satellite than the one it's checked against.** On INSAT runs the storm check is therefore an independent check.
- **Kolkata storm check:** the proxy scores are very low (FAR 0.95–1.0). The case rests on the timing at the city, not on the tile score. Don't present the storm check as support for this case.
- **Delhi hours 4–6** rise to 0.10–0.13 (still LOW). The step from tier 1 to tier 2 shows in the numbers.
- **Hidden runs:** the Kolkata 08Z run is `hide: true` in `cases.json` (it was issued after the storm's peak). Don't show it.
- **Bhubaneswar 2 Sep 2023:** `cases.json` says a source for strike and casualty numbers must be added before any are published.

*§4.4–4.7 are not on the site* (FRAME: scores dropped, no "how it works"). Kept for slides and reference.

### 4.4 Skill / scorecard
- **Headline table and chart** from `scores.scorecard` (lightning CSI, 16 km, per lead hour; `results/RESULTS.md`):

  | lead hour | Tier 1 | Tier 2 | Persistence | HRRR lightning | HRRR reflectivity |
  |---|---|---|---|---|---|
  | 1 | 0.613 | 0.379 | 0.341 | 0.266 | 0.215 |
  | 2 | 0.497 | 0.349 | 0.133 | 0.222 | 0.185 |
  | 3 | 0.440 | 0.332 | 0.080 | 0.197 | 0.166 |
  | 4 | – | 0.319 | – | 0.186 | 0.154 |
  | 5 | – | 0.305 | – | 0.181 | 0.148 |
  | 6 | – | 0.297 | – | 0.175 | 0.141 |

- **The switch hour (3):** tier 1 is used for hours 1–3 and tier 2 for hours 4–6.
- **Tier 2 on GFS-like inputs (India mode):** 0.372 / 0.341 / 0.326 / 0.314 / 0.300 / 0.293.
- **10-minute curves** from `series.full.lightning_csi_per_step` and `vil_csi_per_step`, with persistence (18 points, 10–180 min).
- **Test-set facts:**
  - US storms held out by date (Jun 2019 onwards);
  - 600 test events;
  - the model saw 683,200 training samples.

### 4.5 What each sensor adds (ablations)
All rows are `series.*.csi_by_hour`: one model, with inputs removed at test time.

| Inputs | h1 | h2 | h3 |
|---|---|---|---|
| All (tier 1) | 0.613 | 0.497 | 0.440 |
| No satellite | 0.612 | 0.494 | 0.439 |
| No lightning feed | 0.575 | 0.486 | 0.435 |
| No NWP | 0.609 | 0.463 | 0.386 |
| No radar | 0.592 | 0.486 | 0.435 |
| No radar, no satellite | 0.588 | 0.475 | 0.423 |
| **Satellite + NWP only** | **0.461** | **0.459** | **0.421** |

- **Message for India:** outside radar range, with only satellite and NWP, the model still beats persistence by a wide margin, and by more at longer lead.
- The lightning feed matters most in hour 1; NWP matters most in hour 3.

### 4.6 Works on Indian-style inputs
- `full` against `full_india_mode`: the same model fed INSAT-like satellite (4 km IR, 8 km WV, 15/30-min scans) and GFS-like NWP (no LTNG/UH, ~24 km).
  - `full`: 0.613 / 0.497 / 0.440
  - `full_india_mode`: 0.612 / 0.492 / 0.437
- **Takeaway:** almost no loss.

### 4.7 How it works
- **Four sources:**
  - radar (NEXRAD VIL, 2 km);
  - satellite (GOES-16 IR 6.9 / 10.7 µm, 2 km);
  - lightning (GLM, 8 km);
  - NWP (HRRR, 8 km, hourly, no leakage).
- **Two tiers:**
  - Tier 1: multimodal fusion, 0–3 h, 10-min steps.
  - Tier 2: HRRR post-processing, lead hours 1–6, used for hours 4–6.
- **Architecture:**
  - one encoder per source;
  - a U-Net;
  - NWP enters through cross-attention and FiLM;
  - modality dropout (p = 0.15), so it runs with any source missing.
- **Training data:**
  - SEVIR + HRRR;
  - split by date: train before 2019-01-01, validation to 2019-06-01, test after.
- **India adaptation:** at training time, half the samples are made to look like INSAT and GFS.
- **Suggestion:** a diagram would carry this page best.

### 4.8 India data readiness
From `docs/PLAN.md` §5:

| Source | Access | Status |
|---|---|---|
| INSAT-3DR/3DS L1B (MOSDAC) | Free registration | Verified on real files; primary input on the site. Matches GK2A with correlation 0.87 (IR) / 0.84 (WV), reading ~2.7 K warmer |
| GK2A AMI (NOAA bucket) | Open, no login | Verified; cross-check input, and the reference for the storm check |
| IMD DWR radar | Images public; data on request | dBZ → approximate VIL adapter |
| Indian lightning (ILDN) | Requested | CSV adapter ready |
| ISS-LIS | Free Earthdata login | Verification only; converter not yet run on real files |
| GFS 0.25° | Open | Verified over India |

**The hard fact:** no open Indian lightning archive exists, which is why the model trains on US GLM.

### 4.9 Honest limits and next steps
**Limits:**
- Indian verification waits on ILDN (requested) or ISS-LIS data.
- Probabilities are calibrated to US storms. The model finds where the storms are, but the probabilities can't be trusted until it is recalibrated on Indian data.
- Radar and lightning feeds for India are still to come.

**Next:** IMD radar, an ILDN extract, and recalibration.

### 4.10 Team / about
- Names, SIH26072 (MoES / IMD) and the repo link. Content still needed from the team.

## 5. Gaps the design must handle gracefully

- **The 3 h seam.**
  - Hours 1–3 are tier 1: 10-min steps, VIL, a 10-min risk curve and a storm check.
  - Hours 4–6 are tier 2: hourly maps and hourly risk only.
  - Render only what exists: no empty 10-min slots and no VIL after 3 h. Still render whatever `hours[]` holds, and never show missing data as zeros.
- **INSAT runs aren't in the export yet.**
  - `export_site.py` only reads `results/india/` (GK2A). Main has to add `results/india_insat/`.
  - Both folders use the same file stems, so the ids need a suffix to stay apart.
  - Until main exports INSAT, the site shows the GK2A run and its satellite badge says so.
- **`has_maps: false`:** the forecast has hourly risk but no overlays. Show the cards and curve, and put a note where the map would be.
- **`boundary: null`:** the export was run without `--boundary`. Show no borders at all rather than borders from another source.
- **NaN / null storm-check values** (Delhi): show "no deep convection observed", not 0 or NaN.
- **Missing inputs** are normal (radar and lightning in every India run today). The badge design must make `missing` look expected, not broken.
- **Baselines:** there is no pySTEPS baseline, so don't reserve space for one.
- **Figures** are optional and might not be exported.

## 6. Out of scope

- Live inference and "forecast my city" on demand (possible later only as a server job plus re-export).
- Accounts, alerts and notifications.
- Any data not in the export.

## 7. Open questions

Audience, language, device and archived-versus-live are all settled in `web/FRAME.md`. One is still open:
- **Framework and build** in `web/`, reading `site/public/data/`.
  - `STEPS.md` step 12b still says `cd site && npm run build`.
  - Changing that is main's call, so raise it with the pipeline owner.
