# RunPod Pod Setup — VidLife Step 9

This guide covers everything needed to get a RunPod pod running the **Wan2.2 I2V 14B**
direct FastAPI server and connect it to the VidLife pipeline.

> **No ComfyUI required.** The server exposes a clean REST API that step 9 calls directly.

---

## Prerequisites

- A RunPod account with a pod using a **GPU with ≥ 24GB VRAM** (RTX 4090, A100, etc.)
- The pod must have **port 8000** exposed via RunPod's proxy

---

## 1. Create the Pod

1. Log in at [runpod.io](https://www.runpod.io)
2. Go to **Pods → Deploy**
3. Select a GPU with ≥ 24GB VRAM
4. Choose a base **PyTorch** template (e.g. "RunPod PyTorch 2.x")
5. Under **Expose HTTP Ports**, add port **8000**
6. Deploy the pod

Once running, copy the **proxy URL** for port 8000:
```
https://{pod-id}-8000.proxy.runpod.net
```

---

## 2. Run the Setup Script

Open the pod's **terminal** (via the RunPod web UI or SSH) and run:

```bash
# Upload or clone the runpod/ folder to the pod, then:
bash runpod/setup.sh
```

This script will:
1. Install Python dependencies (`fastapi`, `uvicorn`, `diffusers`, etc.)
2. Download Wan2.2 I2V 14B 480P model weights (~14GB) from HuggingFace
3. Start the FastAPI server on port 8000

> **First run takes 10–20 minutes** due to model downloads. Subsequent runs skip already-downloaded files.

---

## 3. Verify the Server

```bash
# Should return {"detail":"Unknown job_id"} — confirms the server is up
curl https://{pod-id}-8000.proxy.runpod.net/status/test
```

---

## 4. Configure `.keys`

On your **local machine**, edit `.keys` and set:

```bash
export RUNPOD_URL="https://{pod-id}-8000.proxy.runpod.net"
```

Replace `{pod-id}` with your actual pod ID from the RunPod dashboard.

Load the keys:
```bash
source .keys
```

---

## 5. Run Step 9

With the pod running and `.keys` sourced:

```bash
# Run just step 9 on the latest workspace
python automate.py --step 9

# Or run the full pipeline (step 9 runs automatically after step 8)
python automate.py
```

Step 9 will:
1. Find every `animated.txt` in the workspace
2. Submit the paired static asset + animation prompt to `POST /generate`
3. Poll `GET /status/{job_id}` every 5 seconds (up to 10 minutes per clip)
4. Stream the result from `GET /download/{job_id}` and save as `animated.mp4`
5. Skip assets where `animated.mp4` already exists (resumable)

---

## Manual API Test

```bash
BASE="https://{pod-id}-8000.proxy.runpod.net"

# Submit
JOB=$(curl -s -X POST "$BASE/generate" \
  -F "image=@test.png" \
  -F "prompt=camera slowly pans right" \
  -F "duration_seconds=3" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# Poll
curl -s "$BASE/status/$JOB"

# Download (when status=done)
curl -s "$BASE/download/$JOB" -o test.mp4

# Confirm auto-deleted
curl -s "$BASE/download/$JOB"  # → 404
```

---

## Troubleshooting

### "RUNPOD_URL is not set"
Run `source .keys` and check `echo $RUNPOD_URL`.

### Connection refused / timeout
- Confirm the pod is running in the RunPod dashboard
- Confirm port 8000 is exposed in the pod settings
- The server starts only after the model loads (~1–2 min for warm start after initial download)

### Job status = "failed"
Check the server terminal logs for CUDA OOM or model errors.
Ensure the pod GPU has ≥ 24GB VRAM.

### Job times out after 10 minutes
Wan2.2 14B on 24GB VRAM typically takes 3–8 minutes per clip.
If consistently timing out, reduce duration in `asset_manifest.md`.

---

## Pod Persistence

RunPod pods lose their filesystem on stop unless you use **persistent storage**.
To avoid re-downloading ~14GB on every restart:

1. Attach a **RunPod Network Volume** (≥ 30GB) to your pod
2. The model downloads to `/workspace/models/` — map the network volume there
3. On the next pod start, re-run `setup.sh` — it will skip already-downloaded weights

---

## Key Files

| File | Purpose |
|---|---|
| `runpod/server.py` | FastAPI server (3 endpoints: `/generate`, `/status`, `/download`) |
| `runpod/setup.sh` | One-time pod setup script (deps + model download + server start) |
| `runpod/requirements.txt` | Python dependencies for the pod |
| `.keys` | Contains `RUNPOD_URL` (not committed to git) |
| `automate.py` | Step 9 implementation (`run_runpod_animation`) |
