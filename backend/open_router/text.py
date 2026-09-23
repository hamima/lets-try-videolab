"""backend/open_router/text.py — Text generation via OpenRouter chat completions."""

from . import client, models


def generate_text(prompt: str, api_key: str, model: str = models.TEXT_MODEL) -> str:
    resp = client.post(
        "/chat/completions",
        api_key,
        json={"model": model, "messages": [{"role": "user", "content": prompt}]},
    )
    return resp.json()["choices"][0]["message"]["content"]
