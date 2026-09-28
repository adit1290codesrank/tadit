#!/usr/bin/env bash
# Primary server: write the manifest (train shards first) and stage shards for the burst server.
#
#   bash scripts/stage_shards.sh shards                       # manifest only
#   bash scripts/stage_shards.sh shards serve                 # http://<primary>:8000 (burst BASE)
#   bash scripts/stage_shards.sh shards hf <org>/<dataset>    # private HF dataset (upload overnight)
set -euo pipefail
ROOT=${1:?shard root}; MODE=${2:-manifest}; REPO=${3:-}
cd "$ROOT"
: > manifest.sha256
for split in train val test; do
  [[ -d $split ]] || continue
  find "$split" -type f \( -name '*.bin' -o -name '*.idx.npy' -o -name 'nwp_stats.json' \) | sort \
    | xargs -r sha256sum >> manifest.sha256
done
echo "manifest: $(wc -l < manifest.sha256) files, $(du -shc train val test 2>/dev/null | tail -1 | cut -f1)"

case "$MODE" in
  manifest) ;;
  serve) exec python3 -m http.server 8000 --bind 0.0.0.0 ;;
  hf)
    : "${REPO:?give <org>/<dataset>}"
    huggingface-cli upload-large-folder "$REPO" . --repo-type dataset
    echo "BASE=https://huggingface.co/datasets/$REPO/resolve/main"
    ;;
  *) echo "unknown mode $MODE"; exit 2 ;;
esac
