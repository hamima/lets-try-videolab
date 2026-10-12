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


_LOG_BODY_LIMIT = 500
_DEFAULT_TIMEOUT = 120


def _log_request(method: str, url: str, kwargs: dict) -> None:
    params = {k: v for k, v in kwargs.items() if k != "headers"}
    print(f"[openrouter] {method} {url} params={params}", flush=True)


def _log_response(resp: requests.Response) -> None:
    body = resp.text
    if len(body) > _LOG_BODY_LIMIT:
        body = f"{body[:_LOG_BODY_LIMIT]}... (truncated, {len(resp.text)} bytes total)"
    print(f"[openrouter] response status={resp.status_code} body={body}", flush=True)


def post(path: str, api_key: str, **kwargs):
    _require_key(api_key)
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {api_key}"
    kwargs.setdefault("timeout", _DEFAULT_TIMEOUT)
    url = f"{models.BASE_URL}{path}"
    _log_request("POST", url, kwargs)
    resp = requests.post(url, headers=headers, **kwargs)
    _log_response(resp)
    resp.raise_for_status()
    return resp


def get(path: str, api_key: str, absolute: bool = False, **kwargs):
    _require_key(api_key)
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {api_key}"
    kwargs.setdefault("timeout", _DEFAULT_TIMEOUT)
    url = path if absolute else f"{models.BASE_URL}{path}"
    _log_request("GET", url, kwargs)
    resp = requests.get(url, headers=headers, **kwargs)
    _log_response(resp)
    resp.raise_for_status()
    return resp
