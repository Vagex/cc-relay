import unittest
import sys
from unittest.mock import patch
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import codex_web_relay


class FakeAsyncClient:
    def __init__(self, response=None, exc=None, **kwargs):
        self.response = response
        self.exc = exc
        self.kwargs = kwargs
        self.last_headers = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url, headers=None):
        self.last_headers = headers or {}
        if self.exc:
            raise self.exc
        return self.response


class ModelsProxyTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(codex_web_relay.app)

    def test_missing_upstream_base_returns_400(self):
        response = self.client.get("/relay/v1/models")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["data"], [])

    def test_preserves_upstream_error_status(self):
        upstream = httpx.Response(401, json={"error": {"message": "bad key"}})
        with patch.object(codex_web_relay.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(upstream, **kwargs)):
            response = self.client.get(
                "/relay/v1/models",
                headers={
                    "X-Upstream-Base": "https://api.example.test/v1",
                    "Authorization": "Bearer test-key",
                },
            )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"]["message"], "bad key")

    def test_network_errors_return_502(self):
        exc = httpx.ConnectError("connect failed")
        with patch.object(codex_web_relay.httpx, "AsyncClient", lambda **kwargs: FakeAsyncClient(exc=exc, **kwargs)):
            response = self.client.get(
                "/relay/v1/models",
                headers={"X-Upstream-Base": "https://api.example.test/v1"},
            )
        self.assertEqual(response.status_code, 502)
        self.assertIn("connect failed", response.json()["error"])


if __name__ == "__main__":
    unittest.main()
