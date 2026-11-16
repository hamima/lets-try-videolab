# backend/Dockerfile — build from the REPO ROOT, not backend/:
#   docker build -f backend/Dockerfile -t vidlife-backend .
# (docker-compose.yml at the repo root already does this.)
#
# BASE_DIR in tasks.py/settings.py/auth.py resolves two levels up from
# backend/*.py (i.e. the repo root) — prompts/, scripts/, fonts/, and
# admins.conf all need to exist alongside backend/ inside the image, which
# is why the build context is the whole repo, not just backend/.

FROM python:3.12-slim

# ffmpeg/ffprobe are invoked directly by scripts/*.py via subprocess (not a
# pip package) — the pipeline's audio/video steps (narration timing,
# assembly, subtitle burn-in) need them on PATH.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY . .

WORKDIR /app/backend
EXPOSE 8081

# DATA_DIR defaults to BASE_DIR (/app) if unset — mount a volume at /data and
# set DATA_DIR=/data (see docker-compose.yml) so workspace/ and settings.json
# survive container recreation instead of living in the throwaway image layer.
CMD ["uvicorn", "tasks:app", "--host", "0.0.0.0", "--port", "8081"]
