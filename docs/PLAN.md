# SIH26072 Implementation Plan

## 0. Forecast horizon: seamless 0–6 h in two tiers

**Why 1 h is not enough**
- **IMD's operational thunderstorm and lightning nowcasts** cover the **next 3 hours**, reissued every 3 hours by district and station ([IMD nowcast portal](https://mausam.imd.gov.in/imd_latest/contents/stationwise-nowcast-warning.php), [example IMD alerts](https://ommcomnews.com/odisha-news/thunderstorms-with-lightning-expected-in-nine-dists-in-next-three-hours-imd/)).
- **Other SIH26072 teams** publicly pitch **0–6 h** ([example](https://github.com/Avenger2007/SIH-Nowcasting-)).

**What the literature says about horizon**

| Source | Finding |
|---|---|
| Blending studies ([NOAA report](https://repository.library.noaa.gov/view/noaa/32133/noaa_32133_DS1.pdf), [pysteps blending](https://rmets.onlinelibrary.wiley.com/doi/10.1002/qj.4461)) | Radar extrapolation beats NWP up to **~2 h**; NWP wins after that. Operational systems blend the two, shifting weight to NWP with lead time. |
| [NowcastNet (Nature 2023)](https://www.nature.com/articles/s41586-023-06184-4) | Radar-only deep learning skilful up to **3 h**. |
| [MetNet-2 (Nat. Comms 2022)](https://www.nature.com/articles/s41467-022-32483-x) | Reaches **12 h**, but needs a 2048 km context. Its "Postprocess" variant maps HRRR forecasts to calibrated probabilities. |

**SEVIR limits:** events are 4 h long (49 frames) over 384 km patches.
- Storms move 30–60 km/h, so after 2–3 h the weather in the patch comes from outside it.
- Observations alone therefore cannot carry a 6 h forecast.

### Design

| | Tier 1: multimodal fusion nowcast | Tier 2: NWP post-processor (`nowcast.extended`) |
|---|---|---|
| Lead | **0–3 h**, 18 steps × 10 min | **lead hours 1–6** |
| Inputs | 30 min of radar, IR and lightning (5 min) + HRRR f01 | HRRR fields valid at V−1h and V, both from the run initialised at V−(k+1)h (latest run 1 h after issue). No observations |
| Output grid | VIL 2 km, lightning 8 km | lightning probability and VIL max at 16 km |
| Target | VIL frames; "any flash in each 10-min interval" | any GLM flash, and max VIL, during (V−1h, V] |
| Training data | 7 windows per event (52k in train) | 140,880 samples (18,724 train windows × 6 leads) |
| Where it trains | overnight + burst (60M params) | primary, Day 2; small U-Net, minutes to an hour |

**Crossover evaluation:** both tiers are scored on the same question, "lightning in this 16 km cell during lead hour k":
- tier 1 via `lght_lead_hour_16km` in `evaluate.py`;
- tier 2 via `extended eval`, which also scores raw HRRR LTNG and REFC as baselines.

`scripts/crossover.py` prints the 0–6 h scorecard. The **operational product uses tier 1 up to the measured crossover hour and tier 2 after it.** That crossover plot is the core judge slide.

**What the extra horizon costs**
- Tier-1 windows per event drop from 25 to 7. This is compensated by random window starts and 7,500 events.
- Tier 2 needs HRRR f02–f07: **40,950 downloads** (6,825 unique hours), on a 16 km grid.
  - About 2 h on 12 workers at sandbox speed; run it in parallel with the SEVIR build.
  - Priority if short on time: `--fxx 2,3,4` (lead hours 1–3, the crossover), then `5,6,7`.

**Horizon is configurable:** `data.t_in / t_out / out_step`.
- The Earthformer benchmark setting (13 → 12 × 5 min) is still available.
- `NowcastDataset` rejects a horizon that does not fit a 49-frame event.

## 1. Data: SEVIR + HRRR

SEVIR is the only open archive where radar, satellite and lightning are **already co-registered**:
- 384 km patches, 4 h per event, 49 frames at 5 min
- over 10k events

HRRR supplies the NWP. It is 3 km and hourly, and it has the convective fields we need.

| Modality | Use | Avoid (and why) |
|---|---|---|
| Radar | SEVIR `vil` (`s3://sevir`, anonymous) | NEXRAD Level II: polar volumes, needs dealiasing and gridding |
| Satellite | SEVIR `ir069` / `ir107` (drop `vis`: daytime only, and the bulk of SEVIR's size) | raw GOES ABI: needs fixed-grid reprojection |
| Lightning | SEVIR `lght` (GLM flashes) → 48 × 48 counts | WWLLN / ENTLN: licensed. HRRR `LTNG` is a model field, not an observation |
| NWP | HRRR via Herbie; the f01 forecast from the run initialised at H−1 | ERA5: its 4D-Var window uses obs from after t0 (leak), and the CDS queue is slow. WeatherBench 5.6°: coarser than a whole patch |

The **fallback for NWP** is ARCO-ERA5 zarr (global, 0.25°, hourly). It is also the route for the India demo.

**Alignment**
- **Lightning:** the flash lists are gridded with frame *k* = flashes in (T_k − 5 min, T_k]. The SEVIR tutorial bins forward in time instead, which leaks future lightning into the last input frame.
- **NWP:** each event's 48 × 48 grid comes from the catalog's `proj` string and corners (pyproj). HRRR is regridded onto it by KD-tree inverse-distance weighting, so there is no ESMF dependency.
- **Checks:** `scripts/check_alignment.py` checks the row order and the lightning x/y units empirically before anything is built.

**Split:** by date, as in Earthformer: train < 2019-01-01 ≤ val < 2019-06-01 ≤ test.

### Verified against the real data (catalog + S3 + HRRR, from the dev sandbox)

**Catalog**
- 12,863 events have all of vil/ir069/ir107/lght, but only **2,573 of them are storm (`S`) events**: 1,500 train, 431 val, 642 test.
- `select_events` takes every storm event and fills the rest with random (`R`) events.
- The default 6000/500/1000 selection is **7,500 events (2,542 storm)**, covering 2018-02 to 2019-11.

**`minute_offsets` is not clean**
- About 10% of events are on a shifted 5-min grid (e.g. −118…+122).
- About 80 rows have typos (`-40:-40`, `25:27:35`).
- `frame_offsets()` keeps the clean ones and repairs the others.

**Arrays**
- `vil` is `(N, 384, 384, 49)` uint8 and stored contiguously, so one event is a single ~7 MB range read.
- IR is int16 in °C × 100.
- Lightning is `(n, 5)` = [seconds relative to `time_utc`, lat, lon, x, y], with x/y in **48-grid pixels**. Flashes beyond the patch edge (x or y ≥ 48) are dropped.

**Orientation**
- **Row 0 is the south edge** (`ROW0_NORTH = False`): VIL vs HRRR REFC correlates +0.43 under that convention vs −0.08 for north-up, on 7 of 7 events.
- Lightning needs no flip.

**HRRR** (wrfsfc f01, checked in both the v2 2018-05 period and the v3 2019-06 period)
- All 14 requested fields exist in both.
- `RH:700 mb` does not exist, so mid-level dryness is the 700 mb dewpoint depression (TMP − DPT).
- 2–5 km updraft helicity was added.
- Herbie is restricted to aws/google/azure.
- 8,743 unique valid hours; ~2 s per hour per worker in the sandbox.

**Size**
- **2.6–3.0 MB per event compressed** (5.8 MB raw), so **≈ 21 GB for 7,500 events**.
- The full 60M-parameter model trains on real shards; `latest.pt` is ~1 GB and the bf16 EMA file 120 MB.

## 2. Model: FusionNowcaster (`src/nowcast/model/fusion.py`)

The design follows Leinonen et al.:
- **Per-source encoders at native resolution** for radar, IR and lightning (Leinonen et al., AIES 2022 and GRL 2023, the closest prior work, which fuses all four sources)
- **Gated fusion** at H/2, with learned "missing" embeddings for absent sources
- **U-Net encoder** down to H/16
- **Bottleneck** of 4 blocks: self-attention plus **cross-attention from observation tokens to NWP tokens**
- **Decoder** with FiLM conditioning on time of day, pooled NWP and the presence mask

**Output heads:** VIL for 18 lead times (10–180 min) at 2 km, and lightning logits for 18 lead times at 8 km.
All lead times come out in one pass (SimVP-style), so the model is fast and compiles cleanly.

**Training choices**
- **Losses:** intensity-banded L1 + MSE for VIL (TrajGRU B-MSE idea); focal BCE with 1-cell tolerance for lightning.
- **Modality dropout:** p = 0.15. This buys robustness to missing sensors and free inference-time ablations (`evaluate.py --drop`).
- **Augmentation:** 90° rotations only. Wind is stored as shear *magnitude*, so every field is rotation-invariant. Flips are excluded because a mirror flips the sign of helicity.

**Not built, and why**
- ConvLSTM / PredRNN: sequential, slow, compile-unfriendly.
- Earthformer as the backbone: too heavy at this resolution to iterate on. Use its SEVIR checkpoint as a baseline row only, if it loads.
- GAN / diffusion: no time to stabilise or to sample.

**Baselines:** persistence, pySTEPS optical-flow extrapolation, and our model with radar only.

## 3. Time budget: about 11 h of training, ≈ 27–30 4060 Ti-hours

| When | Where | Wall clock | Run |
|---|---|---|---|
| Day 1 H10–13 | 4060 Ti | 0.5 h | smoke test: loss falls, measure throughput |
| Day 1 overnight | 4060 Ti | 9 h | **full model, fallback** (`configs/dev.yaml`) |
| Burst | 5090 #0 | 2 h | full model **`--resume` from the overnight checkpoint** → ≈ 17–19 4060 Ti-h total |
| Burst | 5090 #1 | 2 h | radar-only control from scratch (≈ 8–10 4060 Ti-h) |
| Day 2, during the burst | 4060 Ti | ≤ 1 h | **tier 2** NWP post-processor (`python -m nowcast.extended train`); the primary GPU is free while the burst runs |

**Ablation:** compare the radar-only control with the **overnight checkpoint**, and match them by `samples` seen, not by hours. Both are logged and stored in every checkpoint.

**Why two separate runs instead of DDP:** there is no NCCL/P2P risk on consumer cards, and you get an equal-compute ablation. Use DDP (`torchrun --nproc_per_node=2`) only if you give up the control run.

## 4. Burst server (3 h, 16 GB SSD, 120 GB RAM): RAM is the disk

`scripts/burst.sh all` runs the following, rehearsed on the primary with 1 GPU:

| Time | Phase |
|---|---|
| T+0:00 | `setup`: `ulimit -c 0`; venv, caches, TMPDIR and shards all in `/dev/shm`. Env install and shard download run in parallel. Checksums verified; `sm_120` asserted. |
| T+0:12 | `smoke`: 60 compiled steps per batch size (24 → 16 → 12 → 8); keep the largest that survives. |
| T+0:20 | `train`: both runs, `deadline_minutes: 120`, schedule fitted to the deadline. Atomic checkpoint every 10 min; off-box upload every 5 min (`PRIMARY_SSH` or `HF_CKPT_REPO`). |
| T+2:20 | `eval`: test-set metrics and example predictions for both runs, then upload. |
| T+2:40 | buffer |

**Data path:** shards are uploaded to a private HF dataset (or R2/S3) the night before, and `curl` pulls them straight into `/dev/shm`. With 1 Gbps, 20 GB takes about 3 min. Pushing from a home uplink during the window would take far too long.

**Why shards stay compressed in RAM:** per-event zstd blobs are mmapped from tmpfs, so pages are shared by every DataLoader worker and by both runs. Workers decompress each sample (~5 ms) on the 48 cores.

**Disk-full vectors, and what closes each one**

| Vector | Fix |
|---|---|
| Core dumps | `ulimit -c 0` |
| pip / uv caches | disabled |
| Inductor / Triton caches | moved to `/dev/shm` |
| Logs | tiny JSON lines only |
| Checkpoints | one rolling `latest.pt` per run, plus a free-space check before every save (`min_free_gb`) |

**Failure modes and responses**

| Problem | Response |
|---|---|
| `no kernel image` | use torch ≥ 2.7 with cu128+ wheels, the same version as the primary |
| `/dev/shm` too small (container) | `mount -o remount,size=90G /dev/shm` or `--shm-size` |
| compile trouble | `--set train.compile=false` |
| box dies | resume from the last uploaded `latest.pt`; the overnight model is the fallback |

## 5. India

Training is on the US because SEVIR is the only open, co-registered 4-source archive. The Indian equivalents map one to one:

| SEVIR input | Indian equivalent |
|---|---|
| NEXRAD | IMD DWR |
| GOES IR / WV | INSAT-3DS TIR1 / WV (MOSDAC) |
| GLM | IITM lightning network |
| HRRR | NCUM / IMD-GFS |

Modality dropout lets the model run **without radar**: pass `force_missing=("vil",)`, or `--drop vil` in `evaluate.py`. For an India demo:
- Feed INSAT IR on the same quantisation.
- Provide an NWP source mapped onto the same `NWP_VARS` list (ERA5 has CAPE, CIN, TCWV and shear from u/v levels; any field that is unavailable stays NaN, which becomes 0 after normalisation).
- Treat demo skill as qualitative: this is a domain shift from the US training data.
