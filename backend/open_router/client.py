"""
backend/open_router/client.py — Shared HTTP/auth helper for OpenRouter calls.

Pure HTTP layer: takes api_key as an explicit parameter and knows nothing
about settings.json. Callers in tasks.py are responsible for reading
OPENROUTER_API_KEY() and passing it in.
"""

import requests

from . import models


def _require_key(api_key: str) -> None:
    if not api_key:
        raise RuntimeError(
            "OpenRouter is enabled (USE_OPENROUTER=true) but OPENROUTER_API_KEY "
            "is missing. Add it in Settings."
        )


def post(path: str, api_key: str, **kwargs):
    _require_key(api_key)
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {api_key}"
    resp = requests.post(f"{models.BASE_URL}{path}", headers=headers, **kwargs)
    resp.raise_for_status()
    return resp


def get(path: str, api_key: str, absolute: bool = False, **kwargs):
    _require_key(api_key)
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {api_key}"
    url = path if absolute else f"{models.BASE_URL}{path}"
    resp = requests.get(url, headers=headers, **kwargs)
    resp.raise_for_status()
    return resp
