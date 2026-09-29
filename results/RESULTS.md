# Submission results (frozen 29 Sep 2026)

These are the numbers the submission is built on. A later model replaces them only if it beats this
checkpoint **on validation** by 10:00 IST on 30 Sep.

## Tier-1 checkpoint
- `runs/snaps/latest_0611.pt` (not in git): an hourly snapshot of the overnight run `runs/overnight`.
- step 42,700 · 683,200 samples · EMA weights · `configs/dev.yaml`, batch 16.
- Trained on 3,000 SEVIR events (train < 2019-01-01). Validated on 300 and tested on 600 (≥ 2019-06-01).
- Chosen on **validation** lightning CSI, where it sits at the peak for hours 2–3. The final checkpoint of the
  run (step 101,502) scored lower on validation.

## Tier-2 checkpoint
- `runs/ext/best.pt` (not in git): lead hours 1–3, best epoch 8 of 20.

## Files
- `results/*.json`: test-set scores on US held-out storms (Jun 2019 onward).
  - `full`: the tier-1 model.
  - `persistence`: baseline.
  - `full_india_mode`: tier 1 on INSAT-like and GFS-like inputs.
  - `no_*`, `sat_nwp_only`: the same model with inputs removed at test time.
  - `ext*`: tier 2.
- `results/india/*.json`: India runs on GK2A + GFS, and `*_gk2a_check.json` storm-location checks
  (`scripts/check_india_gk2a.py`). The Kolkata 08Z run was issued after that storm's peak; 06Z is the fair case.
- `figures/`: `python scripts/make_figures.py --results results --out figures --switch-hour 3`.

## Headline (lightning CSI per 16 km cell per lead hour, real GLM lightning)
| lead hour | tier 1 | tier 2 | persistence | HRRR LTNG | HRRR REFC |
|---|---|---|---|---|---|
| 1 | 0.613 | 0.385 | 0.341 | 0.266 | 0.215 |
| 2 | 0.497 | 0.353 | 0.133 | 0.222 | 0.185 |
| 3 | 0.440 | 0.328 | 0.080 | 0.197 | 0.166 |

Satellite + NWP only (the realistic Indian case outside radar range): 0.461 / 0.459 / 0.421.

Trained on US GLM lightning, adapted to INSAT/GFS, not yet verified against Indian lightning observations.
