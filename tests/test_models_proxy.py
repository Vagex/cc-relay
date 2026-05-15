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

    def test_codex_app_requests_use_synced_active_profile(self):
        captured = {}

        async def fake_stream_generator(upstream_url, headers, payload, is_codex_app):
            captured["upstream_url"] = upstream_url
            captured["headers"] = headers
            captured["payload"] = payload
            captured["is_codex_app"] = is_codex_app
            yield b"data: [DONE]\n\n"

        self.client.post(
            "/relay/v1/internal/sync",
            json={
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "deepseek-secret",
                "model": "deepseek-chat",
                "organization": "",
                "project": "",
                "verify_ssl": True,
            },
        )

        with patch.object(codex_web_relay, "stream_generator", fake_stream_generator):
            response = self.client.post(
                "/relay/v1/responses",
                json={
                    "model": "stale-gemma-model",
                    "input": "hello",
                    "instructions": "be concise",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["upstream_url"], "https://api.deepseek.com/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer deepseek-secret")
        self.assertEqual(captured["payload"]["model"], "deepseek-chat")
        self.assertNotIn("input", captured["payload"])
        self.assertNotIn("instructions", captured["payload"])
        self.assertTrue(captured["is_codex_app"])

    def test_web_console_requests_keep_explicit_upstream_headers(self):
        captured = {}

        async def fake_stream_generator(upstream_url, headers, payload, is_codex_app):
            captured["upstream_url"] = upstream_url
            captured["headers"] = headers
            captured["payload"] = payload
            captured["is_codex_app"] = is_codex_app
            yield b"data: [DONE]\n\n"

        with patch.object(codex_web_relay, "stream_generator", fake_stream_generator):
            response = self.client.post(
                "/relay/v1/chat/completions",
                headers={
                    "X-Upstream-Base": "https://api.openai.com/v1",
                    "Authorization": "Bearer web-key",
                    "OpenAI-Organization": "org_test",
                    "OpenAI-Project": "proj_test",
                },
                json={
                    "model": "gpt-4.1",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["upstream_url"], "https://api.openai.com/v1/chat/completions")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer web-key")
        self.assertEqual(captured["headers"]["OpenAI-Organization"], "org_test")
        self.assertEqual(captured["headers"]["OpenAI-Project"], "proj_test")
        self.assertEqual(captured["payload"]["model"], "gpt-4.1")
        self.assertFalse(captured["is_codex_app"])

    def test_sync_state_can_be_read_back_without_secret(self):
        response = self.client.post(
            "/relay/v1/internal/sync",
            json={
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "test-secret",
                "model": "deepseek-chat",
                "organization": "",
                "project": "",
                "verify_ssl": True,
            },
        )
        self.assertEqual(response.status_code, 200)
        state = self.client.get("/relay/v1/internal/state")
        self.assertEqual(state.status_code, 200)
        payload = state.json()
        self.assertEqual(payload["base_url"], "https://api.deepseek.com/v1")
        self.assertEqual(payload["model"], "deepseek-chat")
        self.assertTrue(payload["api_key_set"])
        self.assertNotIn("api_key", payload)

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
