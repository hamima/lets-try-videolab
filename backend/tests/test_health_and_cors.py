"""
backend/tests/test_health_and_cors.py — regression tests for the /health
endpoint (deploy-platform liveness checks, e.g. Render's healthCheckPath)
and ALLOWED_ORIGINS parsing (backend/render.yaml's CORS config).

The CORS middleware itself is wired up once at module import time based on
ALLOWED_ORIGINS at that moment, so it isn't re-tested here via the shared
`tasks.app` singleton (reloading the module would affect every other test
importing `tasks`) — _parse_allowed_origins is tested directly instead, and
the actual middleware behavior (allowed origin gets CORS headers, a
non-listed origin gets rejected, unset ALLOWED_ORIGINS adds no middleware
at all) was verified manually against a running instance in each of those
three configurations.
"""

from fastapi.testclient import TestClient

import tasks


def test_health_endpoint():
    client = TestClient(tasks.app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_parse_allowed_origins_splits_and_strips():
    assert tasks._parse_allowed_origins("https://a.com,https://b.com") == ["https://a.com", "https://b.com"]
    assert tasks._parse_allowed_origins("https://a.com, https://b.com ") == ["https://a.com", "https://b.com"]


def test_parse_allowed_origins_drops_blanks_from_stray_commas():
    assert tasks._parse_allowed_origins("https://a.com,,https://b.com,") == ["https://a.com", "https://b.com"]


def test_parse_allowed_origins_empty_string_is_empty_list():
    assert tasks._parse_allowed_origins("") == []
    assert tasks._parse_allowed_origins("   ") == []
