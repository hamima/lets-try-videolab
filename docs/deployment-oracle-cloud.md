# Deploying the Backend on an Oracle Cloud Free VM

Why this instead of a PaaS like Render: as of late 2026, no push-to-deploy PaaS (Render, Fly.io, Railway, Koyeb) offers a genuinely free persistent disk anymore — Oracle Cloud's "Always Free" tier is the main option left with real free persistent storage (200GB block storage, free forever, attached to a free VM). The tradeoff is you're managing a VM yourself instead of `git push`-to-deploy; this doc covers that with Docker so it's still a one-command deploy once the VM exists.

This covers **the backend only**. The frontend (per `backend/render.yaml`'s `ALLOWED_ORIGINS` default) is assumed to be deployed separately, e.g. on Cloudflare Pages.

## 1. Create the free VM

In the [Oracle Cloud console](https://cloud.oracle.com/): **Compute → Instances → Create Instance**.

- Image: **Ubuntu** (latest LTS) — the rest of this doc assumes `apt`.
- Shape: an **Ampere (ARM) A1** shape, sized within the Always Free allowance (as of the June 2026 cuts: up to 2 OCPU / 12GB RAM — this app doesn't need more).
- Boot volume: default is fine; Always Free gives 200GB of block storage shared across all your volumes.
- Add your SSH public key during creation (or generate one in the console) — you'll need it to log in.
- Note the VM's **public IP** once it's running.

## 2. Open the backend's port

Oracle's default security list blocks inbound traffic — this is the single most commonly-missed step. In the console: **Networking → Virtual Cloud Networks → (your VCN) → Security Lists → (default list) → Add Ingress Rule**:

- Source CIDR: `0.0.0.0/0`
- Destination port: `8081` (or whatever you map in `docker-compose.yml`)

Ubuntu also ships with its own firewall (`ufw`) — if it's active, allow the port there too: `sudo ufw allow 8081/tcp`.

## 3. Install Docker on the VM

SSH in (`ssh ubuntu@<vm-ip>`), then:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
# log out and back in for the group change to take effect
```

This installs Docker Engine with the `docker compose` plugin included.

## 4. Clone the repo and configure

```bash
git clone git@github.com:hamima/lets-try-videolab.git VidLife
cd VidLife
cp .env.example .env
```

Edit `.env` and fill in at minimum:

- `GOOGLE_CLIENT_ID` — required, sign-in 500s without it (see `docs/authentication.md`). Must be authorized in Google Cloud Console for whatever origin the frontend ends up calling this backend from.
- `ALLOWED_ORIGINS` — the frontend's deployed origin(s), comma-separated (e.g. `https://vidlife.pages.dev`).

The pipeline API keys (`GEMINI_API_KEY`, etc.) can go in `.env` too, or be left unset and configured later through the Settings UI — either way, they end up on the persistent `/data` volume, not the throwaway image layer, so they survive container recreation.

## 5. Build and run

```bash
docker compose up -d --build
```

Verify:

```bash
curl http://<vm-ip>:8081/health
# {"status":"ok"}
```

`workspace/` and `settings.json` live on the named Docker volume `vidlife-data` (mounted at `/data`, via the `DATA_DIR` env var — see `backend/tasks.py`/`settings.py`) — this is what actually survives `docker compose down && docker compose up -d --build` after a `git pull`, unlike a plain `docker run` with no volume.

## 6. TLS — required before pointing a deployed frontend at this

If the frontend is served over `https://` (true for Cloudflare Pages and most static hosts), browsers will block requests to a plain `http://` backend as mixed content — this isn't optional once both are deployed. Two reasonable options, pick one based on what you already have:

- **Cloudflare Tunnel** (`cloudflared`) — if the frontend's already on Cloudflare Pages, you likely already have a Cloudflare account/domain. A tunnel connects outbound from the VM to Cloudflare's edge, giving you a `https://api.yourdomain.com` endpoint with zero inbound firewall rules needed (you can even remove the port-8081 ingress rule from step 2). See [Cloudflare's tunnel docs](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) for setup — it's a single `cloudflared` binary + a tunnel token, no code changes here.
- **Caddy** as a reverse proxy in front of the container — if you have your own domain's DNS pointed at the VM's IP instead. Caddy gets a Let's Encrypt certificate automatically with a ~5-line Caddyfile (`reverse_proxy localhost:8081`). Needs port 80/443 open instead of 8081 in step 2.

Either way, once you have an HTTPS URL for the backend, set it as `VITE_API_URL` when building the frontend (see the root `README.md`'s "VITE_API_URL" section, and `frontend/.env.production`).

## Updating the deployment

```bash
cd VidLife
git pull
docker compose up -d --build
```

The named volume (and everything on it) is untouched by this — only the image/container get rebuilt and recreated.

## Troubleshooting

- **Can't reach `http://<vm-ip>:8081` at all** — almost always the Oracle security list (step 2), not Docker or the app. Double-check the ingress rule, and `ufw status` on the VM if it's enabled.
- **Sign-in fails with "GOOGLE_CLIENT_ID is not configured"** — `.env`'s `GOOGLE_CLIENT_ID` is empty or the container wasn't recreated after editing it (`docker compose up -d` picks up `.env` changes on recreate, not on a running container).
- **CORS errors in the browser console** — `ALLOWED_ORIGINS` in `.env` doesn't include the frontend's exact origin (scheme + host, no trailing slash), or the container needs recreating after editing it.
