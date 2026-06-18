#!/usr/bin/env bash
# =============================================================================
# VidLife — RunPod Pod Setup: Wan 2.1 Image-to-Video on ComfyUI
# =============================================================================
# Run this ONCE in the RunPod terminal after the pod starts.
# ComfyUI must already be installed at /workspace/ComfyUI.
#
# Usage:
#   bash pod_setup.sh
#
# After this completes, restart ComfyUI and verify the WanVideo* nodes appear.
# =============================================================================

set -euo pipefail

COMFYUI_DIR="/workspace/ComfyUI"
CUSTOM_NODES_DIR="$COMFYUI_DIR/custom_nodes"
MODELS_WAN_DIR="$COMFYUI_DIR/models/wan"
MODELS_VAE_DIR="$COMFYUI_DIR/models/vae"
MODELS_CLIP_DIR="$COMFYUI_DIR/models/clip"

echo "=== VidLife Pod Setup: Wan 2.1 I2V ==="
echo ""

# ─────────────────────────────────────────────────────────────
# 1. ComfyUI-WanVideoWrapper (kijai)
# ─────────────────────────────────────────────────────────────

echo ">>> [1/4] Installing ComfyUI-WanVideoWrapper..."

cd "$CUSTOM_NODES_DIR"

if [ -d "ComfyUI-WanVideoWrapper" ]; then
  echo "    Already installed — pulling latest..."
  cd ComfyUI-WanVideoWrapper && git pull && cd ..
else
  git clone https://github.com/kijai/ComfyUI-WanVideoWrapper.git
  echo "    Cloned ComfyUI-WanVideoWrapper"
fi

cd ComfyUI-WanVideoWrapper
pip install -r requirements.txt --quiet
cd "$CUSTOM_NODES_DIR"

echo "    ✓ ComfyUI-WanVideoWrapper installed"
echo ""

# ─────────────────────────────────────────────────────────────
# 2. ComfyUI-VideoHelperSuite (VHS_VideoCombine node)
# ─────────────────────────────────────────────────────────────

echo ">>> [2/4] Installing ComfyUI-VideoHelperSuite (VHS nodes)..."

if [ -d "ComfyUI-VideoHelperSuite" ]; then
  echo "    Already installed — pulling latest..."
  cd ComfyUI-VideoHelperSuite && git pull && cd ..
else
  git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
  echo "    Cloned ComfyUI-VideoHelperSuite"
fi

cd ComfyUI-VideoHelperSuite
pip install -r requirements.txt --quiet 2>/dev/null || true
cd "$CUSTOM_NODES_DIR"

echo "    ✓ ComfyUI-VideoHelperSuite installed"
echo ""

# ─────────────────────────────────────────────────────────────
# 3. Model weights
# ─────────────────────────────────────────────────────────────

echo ">>> [3/4] Downloading Wan 2.1 I2V 14B model weights..."
echo "    (This will take several minutes on first run)"
echo ""

mkdir -p "$MODELS_WAN_DIR" "$MODELS_VAE_DIR" "$MODELS_CLIP_DIR"

# Check for huggingface-cli
if ! command -v huggingface-cli &> /dev/null; then
  echo "    Installing huggingface_hub..."
  pip install huggingface_hub --quiet
fi

# Wan 2.1 I2V 14B — FP8 (fits in 24GB VRAM with force_offload)
MODEL_FILE="Wan2_1-I2V-14B-480P_fp8_e4m3fn.safetensors"
if [ -f "$MODELS_WAN_DIR/$MODEL_FILE" ]; then
  echo "    $MODEL_FILE already exists — skipping"
else
  echo "    Downloading $MODEL_FILE (~14GB)..."
  huggingface-cli download Kijai/WanVideo_comfy \
    --include "$MODEL_FILE" \
    --local-dir "$MODELS_WAN_DIR"
fi

# VAE
VAE_FILE="Wan_2.1_VAE.safetensors"
if [ -f "$MODELS_VAE_DIR/$VAE_FILE" ]; then
  echo "    $VAE_FILE already exists — skipping"
else
  echo "    Downloading $VAE_FILE..."
  huggingface-cli download Kijai/WanVideo_comfy \
    --include "$VAE_FILE" \
    --local-dir "$MODELS_VAE_DIR"
fi

# Text encoder (UMT5-XXL)
CLIP_FILE="umt5-xxl-enc-bf16.safetensors"
if [ -f "$MODELS_CLIP_DIR/$CLIP_FILE" ]; then
  echo "    $CLIP_FILE already exists — skipping"
else
  echo "    Downloading $CLIP_FILE..."
  huggingface-cli download Kijai/WanVideo_comfy \
    --include "$CLIP_FILE" \
    --local-dir "$MODELS_CLIP_DIR"
fi

echo ""
echo "    ✓ Model weights ready"
echo ""

# ─────────────────────────────────────────────────────────────
# 4. Restart ComfyUI
# ─────────────────────────────────────────────────────────────

echo ">>> [4/4] Restarting ComfyUI..."

pkill -f "python main.py" 2>/dev/null || true
sleep 2

cd "$COMFYUI_DIR"
nohup python main.py --listen 0.0.0.0 --port 8188 > /tmp/comfyui.log 2>&1 &
COMFYUI_PID=$!

echo "    ComfyUI starting (PID $COMFYUI_PID)..."
echo "    Logs: tail -f /tmp/comfyui.log"
echo ""

# Wait for ComfyUI to be ready
echo "    Waiting for ComfyUI to be ready..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8188/system_stats > /dev/null 2>&1; then
    echo "    ✓ ComfyUI is up and running"
    break
  fi
  sleep 2
done

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Open the ComfyUI web UI at your pod's proxy URL (port 8188)"
echo "  2. Load wan_i2v_workflow.json and verify the WanVideo* nodes appear"
echo "  3. Do a test run with a sample image to confirm everything works"
echo "  4. Set COMFYUI_URL in .keys to your pod's proxy URL"
echo "  5. Run: python automate.py --step 9"
echo ""
