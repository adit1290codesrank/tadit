# Submission results (frozen 29 Sep 2026; tier 2 extended to 6 h the same evening)

These are the numbers the submission is built on. A later tier-1 model replaces them only if it beats this
checkpoint **on validation** by 10:00 IST on 30 Sep.

## Tier-1 checkpoint (0–3 h)
- `runs/snaps/latest_0611.pt` (not in git): an hourly snapshot of the overnight run `runs/overnight`.
- step 42,700 · 683,200 samples · EMA weights · `configs/dev.yaml`, batch 16.
- Trained on 3,000 SEVIR events (train < 2019-01-01). Validated on 300 and tested on 600 (≥ 2019-06-01).
- Chosen on **validation** lightning CSI, where it sits at the peak for hours 2–3. The final checkpoint of the
  run (step 101,502) scored lower on validation.

## Tier-2 checkpoint (lead hours 1–6)
- `runs/ext6/best.pt` (not in git): best validation epoch 6 of 20, 11,484 samples, same test windows as before.
- It replaces the first tier-2 model (`runs/ext/best.pt`, hours 1–3 only), whose scores are kept in
  `results/ext_leads123*.json`.
- Tier-2 CSI changed for hours 1–3 as follows (update any slide that used the old values):
  - hour 1: 0.385 → **0.379**
  - hour 2: 0.353 → **0.349**
  - hour 3: 0.328 → **0.332**

## Files
- `results/*.json`: test-set scores on US held-out storms (Jun 2019 onward).
  - `full`: the tier-1 model.
  - `persistence`: baseline.
  - `full_india_mode`: tier 1 on INSAT-like and GFS-like inputs.
  - `no_*`, `sat_nwp_only`: the same model with inputs removed at test time.
  - `ext*`: tier 2.
- `results/india/*.json`: India runs on **GK2A** + GFS (tier 1 hours 1–3, tier 2 hours 4–6).
- `results/india_insat/*.json`: the same cases on **INSAT-3DR** (MOSDAC L1B) + GFS.
- `*_gk2a_check.json`: storm-location check against GK2A cloud tops observed after issue time
  (`scripts/check_india_gk2a.py`). It is a proxy, not lightning verification.
- The Kolkata 08Z run was issued after that storm's peak; 06Z is the fair case.
- `figures/` (US scorecard, ablations, examples, GK2A India maps) and `figures/insat/` (INSAT India maps):
  `python scripts/make_figures.py --results results --out figures --switch-hour 3`.

## Headline: lightning CSI per 16 km cell per lead hour, held-out 2019 storms, real GLM lightning
| lead hour | tier 1 | tier 2 | persistence | HRRR LTNG | HRRR REFC |
|---|---|---|---|---|---|
| 1 | **0.613** | 0.379 | 0.341 | 0.266 | 0.215 |
| 2 | **0.497** | 0.349 | 0.133 | 0.222 | 0.185 |
| 3 | **0.440** | 0.332 | 0.080 | 0.197 | 0.166 |
| 4 | – | **0.319** | – | 0.186 | 0.154 |
| 5 | – | **0.305** | – | 0.181 | 0.148 |
| 6 | – | **0.297** | – | 0.175 | 0.141 |

- Switch hour is 3: tier 1 is used for hours 1–3 and tier 2 for hours 4–6.
- Strict tier-1 CSI (8 km cell, per 10 min, pooled over all 18 steps to 3 h): 0.284 (persistence 0.085).
- Satellite + NWP only (the realistic Indian case outside radar range): 0.461 / 0.459 / 0.421, 1.4–5× persistence.
- Tier 2 on GFS-like inputs (India mode): 0.372 / 0.341 / 0.326 / 0.314 / 0.300 / 0.293.

## India cases (satellite + GFS, no radar, no lightning feed)
Storm-location check against satellite: tier-1 CSI for hours 1 / 2 / 3.

| case | P at city, hours 1–3 (GK2A input) | GK2A input | INSAT input |
|---|---|---|---|
| Bhubaneswar 2 Sep 2023 08Z (documented lightning outbreak) | 0.71 / 0.72 / 0.43 | 0.43 / 0.10 / 0.05 | 0.47 / 0.16 / 0.03 |
| Bhubaneswar 10 May 2024 09Z | 0.56 / 0.60 / 0.46 | 0.29 / 0.25 / 0.01 | 0.29 / 0.32 / 0.07 |
| Kolkata 9 May 2024 06Z (hailstorm ~07Z) | 0.62 / 0.69 / 0.65 | ≤ 0.05 | ≤ 0.04 |
| Delhi 28 May 2024 08Z (dry control) | 0.04 / 0.04 / 0.03 | no storms, none forecast | same |

The model locates storms, but its probabilities are calibrated to US climatology. Recalibration needs
Indian lightning observations; ILDN data has been requested.

Trained on US GLM lightning, adapted to INSAT/GFS, not yet verified against Indian lightning observations.
