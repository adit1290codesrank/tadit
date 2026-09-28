# SIH26072: Multimodal Thunderstorm & Lightning Nowcasting

Seamless **0–6 h** thunderstorm and lightning forecasts in two tiers:

- **Tier 1 (0–3 h, 10-min steps):** multimodal fusion of radar, satellite, lightning and NWP.
- **Tier 2 (lead hours 1–6):** ML post-processing of HRRR forecasts, trained against observed lightning and radar.

The product switches from tier 1 to tier 2 at the measured crossover hour (`scripts/crossover.py`).
IMD's operational nowcasts cover the next 3 h; see `docs/PLAN.md` §0 for the sources.

The four sources:

| Modality | Source | Grid in shards |
|---|---|---|
| Doppler weather radar | SEVIR `vil` (NEXRAD mosaic) | 192 × 192 @ 2 km, 5 min |
| Satellite | SEVIR `ir069`, `ir107` (GOES-16 ABI) | 192 × 192 @ 2 km, 5 min |
| Lightning | SEVIR `lght` (GOES-16 GLM flashes) | 48 × 48 @ 8 km, 5 min |
| NWP | HRRR f01 (run init = valid − 1 h, so no leakage) | 48 × 48 @ 8 km, hourly |

The model is a **mid-fusion U-Net**:
- each modality gets its own stem (encoder) at native resolution; the features are gated and fused
- NWP is fed in through **cross-attention in the bottleneck** and **FiLM** conditioning
- **modality dropout** during training, so it can run with a sensor missing
- it predicts all 18 lead times (10–180 min) of VIL and lightning probability in one pass

See `docs/PLAN.md` for the reasoning, the dataset ranking and the burst-server runbook.

## India

The models run on Indian data:
- **INSAT-3DR/3DS** L1B (MOSDAC)
- **GFS** (open)
- **IMD DWR** reflectivity
- **Indian lightning networks** (IITM ILLN CSV, or ISS-LIS for verification)

Satellite and NWP inputs are adapted *in training* (INSAT resolution and scan rate, GFS variables). Any missing source is handled by modality dropout.

```bash
python -m nowcast.india.run --city Bhubaneswar --time 2024-05-10T09:00 \
    --insat-dir data/insat --tier1 runs/full/final_ema_bf16.pt --tier2 runs/ext/best.pt --out results/india
```

`docs/PLAN.md` §5 covers what is open, what needs registration, and what to request today.

## Layout

```
src/nowcast/
  data/sevir.py      catalog filtering, S3 reads, IR units, leak-free lightning gridding, geometry
  data/hrrr.py       Herbie byte-range fetch, derived fields, KD-tree regridding
  data/shards.py     per-event zstd blobs + mmap index (same format on both servers)
  data/dataset.py    random 25-frame windows, NWP hour selection, 90° rotations, prepare_batch
  data/synthetic.py  fake events in the real format (tests / pipeline dev)
  india/             tiles, INSAT L1B reader, GFS, IMD radar (dBZ), lightning CSV / ISS-LIS, run.py CLI
  model/fusion.py    FusionNowcaster (tier 1)
  extended.py        tier 2: build / train / eval of the HRRR post-processor (+ raw-HRRR baselines)
  losses.py          intensity-weighted VIL loss + focal lightning loss
  metrics.py         CSI (pool 1/4/16) per threshold & lead, lightning CSI/POD/FAR/Brier
  train.py           wall-clock LR schedule, atomic checkpoints, resume / init-from, DDP-capable
  evaluate.py        test metrics, --drop ablations, persistence / pySTEPS baselines
scripts/
  select_events.py   -> work/events.csv
  fetch_hrrr.py      -> work/nwp/<hour>.npz (tier 1, f01, 8 km); --mode ext -> work/nwp/f0X_g24/ (tier 2)
  check_alignment.py verify row order + lightning x/y units before building
  build_shards.py    -> shards/{train,val,test}
  stage_shards.sh    manifest + serve over HTTP or upload to HF
  burst.sh           3-hour burst runbook (setup | smoke | train | eval)
  make_synthetic.py  synthetic shards
  crossover.py       0-6 h scorecard: lightning CSI per lead hour, tier 1 vs tier 2 vs raw HRRR
configs/  dev.yaml (4060 Ti)  burst.yaml (5090)  smoke.yaml (CPU)
```

## Quickstart

```bash
# PyTorch >= 2.7 with CUDA 12.8+ wheels on BOTH servers (the RTX 5090 is sm_120).
# Use the same version on both, so checkpoints resume cleanly.
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -e ".[data,dev]"

pytest -q                                   # everything runs on synthetic data, CPU is fine

# Develop the training loop before real data exists
python scripts/make_synthetic.py --out shards/tiny --hr 64 --lr 16 --n-train 32 --n-val 8 --n-test 8
python -m nowcast.train --config configs/smoke.yaml
```

## Real-data pipeline (primary server)

```bash
python scripts/select_events.py --out work/events.csv --n-train 6000 --n-val 500 --n-test 1000
python scripts/fetch_hrrr.py --inventory "2018-06-01 18:00"   # every field should print OK
python scripts/fetch_hrrr.py --inventory "2017-06-01 18:00"   # HRRRv2 period too
python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --limit-hours 20   # time it
python scripts/check_alignment.py --events work/events.csv --n 12                       # fix flags if told
python scripts/build_shards.py --events work/events.csv --nwp work/nwp --splits train --limit 100  # measure MB/event
python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --workers 12
python scripts/build_shards.py --events work/events.csv --nwp work/nwp --out shards --workers 12
# tier 2 (hours 1-6): 40,950 HRRR downloads; start f02-f04 first if short on time
python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --mode ext --fxx 2,3,4,5,6,7 --workers 12
python -m nowcast.extended build --shards shards --nwp work/nwp --out ext
```

## Training & evaluation

```bash
# overnight fallback on the 4060 Ti (9 h wall clock; LR schedule fits the deadline)
python -m nowcast.train --config configs/dev.yaml

# burst server: see docs/PLAN.md §3 and scripts/burst.sh
bash scripts/stage_shards.sh shards hf <org>/<dataset>      # the night before

python -m nowcast.evaluate --ckpt runs/overnight/final_ema_bf16.pt --data shards/test --out results/full.json
python -m nowcast.evaluate --ckpt ... --drop nwp --out results/no_nwp.json      # ablation, no retraining
python -m nowcast.evaluate --baseline persistence --data shards/test --out results/persistence.json
python -m nowcast.evaluate --baseline pysteps --data shards/test --out results/pysteps.json

# tier 2 (trains on the primary while the burst runs)
python -m nowcast.extended train --data ext --out runs/ext --epochs 20
python -m nowcast.extended eval --ckpt runs/ext/best.pt --data ext/test --out results/ext.json

# the 0-6 h scorecard (markdown table)
python scripts/crossover.py --tier1 results/full.json results/radar.json results/persistence.json --tier2 results/ext.json
```

Compare models at **equal samples seen** (`samples` is logged and stored in every checkpoint), not
at equal wall-clock time: the two GPU types run at different speeds.
