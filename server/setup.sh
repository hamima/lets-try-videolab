#!/usr/bin/env bash
# setup.sh — One-time Hyperstack setup for Wan2.2 A14B I2V inference server
# All large files are stored under /mnt/vidlab.
#
# Run once:
#   bash setup.sh
#
# On subsequent server restarts:
#   bash setup.sh --start-only
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$SCRIPT_DIR/server_config.json"
START_ONLY="${1:-}"

# ─── Single persistent storage mount ────────────────────────────────────────
STORAGE_ROOT="/mnt/vidlab"

VENV_DIR="$STORAGE_ROOT/venvs/wan2.2-i2v"
MODEL_DIR="$STORAGE_ROOT/models/Wan2.2-I2V-A14B-Diffusers"
OUTPUT_DIR="$STORAGE_ROOT/wan_outputs"
CACHE_DIR="$STORAGE_ROOT/cache"
TMP_DIR="$STORAGE_ROOT/tmp"
MODEL_REPO="Wan-AI/Wan2.2-I2V-A14B-Diffusers"

# Keep all caches and temporary files on /mnt/vidlab.
export HF_HOME="$CACHE_DIR/huggingface"
export HF_HUB_CACHE="$HF_HOME/hub"
export HUGGINGFACE_HUB_CACHE="$HF_HUB_CACHE"
export HF_XET_CACHE="$HF_HOME/xet"
export HF_HUB_ENABLE_HF_TRANSFER="0"

export PIP_CACHE_DIR="$CACHE_DIR/pip"
export TORCH_HOME="$CACHE_DIR/torch"
export XDG_CACHE_HOME="$CACHE_DIR/xdg"

export TMPDIR="$TMP_DIR"
export TMP="$TMP_DIR"
export TEMP="$TMP_DIR"

# ─── Verify mount ───────────────────────────────────────────────────────────
if ! mountpoint -q "$STORAGE_ROOT"; then
  echo "ERROR: $STORAGE_ROOT is not mounted."
  echo "Mount the persistent disk before running this script."
  exit 1
fi

if [[ ! -w "$STORAGE_ROOT" ]]; then
  echo "ERROR: $STORAGE_ROOT is not writable by the current user."
  echo "Fix ownership with:"
  echo "  sudo chown -R $(id -u):$(id -g) $STORAGE_ROOT"
  exit 1
fi

mkdir -p \
  "$VENV_DIR" \
  "$MODEL_DIR" \
  "$OUTPUT_DIR" \
  "$HF_HUB_CACHE" \
  "$HF_XET_CACHE" \
  "$PIP_CACHE_DIR" \
  "$TORCH_HOME" \
  "$XDG_CACHE_HOME" \
  "$TMP_DIR"

echo ""
echo "=== Storage configuration ==="
echo "Storage root : $STORAGE_ROOT"
echo "Python env   : $VENV_DIR"
echo "Model        : $MODEL_DIR"
echo "Outputs      : $OUTPUT_DIR"
echo "Cache        : $CACHE_DIR"
echo "Temporary    : $TMP_DIR"
echo ""

df -h "$STORAGE_ROOT"

if [[ "$START_ONLY" != "--start-only" ]]; then
  echo ""
  echo "=== Step 1: Verify NVIDIA GPU ==="

  if ! command -v nvidia-smi >/dev/null 2>&1; then
    echo "ERROR: nvidia-smi was not found."
    echo "The NVIDIA driver must be installed before running this setup."
    exit 1
  fi

  nvidia-smi

  echo ""
  echo "=== Step 2: Check available persistent storage ==="

  AVAILABLE_KB="$(df --output=avail -k "$STORAGE_ROOT" | tail -1 | tr -d ' ')"
  REQUIRED_KB=$((150 * 1024 * 1024))

  if (( AVAILABLE_KB < REQUIRED_KB )); then
    echo "ERROR: Wan2.2 I2V A14B requires about 126 GB for model files."
    echo "Keep at least 150 GB free for the model, environment, and temporary files."
    df -h "$STORAGE_ROOT"
    exit 1
  fi

  echo ""
  echo "=== Step 3: Create Python environment ==="

  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3 -m venv "$VENV_DIR"
  fi

  source "$VENV_DIR/bin/activate"

  echo "Python: $(which python)"
  echo "Pip   : $(which pip)"

  echo ""
  echo "=== Step 4: Install inference dependencies ==="

  python -m pip install --no-cache-dir --upgrade \
    pip \
    setuptools \
    wheel

  # CUDA 12.1 wheels are compatible with the installed 535-series driver.
  python -m pip install --no-cache-dir \
    "torch==2.5.1" \
    "torchvision==0.20.1" \
    --index-url https://download.pytorch.org/whl/cu121

  python -m pip install --no-cache-dir \
    "fastapi>=0.111.0" \
    "uvicorn[standard]>=0.29.0" \
    "diffusers>=0.35.0" \
    "transformers>=4.49.0" \
    "accelerate>=1.1.0" \
    "safetensors>=0.4.5" \
    "huggingface-hub[hf-xet]>=0.27.0" \
    "sentencepiece>=0.2.0" \
    "imageio>=2.34.0" \
    "imageio-ffmpeg>=0.5.1" \
    "Pillow>=10.0.0" \
    "ftfy>=6.2.0" \
    "tiktoken>=0.7.0" \
    "protobuf>=5.28.0" \
    "python-multipart>=0.0.12"

  echo ""
  echo "=== Step 5: Verify CUDA in PyTorch ==="

  python - <<'PYEOF'
import sys
import torch

print(f"PyTorch version : {torch.__version__}")
print(f"PyTorch CUDA    : {torch.version.cuda}")
print(f"CUDA available  : {torch.cuda.is_available()}")

if not torch.cuda.is_available():
    print("ERROR: PyTorch cannot access CUDA.", file=sys.stderr)
    sys.exit(1)

print(f"GPU             : {torch.cuda.get_device_name(0)}")
print(
    f"GPU memory      : "
    f"{torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB"
)
PYEOF

  echo ""
  echo "=== Step 6: Download Wan2.2 I2V A14B Diffusers model ==="
  echo "Repository  : $MODEL_REPO"
  echo "Destination : $MODEL_DIR"
  echo "HF cache    : $HF_HOME"
  echo "Temporary   : $TMP_DIR"

  "$VENV_DIR/bin/hf" download \
    "$MODEL_REPO" \
    --repo-type model \
    --local-dir "$MODEL_DIR"

  echo ""
  echo "=== Step 7: Remove temporary installation files ==="

  rm -rf "$TMP_DIR"/*
  rm -rf "$PIP_CACHE_DIR"/*

  echo ""
  echo "=== Storage usage after setup ==="

  du -sh "$VENV_DIR" 2>/dev/null || true
  du -sh "$MODEL_DIR" 2>/dev/null || true
  du -sh "$CACHE_DIR" 2>/dev/null || true
  du -sh "$OUTPUT_DIR" 2>/dev/null || true

  df -h "$STORAGE_ROOT"
else
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "ERROR: Python environment not found: $VENV_DIR"
    echo "Run without --start-only first."
    exit 1
  fi

  source "$VENV_DIR/bin/activate"
fi

# ─── Validate required files ────────────────────────────────────────────────
if [[ ! -f "$CONFIG" ]]; then
  echo "ERROR: Configuration file not found: $CONFIG"
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/server.py" ]]; then
  echo "ERROR: Server file not found: $SCRIPT_DIR/server.py"
  exit 1
fi

if [[ ! -f "$MODEL_DIR/model_index.json" ]]; then
  echo "ERROR: Wan2.2 Diffusers model is incomplete: $MODEL_DIR"
  echo "Run without --start-only first."
  exit 1
fi

mkdir -p "$OUTPUT_DIR" "$TMP_DIR"

# ─── Update server_config.json ──────────────────────────────────────────────
python - "$CONFIG" "$MODEL_DIR" "$OUTPUT_DIR" <<'PYEOF'
import json
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
model_dir = sys.argv[2]
output_dir = sys.argv[3]

with config_path.open("r", encoding="utf-8") as file:
    cfg = json.load(file)

cfg["model_id"] = model_dir
cfg["output_dir"] = output_dir
cfg["model_type"] = "wan2.2-i2v-a14b"

with config_path.open("w", encoding="utf-8") as file:
    json.dump(cfg, file, indent=2)
    file.write("\n")

print(f"[config] model_id   -> {model_dir}")
print(f"[config] output_dir -> {output_dir}")
print("[config] model_type -> wan2.2-i2v-a14b")
PYEOF

echo ""
echo "=== Starting Wan2.2 A14B I2V inference server ==="
echo "Config       : $CONFIG"
echo "Python       : $VENV_DIR/bin/python"
echo "Storage root : $STORAGE_ROOT"
echo "Model        : $MODEL_DIR"
echo "HF cache     : $HF_HOME"
echo "Temporary    : $TMP_DIR"
echo "Outputs      : $OUTPUT_DIR"

python - "$CONFIG" <<'PYEOF'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as file:
    cfg = json.load(file)

print(f"  model_id             : {cfg['model_id']}")
print(f"  host:port            : {cfg['host']}:{cfg['port']}")
print(f"  idle_timeout_minutes : {cfg['idle_timeout_minutes']} (0 = disabled)")
print(f"  output_dir           : {cfg['output_dir']}")
print(f"  resolution           : {cfg['width']}x{cfg['height']}")
PYEOF

echo ""
echo "Edit $CONFIG to change server settings before restarting."
echo ""

cd "$SCRIPT_DIR"
SERVER_CONFIG="$CONFIG" exec "$VENV_DIR/bin/python" server.py