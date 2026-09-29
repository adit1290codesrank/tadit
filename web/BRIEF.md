# Website brief: SIH26072 thunderstorm & lightning nowcasting

This is input for the design pass. It lists what the website can show, where each piece comes from,
and the rules it has to keep. It covers content and features, not visuals.
Every number here is copied from the repo, with its source file named. **Don't invent or round
numbers in the design; use the data files.**

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
5. **India maps use ISRO Bhuvan / Survey of India boundaries.** Never use Natural Earth or default OSM/Mapbox country borders.
6. **The storm check** is labelled as a *satellite storm proxy (GK2A cold cloud tops)*, never as lightning verification.
7. **Numbers are shown as measured.** No rounding up, and no hiding a bad case.

## 3. Data inventory

Everything is under `data/` (as exported to `site/public/data/`). All paths inside the JSONs are relative to `data/`.

| File | Key fields | Feeds |
|---|---|---|
| `manifest.json` | `honest_label`, `switch_hour` (=3), `model.tier1/tier2` (step, samples, epoch), `forecasts[]` (`id, city, lat, lon, title, kind, issue_ist, issue_utc, peak_risk, has_maps, file`), `figures[]`, `boundary` | Site bootstrap, case picker, model facts, figure gallery |
| `scores.json` | `scorecard[]` (`lead_hour, tier1, tier2, persistence, hrrr_lightning, hrrr_reflectivity`), `switch_hour`, `metric_note`, `series.<name>` (`label, group, csi_by_hour`; tier-1 runs also have `lead_minutes, lightning_csi_per_step, vil_csi_per_step, summary`) | Scorecard table/chart, 10-min skill curves, ablations, India-mode comparison |
| `forecasts/<id>.json` | `title, description, kind, issue_ist, valid_until_ist, lat, lon, tile.corners, peak_risk, honest_label`, `hours[]` (`lead_hour, window_ist, source, p_location, p_tile_max, risk, advice`), `inputs.{satellite,radar,lightning,nwp}.status`, `storm_check`, `overlays.hourly`, `overlays.steps[]` (`minutes, time_ist, p_location, lightning, vil`) | Forecast viewer, risk cards, animation, 10-min risk curve, badges, storm-check table |
| `forecasts/<id>/hour<h>.png` | Lightning probability per lead hour, RGBA, north-up | Map overlay (hour slider) |
| `forecasts/<id>/lght_<mmm>.png`, `vil_<mmm>.png` | 18 steps × 10 min (010…180), lightning probability and storm intensity (VIL) | Map animation, lightning/VIL toggle |
| `figures/*.png` | Slide figures: scorecard, CSI vs lead, ablations, India mode, example panels, India case maps | Optional gallery / fallback images |
| `india_boundary.geojson` | Bhuvan outline, only if exported | Map boundary layer |

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
- **What we built:** a seamless nowcast of thunderstorms and lightning from radar, satellite, lightning and NWP. The product design is 0–6 h in two tiers.
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
- **Lead-hour slider:** switches `overlays.hourly[h]` and shows each hour's `window_ist` and `source` (tier1/tier2).
- **10-minute animation:**
  - play/pause/scrub over `overlays.steps[]`, 18 steps, 10 → 180 min;
  - a toggle between **lightning probability** and **storm intensity (VIL)**;
  - the `time_ist` label is shown for each step.
- **Hourly risk cards:**
  - LOW / MODERATE / HIGH, with thresholds of 0.2 and 0.5 on `p_location`;
  - the probability at the city, and the tile maximum;
  - the `advice` sentence.
- **10-min risk curve:** `p_location` against time, with bands at 0.2 and 0.5.
- **Input badges:** satellite, radar, lightning and NWP, each with a status and detail on hover or tap (e.g. "GK2A AMI, stand-in until INSAT is connected"; "GFS").
- **Storm check panel** (if `storm_check` is present):
  - POD, FAR and CSI per hour against GK2A deep-convection cells;
  - labelled as a proxy.
- **Legend** with both colour ramps.
- **Always visible:** the honest label, the issue time, and valid-until.

### 4.3 Case stories
These come from `site/cases.json` and `results/india/*`. All four runs used the same inputs:
- satellite: GK2A, `live`;
- NWP: GFS, `live`;
- radar and lightning: `missing`.

| Case | Hourly risk at city (p) | Storm check CSI h1/h2/h3 | Story |
|---|---|---|---|
| **Odisha lightning outbreak**, Bhubaneswar, 2 Sep 2023 13:30 IST | HIGH 0.708 / HIGH 0.724 / MOD 0.427 | 0.43 / 0.10 / 0.05 | The hit: HIGH for hours 1–2 on a severe lightning day |
| **Kolkata hailstorm**, 9 May 2024 11:30 IST | HIGH 0.616 / 0.695 / 0.645 | 0.01 / 0.05 / 0.00 | Warned about 1 h before the storm reached the city |
| **Delhi heatwave control**, 28 May 2024 13:30 IST | LOW 0.039 / 0.037 / 0.031 | n/a (no deep cells) | No false alarm on a hot, dry day |
| **Bhubaneswar partial miss**, 10 May 2024 14:30 IST | HIGH 0.563 / 0.602 / MOD 0.461 | 0.29 / 0.25 / 0.01 | Shown on purpose: the storm formed about 157 km north |

- **Kolkata storm check:** the proxy scores are very low (FAR 0.95–1.0). The story leans on the city-level timing, not the tile score. Don't present the storm check as support for this case.
- **Hidden runs:** the Kolkata 08Z run is `hide: true` in `cases.json` (it was issued after the storm's peak). Don't show it.
- **Bhubaneswar 2 Sep 2023:** `cases.json` says a source for strike and casualty numbers must be added before any are published.

### 4.4 Skill / scorecard
- **Headline table and chart** from `scores.scorecard` (lightning CSI, 16 km, per lead hour):

  | lead hour | Tier 1 | Tier 2 | Persistence | HRRR lightning | HRRR reflectivity |
  |---|---|---|---|---|---|
  | 1 | 0.613 | 0.385 | 0.341 | 0.266 | 0.215 |
  | 2 | 0.497 | 0.353 | 0.133 | 0.222 | 0.185 |
  | 3 | 0.440 | 0.328 | 0.080 | 0.197 | 0.166 |

- **The switch hour (3)** is marked on the chart: tier 1 up to it, tier 2 after it.
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
  - Tier 2: HRRR post-processing, lead hours 1–6 by design.
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
| INSAT-3DR/3DS L1B (MOSDAC) | Free registration | Reader written, not yet run on real files |
| GK2A AMI (NOAA bucket) | Open, no login | Verified; used in all the India runs |
| IMD DWR radar | Images public; data on request | dBZ → approximate VIL adapter |
| IITM ILLN lightning | On request | CSV adapter ready |
| ISS-LIS | Free Earthdata login | Verification only; converter not yet run on real files |
| GFS 0.25° | Open | Verified over India |

**The hard fact:** no open Indian lightning archive exists, which is why the model trains on US GLM.

### 4.9 Honest limits and next steps
**Limits:**
- Indian verification waits on ILLN or ISS-LIS data.
- Probabilities are calibrated to US storms.
- Radar and lightning feeds for India are still to come.

**Next:** INSAT via MOSDAC, IMD radar, an ILLN extract, and recalibration.

### 4.10 Team / about
- Names, SIH26072 (MoES / IMD) and the repo link. Content still needed from the team.

## 5. Gaps the design must handle gracefully

- **Hours 4–6:**
  - tier 2 was trained for lead hours 1–3 only, and `switch_hour` is 3, so every hour shown today is tier 1 (0–3 h).
  - Design for 6 hours, but render only the hours the data has; don't show empty slots as zeros.
- **`has_maps: false`:** the forecast has hourly risk but no overlays. Show the cards and curve, and put a note where the map would be.
- **`boundary: null`:** there's no Bhuvan outline yet. Show no country border at all rather than a non-Bhuvan one.
- **NaN / null storm-check values** (Delhi): show "no deep convection observed", not 0 or NaN.
- **Missing inputs** are normal (radar and lightning in every India run today). The badge design must make `missing` look expected, not broken.
- **Baselines:** there is no pySTEPS baseline, so don't reserve space for one.
- **Figures** are optional and might not be exported.

## 6. Out of scope

- Live inference and "forecast my city" on demand (possible later only as a server job plus re-export).
- Accounts, alerts and notifications.
- Any data not in the export.

## 7. Open questions for the design pass

1. **Audience balance:** a judge-first story page, or a forecast-first app with the story behind it?
2. **Languages:** Hindi or Odia for the risk cards and advice?
3. **Mobile:** mobile-first for the public view (IMD's audience is mostly on phones)?
4. **Framework and build** in `web/`, reading `site/public/data/`. `STEPS.md` step 12b still says `cd site && npm run build`. Changing that is main's call, so raise it with the pipeline owner.
5. **Real-time look:** the cases are past events. How clearly should the site say "archived case" as opposed to "live"?
