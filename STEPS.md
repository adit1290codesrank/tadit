# STEPS: what to run, in order, until submission (30 Sep)

Run every command from the repo root unless it says otherwise.
Times are estimates; the ✅ lines say what "done" looks like.
Deadline rules are in **bold**; follow them rather than waiting.

---

## DAY 1 (28 Sep): data + overnight training

### Step 1: Get the code and environment (primary server, 20 min)

```bash
git clone https://github.com/adit1290codesrank/sih2026.git && cd sih2026
git checkout main
python3 -m venv .venv && source .venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -e ".[data,dev]"
python -c "import torch; print(torch.__version__, torch.cuda.is_available())"
pytest -q
```

✅ `True` printed, and `35 passed`.

📝 **Write down the torch version** (e.g. `2.8.0`, without the `+cu128` suffix). The burst server must install exactly this version.

### Step 2: Pick events and time the downloads (15 min)

```bash
python scripts/select_events.py --out work/events.csv
python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --limit-jobs 20 --workers 12
python scripts/build_shards.py --events work/events.csv --nwp work/nwp --out shards_trial --splits train --limit 100 --workers 12
rm -rf shards_trial
```

✅ The first command prints ~7,500 events. The last one prints `MB/event compressed` (expect ~2.8) and an ETA.

If the extrapolated times are too long for today, shrink the selection. Halving the events halves every step below:
`--n-train 3000 --n-val 300 --n-test 600`

### Step 3: Full data build (run all three at the same time, ~1–2 h)

Use three terminals, or `tmux`. Start them together:

```bash
# A: HRRR for tier 1 (~30 min)
python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --workers 12

# B: HRRR for tier 2, lead hours 1-3 first (~1 h)
python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --mode ext --fxx 2,3,4 --workers 8
```

When **A** has finished, start C:

```bash
# C: SEVIR -> shards (~1 h). Needs A's output for NWP.
python scripts/build_shards.py --events work/events.csv --nwp work/nwp --out shards --workers 12
```

✅ C ends with `[test] done: ... events` and ~20 GB in `shards/`. A few `failed` events or hours are normal.

Afterwards, if time allows, extend tier 2 to hours 4–6 (it can run overnight):

```bash
python scripts/fetch_hrrr.py --events work/events.csv --out work/nwp --mode ext --fxx 5,6,7 --workers 8
```

### Step 4: GPU smoke test (20 min)

```bash
python -m nowcast.train --config configs/dev.yaml \
  --set train.out_dir=runs/smoke --set train.max_steps=200 --set train.deadline_minutes=null \
  --set train.log_every=20 --set train.val_every_min=3
```

✅ `loss` goes down over the log lines, and a `"event": "val"` line appears.

Check `peak_mem_gb` against the 16 GB card:
- well under ~13 GB: increase `train.batch_size` in `configs/dev.yaml` (it is 6) and rerun until it's close;
- out of memory: lower it.

Then try `--set train.compile=true` once. If it errors, leave compile off.

```bash
rm -rf runs/smoke
```

### Step 5: Start the overnight run (before you sleep)

Set `deadline_minutes` to the minutes from **now** until you need the checkpoint. That's the burst start, or tomorrow ~10:00 if there's no burst. Example for 9 h:

```bash
nohup python -m nowcast.train --config configs/dev.yaml --set train.deadline_minutes=540 > overnight.log 2>&1 &
tail -f overnight.log
```

✅ Log lines every ~50 steps; `runs/overnight/latest.pt` appears within 15 min.

Leave it running.

### Step 6: Stage data for the burst server (while training runs, ~1–2 h of upload)

Skip this step if you will not use the burst server.

```bash
pip install -U huggingface_hub
huggingface-cli login                       # token with WRITE access
# on huggingface.co: New -> Dataset -> name "sih-shards" -> Private (and New -> Model -> "sih-ckpt" -> Private)
bash scripts/stage_shards.sh shards hf <your-hf-username>/sih-shards
```

✅ It prints `BASE=https://huggingface.co/datasets/<user>/sih-shards/resolve/main`. Save that line.

**If the upload is too slow to finish by morning:** the burst server can pull straight from the primary instead. Run `bash scripts/stage_shards.sh shards serve` on the primary, then use `BASE=http://<primary-ip>:8000` in Step 8 (only if the burst server can reach the primary).

---

## DAY 2 (29 Sep): results

### Step 7: Upload the overnight checkpoint (5 min, just before the burst)

```bash
huggingface-cli upload <your-hf-username>/sih-shards runs/overnight/latest.pt ckpt/overnight_latest.pt --repo-type dataset
```

### Step 8: Burst server (3 h window)

On the burst server:

```bash
mkdir -p /dev/shm/w && git clone https://github.com/adit1290codesrank/sih2026.git /dev/shm/w/code
cd /dev/shm/w/code && git checkout main
export BASE=https://huggingface.co/datasets/<your-hf-username>/sih-shards/resolve/main
export HF_TOKEN=<your token>
export OVERNIGHT_URL=$BASE/ckpt/overnight_latest.pt
export TORCH_VER=<version from step 1, e.g. 2.8.0>
export HF_CKPT_REPO=<your-hf-username>/sih-ckpt   # the private model repo created in step 6
bash scripts/burst.sh all 2>&1 | tee burst.log
```

What `burst.sh all` does:

| Time | Phase |
|---|---|
| ~15 min | setup |
| ~10 min | smoke test and batch size |
| 2 h | training: GPU0 continues the full model, GPU1 trains the radar-only control |
| ~20 min | evaluation |
| continuous | upload of checkpoints and results |

Watch progress with `tail -f /dev/shm/w/tmp/full.log`.

✅ `ckpt/results/*.json` and `ckpt/{full,radar}/final_ema_bf16.pt` are uploaded to `sih-ckpt`.

**If setup or smoke fails and you cannot fix it in 20 min:** stop, and use the overnight model for everything below. That's the plan B, not a failure.

### Step 9: Tier 2 (primary GPU, in parallel with the burst, ~1 h)

Stop the overnight run first if it's still going: `pkill -f nowcast.train`. Training catches the signal, saves `latest.pt` and `final_ema_bf16.pt`, then exits (give it a minute). Then:

```bash
python -m nowcast.extended build --shards shards --nwp work/nwp --out ext --leads 1,2,3,4,5,6
python -m nowcast.extended train --data ext --out runs/ext --epochs 20
python -m nowcast.extended eval --ckpt runs/ext/best.pt --data ext/test --out results/ext.json
python -m nowcast.extended eval --ckpt runs/ext/best.pt --data ext/test --out results/ext_india_mode.json --india-mode
```

- If you only fetched `--fxx 2,3,4`, use `--leads 1,2,3` in the build.
- ✅ `eval` prints per lead hour: model CSI vs HRRR LTNG vs HRRR REFC.

### Step 10: Tier-1 results

**If the burst worked:** download its results.

```bash
huggingface-cli download <your-hf-username>/sih-ckpt --local-dir burst_out
cp burst_out/burst/results/*.json results/
```

**If there was no burst:** evaluate the overnight model (~30 min).

```bash
python -m nowcast.evaluate --ckpt runs/overnight/final_ema_bf16.pt --data shards/test --out results/full.json --save-examples 48
python -m nowcast.evaluate --ckpt runs/overnight/final_ema_bf16.pt --data shards/test --out results/full_india_mode.json --india-mode
python -m nowcast.evaluate --ckpt runs/overnight/final_ema_bf16.pt --data shards/test --out results/no_radar.json --drop vil
python -m nowcast.evaluate --ckpt runs/overnight/final_ema_bf16.pt --data shards/test --out results/no_nwp.json --drop nwp
```

Always run the persistence baseline:

```bash
python -m nowcast.evaluate --baseline persistence --data shards/test --out results/persistence.json
```

### Step 11: The 0–6 h scorecard (the key slide)

```bash
python scripts/crossover.py --tier1 results/full.json results/persistence.json --tier2 results/ext.json
```

Add `results/radar.json` to `--tier1` if the burst produced it.

✅ A markdown table of lightning CSI per lead hour. The first hour where `tier2_model` beats `full` is your **switch hour**.

### Step 12: India demo runs (~15 min per case)

Choose 3–4 real storm afternoons over Odisha, West Bengal, Jharkhand or the North-East: April–June 2023 or later, around 08–11 UTC. To find dates, search news for "Odisha lightning deaths" or "Kalbaisakhi" with a month and year. **2024-05-10 09 UTC** is already known to have deep convection near Bhubaneswar.

For each case:

```bash
python -m nowcast.india.run --city Bhubaneswar --time 2024-05-10T09:00 --gk2a \
  --tier1 runs/overnight/final_ema_bf16.pt --tier2 runs/ext/best.pt \
  --switch-hour <from step 11> --out results/india
```

- Replace the tier-1 checkpoint with `burst_out/burst/full/final_ema_bf16.pt` if the burst worked.
- If your MOSDAC account works, download INSAT-3DR/3DS L1B files for the case into `data/insat/` and add `--insat-dir data/insat`. INSAT is then used first and GK2A becomes the fallback.

✅ `results/india/<city>_<time>.json` (hourly risk and data provenance) and `.npz` (maps).

### Step 12b: Website data (server, 1 min per export)

The website never runs the models. It reads static files exported from the pipeline outputs. The data format is in `docs/SITE_DATA.md`.

```bash
python scripts/export_site.py --results results --figures figures --cases site/cases.json --out site/public/data
# add --boundary <ISRO Bhuvan India GeoJSON> for the map outline (never Natural Earth)
```

Run it on the server, where the India `.npz` map files exist, so map overlays are included. Re-run after every new India run.

Deploy from the server (Cloudflare Pages, free):

```bash
cd site && npm run build && npx wrangler pages deploy dist --project-name <name>
```

Log in once first with `npx wrangler login`.

### Step 13: Figures and slides (evening)

The figures to make:
1. The 0–6 h scorecard chart (step 11).
2. CSI vs lead time: full model vs persistence vs radar-only (or `--drop` runs).
3. `full` vs `full_india_mode` (the model on INSAT-like and GFS-like inputs).
4. Forecast example panels (`results/full_examples.npz`).
5. India case maps and risk timelines (`results/india/*.npz` and `.json`).

A script to generate all of these from the result files is not written yet; ask for it.

Slide order:
1. Problem (IMD, lightning deaths, 3-hour warnings)
2. The 4 sources
3. Architecture
4. Scorecard
5. Ablations
6. India runs
7. Honest limits and next steps: IITM ILLN, IMD radar, INSAT

---

## DAY 3 (30 Sep): submit

- **No new code.** Re-run anything that failed, polish the slides, record the demo video, and push final results/figures (not data or checkpoints).
- Submit early in the day, not at the deadline.

---

## When things go wrong

| Problem | Do this |
|---|---|
| `pytest` fails on the server | Check that `pip install -e ".[data,dev]"` finished. Show me the error. |
| HRRR fetch shows many `FAILED` hours | A few are normal: missing hours become "NWP missing", which the model handles. If more than 20% fail, rerun the same command; it skips finished files. |
| Build too slow | Shrink the selection (Step 2) and rebuild. The code needs no change. |
| GPU out of memory | Lower `train.batch_size` in `configs/dev.yaml`. |
| Loss is `nan` | Add `--set train.lr=2.5e-4` and restart. |
| Disk full on the primary | Delete `shards_trial/` and any `runs/smoke/`. `work/nwp/` can go after Step 3 **and** Step 9 are done. |
| Burst: `no kernel image` | `TORCH_VER` doesn't match a cu128 build. Use the exact version from Step 1. |
| Burst: `/dev/shm has only ...G` | As root: `mount -o remount,size=90G /dev/shm`. Otherwise, use plan B (overnight model). |
| Running out of time | Cut in this order: pySTEPS → tier-2 hours 5–6 → radar-only control → burst server. **Never cut:** scorecard, one India run, the honest "trained in the US, adapted to India" label. |

## Ground rules

- **Never commit** `shards/`, `work/`, `runs/`, `ext/` or `*.pt`; `.gitignore` already covers them.
- Compare models at **equal `samples`** (in every log line and checkpoint), not equal hours.
- Report numbers as measured. Say "trained on US GLM lightning, adapted to INSAT/GFS, not yet verified against Indian lightning observations" wherever skill over India comes up.
