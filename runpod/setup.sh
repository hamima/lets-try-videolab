#!/usr/bin/env bash
# setup.sh — One-time RunPod pod setup for LTX-Video I2V direct server
# Run this once after creating the pod: bash runpod/setup.sh
#
# On subsequent pod restarts, just run:
#   bash runpod/setup.sh --start-only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$SCRIPT_DIR/server_config.json"
START_ONLY="${1:-}"

# ─── Detect storage root ────────────────────────────────────────────────────
# Prefer a mounted RunPod Network Volume (/runpod-volume) so model weights and
# outputs survive pod stop/restart. Fall back to /workspace (ephemeral).
if mountpoint -q /runpod-volume 2>/dev/null; then
  STORAGE_ROOT="/runpod-volume"
  echo "[storage] Network volume detected — using /runpod-volume"
else
  STORAGE_ROOT="/workspace"
  echo "[storage] No network volume — using /workspace (ephemeral on pod stop)"
fi

MODEL_DIR="$STORAGE_ROOT/models/LTX-Video"
OUTPUT_DIR="$STORAGE_ROOT/ltx_outputs"

if [[ "$START_ONLY" != "--start-only" ]]; then
  echo ""
  echo "=== Step 1: Install Python dependencies ==="
  pip install --upgrade pip
  pip install \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.29.0" \
    "diffusers>=0.30.0" \
    "transformers>=4.42.0" \
    "accelerate>=0.30.0" \
    "imageio[ffmpeg]>=2.34.0" \
    "Pillow>=10.0.0"

  echo ""
  echo "=== Step 2: Download LTX-Video model weights (~12GB) ==="
  echo "Destination: $MODEL_DIR"
  python - "$MODEL_DIR" <<'PYEOF'
import sys
from huggingface_hub import snapshot_download
dest = sys.argv[1]
print(f"Downloading Lightricks/LTX-Video to {dest} ...")
print("(already-present files are skipped — safe to re-run)")
snapshot_download(
    repo_id="Lightricks/LTX-Video",
    revision="main",
    local_dir="/workspace/models/LTX-Video",
    allow_patterns=[
        "model_index.json",
        "scheduler/**",
        "tokenizer/**",
        "text_encoder/**",
        "transformer/**",
        "vae/**",
    ],
)
print("Download complete.")
PYEOF
fi

# ─── Update server_config.json with resolved paths ──────────────────────────
python - "$CONFIG" "$MODEL_DIR" "$OUTPUT_DIR" <<'PYEOF'
import json, sys
config_path, model_dir, output_dir = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.loads(open(config_path).read())
cfg["model_id"] = model_dir
cfg["output_dir"] = output_dir
open(config_path, "w").write(json.dumps(cfg, indent=2))
print(f"[config] model_id   → {model_dir}")
print(f"[config] output_dir → {output_dir}")
PYEOF

echo ""
echo "=== Starting LTX-Video I2V server ==="
echo "Config: $CONFIG"
python - "$CONFIG" <<'PYEOF'
import json, sys
cfg = json.loads(open(sys.argv[1]).read())
print(f"  model_id            : {cfg['model_id']}")
print(f"  host:port           : {cfg['host']}:{cfg['port']}")
print(f"  idle_timeout_minutes: {cfg['idle_timeout_minutes']} (0 = disabled)")
print(f"  output_dir          : {cfg['output_dir']}")
print(f"  resolution          : {cfg['width']}x{cfg['height']}")
PYEOF
echo ""
echo "Edit $CONFIG to change these settings before restarting."
echo "Server auto-shuts down after idle_timeout_minutes of inactivity."
echo ""

cd "$SCRIPT_DIR"
SERVER_CONFIG="$CONFIG" python server.py
