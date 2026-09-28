#!/usr/bin/env bash
# Burst-server runbook (2x RTX 5090, 120 GB RAM, 16 GB SSD). Rehearse it on the primary first.
#
# Everything lives in RAM (/dev/shm/w): venv, shards, compile caches, tmp. The SSD only holds
# ckpt/{full,radar}/latest.pt + final_ema_bf16.pt, which are also pushed off-box every 5 min.
#
#   git clone <repo> /dev/shm/w/code && cd /dev/shm/w/code
#   export BASE=https://huggingface.co/datasets/<org>/<repo>/resolve/main   # or http://<primary>:8000
#   export HF_TOKEN=...            # only for a private HF repo
#   export OVERNIGHT_URL=$BASE/ckpt/overnight_latest.pt   # optional: GPU0 continues this run
#   export PRIMARY_SSH=user@primary:/data/burst_ckpt      # or HF_CKPT_REPO=<org>/<repo> for uploads
#   export TORCH_VER=2.8.0         # EXACTLY the version tested on the primary (cu128 wheels)
#   bash scripts/burst.sh all      # or: setup | smoke | train | eval | upload
set -euo pipefail
ulimit -c 0   # a core dump of a 50 GB process fills the SSD instantly

W=${W:-/dev/shm/w}
CKPT=${CKPT:-$HOME/ckpt}
REPO_DIR=$(cd "$(dirname "$0")/.." && pwd)
export TMPDIR=$W/tmp XDG_CACHE_HOME=$W/cache HF_HOME=$W/cache/hf \
  TORCHINDUCTOR_CACHE_DIR=$W/cache/inductor TRITON_CACHE_DIR=$W/cache/triton \
  UV_NO_CACHE=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$REPO_DIR/src
export BASE=${BASE:-} HF_TOKEN=${HF_TOKEN:-}
mkdir -p "$W"/{tmp,cache,data} "$CKPT"/{full,radar,results}
log() { echo "[$(date +%H:%M:%S)] $*"; }

fetch() {  # fetch <relative path> -> $W/data/<path>, straight into RAM
  mkdir -p "$(dirname "$1")"
  curl -sfL --retry 5 --retry-delay 2 ${HF_TOKEN:+-H "Authorization: Bearer $HF_TOKEN"} "$BASE/$1" -o "$1"
}
export -f fetch

setup() {
  : "${BASE:?set BASE}" "${TORCH_VER:?set TORCH_VER}"
  df -h / /dev/shm; free -g
  nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
  nvidia-smi topo -m || true
  local shm_gb
  shm_gb=$(df -BG --output=avail /dev/shm | tail -1 | tr -dc 0-9)
  if (( shm_gb < 40 )); then
    log "/dev/shm has only ${shm_gb}G. As root: mount -o remount,size=90G /dev/shm (Docker: --shm-size=90g)"
    exit 1
  fi

  log "env + data download in parallel (logs: $W/tmp/{env,data}.log)"
  (
    command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH=$HOME/.local/bin:$PATH
    uv venv "$W/venv" -p 3.11
    uv pip install -p "$W/venv" "torch==$TORCH_VER" --index-url https://download.pytorch.org/whl/cu128
    uv pip install -p "$W/venv" numpy zstandard pyyaml ${HF_CKPT_REPO:+huggingface_hub}
  ) > "$W/tmp/env.log" 2>&1 &
  local envpid=$!
  (
    cd "$W/data"
    fetch manifest.sha256
    # manifest lists train shards first, so a slow link still gets the training data early
    awk '{print $2}' manifest.sha256 | xargs -P 8 -I{} bash -c 'fetch "$1"' _ {}
    sha256sum -c --quiet manifest.sha256
    if [[ -n "${OVERNIGHT_URL:-}" ]]; then
      curl -sfL --retry 5 ${HF_TOKEN:+-H "Authorization: Bearer $HF_TOKEN"} "$OVERNIGHT_URL" -o "$W/overnight.pt"
    fi
  ) > "$W/tmp/data.log" 2>&1 &
  local datapid=$!
  wait $envpid || { tail -30 "$W/tmp/env.log"; exit 1; }
  log "env ready"
  wait $datapid || { tail -30 "$W/tmp/data.log"; exit 1; }
  log "data ready: $(du -sh "$W/data" | cut -f1)"
  "$W/venv/bin/python" -c "import torch; c=[torch.cuda.get_device_capability(i) for i in range(torch.cuda.device_count())]; print('torch', torch.__version__, 'capabilities', c); assert all(x >= (12, 0) for x in c), 'expected Blackwell sm_120'"
}

resume_args() { [[ -f "$W/overnight.pt" ]] && echo "--resume $W/overnight.pt" || true; }

smoke() {
  source "$W/venv/bin/activate"
  cd "$REPO_DIR"
  # Largest batch that survives 60 compiled steps. Each attempt includes compile time (~1-2 min).
  for bs in ${SMOKE_BATCHES:-24 16 12 8}; do
    log "smoke: batch $bs"
    if CUDA_VISIBLE_DEVICES=0 python -m nowcast.train --config configs/burst.yaml $(resume_args) \
        --set train.out_dir="$W/tmp/smoke" --set train.max_steps=60 --set train.deadline_minutes=null \
        --set train.batch_size=$bs --set train.log_every=20 --set data.val_dir=null \
        > "$W/tmp/smoke_$bs.log" 2>&1; then
      echo "$bs" > "$W/batch_size"
      grep '"step": 60' "$W/tmp/smoke_$bs.log" || tail -3 "$W/tmp/smoke_$bs.log"
      rm -rf "$W/tmp/smoke"
      log "smoke OK -> batch size $bs"
      return 0
    fi
    tail -5 "$W/tmp/smoke_$bs.log"
    rm -rf "$W/tmp/smoke"
  done
  log "smoke failed at every batch size; retry with --set train.compile=false"
  exit 1
}

upload() {
  if [[ -n "${PRIMARY_SSH:-}" ]]; then
    rsync -a --partial "$CKPT"/ "$PRIMARY_SSH"/ && log "uploaded -> $PRIMARY_SSH"
  elif [[ -n "${HF_CKPT_REPO:-}" ]]; then
    "$W/venv/bin/python" - <<EOF && log "uploaded -> hf:$HF_CKPT_REPO"
from huggingface_hub import HfApi
HfApi().upload_folder(folder_path="$CKPT", repo_id="$HF_CKPT_REPO", repo_type="model", path_in_repo="burst")
EOF
  else
    log "WARNING: no PRIMARY_SSH / HF_CKPT_REPO; checkpoints only exist on this box"
  fi
}

upload_loop() { while sleep 300; do upload || log "upload failed (will retry)"; done; }

train() {
  source "$W/venv/bin/activate"
  cd "$REPO_DIR"
  local bs; bs=$(cat "$W/batch_size" 2>/dev/null || echo 16)
  log "training: batch $bs, 2 independent runs (no NCCL). tail -f $W/tmp/{full,radar}.log"
  CUDA_VISIBLE_DEVICES=0 python -m nowcast.train --config configs/burst.yaml $(resume_args) \
    --set train.out_dir="$CKPT/full" --set train.batch_size=$bs > "$W/tmp/full.log" 2>&1 &
  local p0=$!
  CUDA_VISIBLE_DEVICES=1 python -m nowcast.train --config configs/burst.yaml \
    --set 'model.modalities=[vil]' --set train.warmup_steps=500 \
    --set train.out_dir="$CKPT/radar" --set train.batch_size=$bs > "$W/tmp/radar.log" 2>&1 &
  local p1=$!
  upload_loop & local up=$!
  local rc=0
  wait $p0 || { rc=1; log "full run failed: tail $W/tmp/full.log"; }
  wait $p1 || { rc=1; log "radar run failed: tail $W/tmp/radar.log"; }
  kill $up 2>/dev/null || true
  cp "$W"/tmp/{full,radar}.log "$CKPT/results/" 2>/dev/null || true
  upload || true
  return $rc
}

evaluate() {
  source "$W/venv/bin/activate"
  cd "$REPO_DIR"
  CUDA_VISIBLE_DEVICES=0 python -m nowcast.evaluate --ckpt "$CKPT/full/final_ema_bf16.pt" \
    --data "$W/data/test" --out "$CKPT/results/full.json" --save-examples 48 &
  CUDA_VISIBLE_DEVICES=1 python -m nowcast.evaluate --ckpt "$CKPT/radar/final_ema_bf16.pt" \
    --data "$W/data/test" --out "$CKPT/results/radar.json" &
  wait
  # the same model scored on INSAT-like satellite + GFS-like NWP inputs (what it gets over India)
  CUDA_VISIBLE_DEVICES=0 python -m nowcast.evaluate --ckpt "$CKPT/full/final_ema_bf16.pt" \
    --data "$W/data/test" --out "$CKPT/results/full_india_mode.json" --india-mode &
  CUDA_VISIBLE_DEVICES=1 python -m nowcast.evaluate --ckpt "$CKPT/full/final_ema_bf16.pt" \
    --data "$W/data/test" --out "$CKPT/results/full_india_mode_no_radar.json" --india-mode --drop vil,lght &
  wait
  upload
}

case "${1:-all}" in
  setup) setup ;;
  smoke) smoke ;;
  train) train ;;
  eval) evaluate ;;
  upload) upload ;;
  all) setup; smoke; train; evaluate ;;
  *) echo "usage: $0 {setup|smoke|train|eval|upload|all}"; exit 2 ;;
esac
