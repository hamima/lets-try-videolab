# RunPod Pod Setup — LTX-Video I2V Server

This guide sets up an **LTX-Video I2V** server on a RunPod pod (no ComfyUI required)
and connects it to VidLife pipeline step 9.

---

## Quick Reference

```bash
# First time — install deps, download model, start server (~10–15 min)
bash /workspace/runpod/setup.sh

# Restart server only (pod restarted, model already downloaded)
bash /workspace/runpod/setup.sh --start-only

# Re-upload config change from local machine
scp -P <port> runpod/server_config.json root@<pod-ip>:/workspace/runpod/
```

---

## Prerequisites

- RunPod account with a GPU pod using **≥ 12GB VRAM** (RTX 4090 recommended)
- Port **8080** exposed via RunPod's HTTP proxy

---

## 1. Create the Pod

1. Log in at [runpod.io](https://www.runpod.io)
2. Go to **Pods → Deploy**
3. Select a **data center** and **GPU** (see recommendations below)
4. Choose the **RunPod PyTorch** template
5. Under **Expose HTTP Ports**, add port **8080**
6. Under **Advanced → Expose TCP Ports**, add port **22** (for SCP/SSH)
7. Deploy the pod

### Data Center (NL-based)

| Data center | Location | Notes |
|---|---|---|
| **EU-NL-1** | Netherlands | Closest — lowest latency, data stays in NL |
| EU-FR-1 | France | Good fallback if EU-NL-1 has no availability |
| EU-CZ-1 | Czech Republic | Alternative fallback |

### GPU Recommendations

LTX-Video fits comfortably in **12GB VRAM**. Listed by price/performance:

| GPU | VRAM | Price/hr | Notes |
|---|---|---|---|
| RTX 3090 | 24 GB | $0.46 | Budget option |
| **RTX 4090** | **24 GB** | **$0.69** | **Recommended** — fastest consumer card |
| L40S | 48 GB | $0.99 | Overkill but very fast |
| A100 PCIe | 80 GB | $1.39 | Only for batched production |

Once running, copy the **proxy URL** for port 8080:
```
https://{pod-id}-8080.proxy.runpod.net
```

---

## 2. Upload the runpod/ Folder

### One-time: SSH key setup

```bash
# Generate a key if you don't have one
ssh-keygen -t ed25519 -C "vidlife-runpod" -f ~/.ssh/runpod_key

# Print the public key — copy the full output
cat ~/.ssh/runpod_key.pub
```

Go to [runpod.io → Settings → SSH Public Keys](https://www.runpod.io/console/user/settings) and paste it in.

> Keys are injected at pod creation time. Add the key **before** creating the pod.

### Find your SSH host and port

In the RunPod dashboard → **Connect** on your pod → **SSH over exposed TCP**:
```
ssh root@<pod-ip> -p <port> -i ~/.ssh/runpod_key
```

### Upload the folder

Run this from the **root of this repo** on your local machine:

```bash
rsync -av -e "ssh -i ~/.ssh/runpod_key -p <port>" runpod/ root@<pod-ip>:/workspace/runpod/
```

This copies the entire `runpod/` folder to `/workspace/runpod/` on the pod.

---

## 3. Run the Setup Script

SSH into the pod and run:

```bash
bash /workspace/runpod/setup.sh
```

This script will:
1. Install Python dependencies (`fastapi`, `uvicorn`, `diffusers`, etc.)
2. Download LTX-Video model weights from HuggingFace (~12GB) — **10–15 min first run**
3. Update `server_config.json` with resolved local paths
4. Start the FastAPI server on port 8080

> **Subsequent restarts are fast.** If the pod restarts and the model is already downloaded, use `--start-only` to skip steps 1 & 2 and go straight to starting the server:
> ```bash
> bash /workspace/runpod/setup.sh --start-only
> ```

---

## 4. Verify the Server

```bash
# Should return {"detail":"Unknown job_id"} — confirms server is running
curl https://{pod-id}-8080.proxy.runpod.net/status/test
```

---

## 5. Configure `.keys`

On your **local machine**, edit `.keys` and add:

```bash
export RUNPOD_URL="https://{pod-id}-8080.proxy.runpod.net"
```

Then load:
```bash
source .keys
```

---

## 6. Run Step 9

```bash
# Run just step 9
python automate.py --step 9 --workspace <id>

# Or run the full pipeline
python automate.py
```

Step 9 will:
1. Find every `animated.txt` in the workspace
2. Submit the paired static asset + animation prompt to the pod server
3. Poll for completion (up to 10 minutes per clip)
4. Stream and save each result as `animated.mp4`
5. Skip assets that already have `animated.mp4` (resumable)

---

## Server Config (`server_config.json`)

Edit `runpod/server_config.json` before uploading to the pod to control server behaviour:

```json
{
  "model_id": "Lightricks/LTX-Video",
  "host": "0.0.0.0",
  "port": 8080,
  "idle_timeout_minutes": 30,
  "output_dir": "/tmp/ltx_outputs",
  "width": 704,
  "height": 480,
  "num_inference_steps": 30,
  "guidance_scale": 3.0
}
```

| Field | Default | Description |
|---|---|---|
| `model_id` | HuggingFace repo or local path | Updated to local path by `setup.sh` after download |
| `port` | `8080` | Must match the port exposed in RunPod pod settings |
| `idle_timeout_minutes` | `30` | Minutes of inactivity before auto-shutdown. Set `0` to disable. |
| `width` / `height` | `704` / `480` | Output video resolution |
| `num_inference_steps` | `30` | More steps = better quality, slower |
| `guidance_scale` | `3.0` | Prompt adherence strength |

### Auto-Shutdown

The server shuts itself down after `idle_timeout_minutes` of no HTTP traffic **and** no running/pending jobs. This keeps RunPod costs low when the pipeline isn't active.

To restart after auto-shutdown:
```bash
bash /workspace/runpod/setup.sh --start-only
```

`--start-only` skips dependency installation and model download — the server starts in seconds.

### View Config at Runtime

```bash
curl https://{pod-id}-8080.proxy.runpod.net/config
```

---

## API Reference

### `POST /generate`

Submit a generation job.

**Form fields:**
| Field | Type | Default | Description |
|---|---|---|---|
| `image` | file | — | Static image to animate (PNG/JPG) |
| `prompt` | string | — | Animation description |
| `duration_seconds` | int | `5` | Output duration in seconds |

**Response:**
```json
{"job_id": "550e8400-e29b-41d4-a716-446655440000"}
```

### `GET /status/{job_id}`

Poll job status.

```json
{"status": "pending|processing|done|failed", "error": null}
```

### `GET /download/{job_id}`

Download the finished video. Returns 404 if not `done`. File is automatically deleted from the pod after streaming.

---

## Pod Persistence & Network Volume

RunPod pods lose `/workspace` on stop. Without a network volume the ~12GB model re-downloads every restart (~15 min).

`setup.sh` detects storage automatically:

| `/runpod-volume` mounted? | Model path | Output path |
|---|---|---|
| Yes (network volume) | `/runpod-volume/models/LTX-Video` | `/runpod-volume/ltx_outputs` |
| No (ephemeral) | `/workspace/models/LTX-Video` | `/workspace/ltx_outputs` |

### Attaching a Network Volume

1. RunPod dashboard → **Storage → Network Volumes → Create**
2. Size: **≥ 20GB** (12GB model + output headroom)
3. When deploying your pod, attach the volume — it mounts at `/runpod-volume`
4. Run `bash /workspace/runpod/setup.sh` — detects the volume automatically
5. On subsequent restarts: `bash /workspace/runpod/setup.sh --start-only`

---

## Troubleshooting

### "RUNPOD_URL is not set"
Run `source .keys` and verify: `echo $RUNPOD_URL`

### Connection refused / timeout
- Confirm the pod is running in the RunPod dashboard
- Confirm port **8080** is exposed in the pod's HTTP port settings
- Model loading takes ~1–2 min on warm start — wait before testing

### Job fails immediately
Check the server logs (the terminal where `setup.sh` is running) for CUDA OOM or other errors.

### subsystem request failed (SCP error)
Use `rsync` instead — see the upload step above.

---

## Key Files

| File | Purpose |
|---|---|
| `runpod/server.py` | FastAPI server (4 endpoints: `/generate`, `/status`, `/download`, `/config`) |
| `runpod/server_config.json` | Server settings (model path, port, resolution, idle timeout) |
| `runpod/setup.sh` | Full setup + server launch; use `--start-only` to skip install/download on restarts |
| `runpod/requirements.txt` | Python dependencies |
| `.keys` | Contains `RUNPOD_URL` (gitignored — never commit) |
| `automate.py` | Step 9 implementation (`run_runpod_animation`) |
