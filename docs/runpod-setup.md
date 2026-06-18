# RunPod Pod Setup — VidLife Step 9

This guide covers everything needed to get a RunPod pod running ComfyUI with the
Wan 2.1 I2V model, and connect it to the VidLife pipeline.

---

## Prerequisites

- A RunPod account with a pod using a **GPU with ≥ 24GB VRAM** (e.g. RTX Pro 4500)
- ComfyUI pre-installed on the pod (select a ComfyUI template when creating the pod,
  or install it manually at `/workspace/ComfyUI`)
- The pod must have **port 8188** exposed via RunPod's proxy

---

## 1. Create the Pod

1. Log in at [runpod.io](https://www.runpod.io)
2. Go to **Pods → Deploy**
3. Select a GPU with ≥ 24GB VRAM (RTX Pro 4500 or equivalent)
4. Choose the **RunPod ComfyUI** template (or any PyTorch image if you'll install ComfyUI manually)
5. Under **Expose HTTP Ports**, add port **8188**
6. Deploy the pod

Once running, copy the **proxy URL** for port 8188. It looks like:
```
https://{pod-id}-8188.proxy.runpod.net
```

---

## 2. Run the Setup Script

Open the pod's **terminal** (via the RunPod web UI or SSH) and run:

```bash
# Clone or copy pod_setup.sh to the pod, then:
bash pod_setup.sh
```

This script will:
1. Install `ComfyUI-WanVideoWrapper` (kijai) custom nodes
2. Install `ComfyUI-VideoHelperSuite` (VHS nodes for video output)
3. Download Wan 2.1 I2V 14B FP8 model weights (~14GB) from HuggingFace
4. Download VAE and UMT5 text encoder weights
5. Restart ComfyUI

> **First run takes 10–20 minutes** due to model downloads. Subsequent runs skip already-downloaded files.

---

## 3. Verify the Workflow

1. Open the ComfyUI web UI at your pod proxy URL
2. Click **Load** and select `wan_i2v_workflow.json` from this repo
3. Verify that all **WanVideo\*** nodes appear without red "Unknown Node" errors
4. Do a quick manual test:
   - Upload a sample image via the `LoadImage` node
   - Replace `__PROMPT__` with any short description
   - Replace `__FRAME_COUNT__` with `96` (4 seconds at 24fps)
   - Click **Queue Prompt**
   - Confirm an `animated.mp4` is generated in ComfyUI's output folder

> **If nodes show as Unknown**: the custom nodes didn't load. Check ComfyUI logs:
> ```bash
> tail -f /tmp/comfyui.log
> ```
> Then restart ComfyUI and reload the page.

---

## 4. Configure `.keys`

Back on your local machine, edit `.keys` and set:

```bash
export COMFYUI_URL="https://{pod-id}-8188.proxy.runpod.net"
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
2. Upload the paired static asset to ComfyUI
3. Submit the workflow with the animation prompt, burn key prefix, and frame count
4. Poll for completion (up to 10 minutes per clip)
5. Download and save each result as `animated.mp4`

---

## Troubleshooting

### "COMFYUI_URL is not set"
Run `source .keys` and check `COMFYUI_URL` is set (`echo $COMFYUI_URL`).

### Connection refused / timeout
- Confirm the pod is running in the RunPod dashboard
- Confirm port 8188 is exposed in the pod's settings
- Try opening `$COMFYUI_URL` in a browser — you should see the ComfyUI UI

### "Unknown Node" errors in ComfyUI
Custom nodes didn't load. Re-run `pod_setup.sh` and check `/tmp/comfyui.log` for pip errors.

### Job times out after 10 minutes
Wan 2.1 14B on 24GB VRAM with `force_offload: true` can take 6–9 minutes for longer clips.
If clips are consistently timing out, reduce duration in `asset_manifest.md` or switch to
the 480P model variant (already configured in the workflow).

### Output filename not found after completion
The `VHS_VideoCombine` node saves output under the `gifs` key in ComfyUI's history response.
If your ComfyUI version differs, check the raw history at:
```
GET {COMFYUI_URL}/history/{prompt_id}
```
And update the output key lookup in `run_runpod_animation()` in `automate.py`.

---

## Pod Restart / Persistence

RunPod pods lose their filesystem on stop unless you use **persistent storage** (network volume).
To avoid re-downloading models after every restart:

1. Attach a **RunPod Network Volume** (≥ 50GB) to your pod
2. Move the ComfyUI models directory to the volume:
   ```bash
   mv /workspace/ComfyUI/models /runpod-volume/comfyui-models
   ln -s /runpod-volume/comfyui-models /workspace/ComfyUI/models
   ```
3. On the next pod start, re-run `pod_setup.sh` — it will skip already-downloaded weights.

---

## Key Files

| File | Purpose |
|---|---|
| `pod_setup.sh` | One-time pod setup script (custom nodes + model weights) |
| `wan_i2v_workflow.json` | ComfyUI workflow template with `__PLACEHOLDER__` tokens |
| `.keys` | Contains `COMFYUI_URL` (not committed to git) |
| `automate.py` | Step 9 implementation (`run_runpod_animation`) |
