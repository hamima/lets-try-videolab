"""backend/open_router/image.py — Image generation via OpenRouter's Unified Image API."""

import base64

from . import client, models


def generate_image(prompt: str, api_key: str, model: str = models.IMAGE_MODEL) -> bytes:
    resp = client.post(
        "/images",
        api_key,
        json={"model": model, "prompt": prompt},
    )
    data = resp.json()["data"]
    if not data:
        raise RuntimeError("OpenRouter image generation returned no images")
    return base64.b64decode(data[0]["b64_json"])
