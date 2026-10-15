"""
Unit tests for live traffic inspection, ring buffer, SSE broadcasting, and Web Mode endpoints.
"""

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import httpx

from agy_proxy.auth import AccountPool
from agy_proxy.server import create_app
from agy_proxy.traffic import TrafficInspector, TrafficRecord, traffic_inspector


class TestTrafficModule(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.inspector = TrafficInspector(maxlen=5)

    def test_record_and_ring_buffer_maxlen(self):
        for i in range(10):
            self.inspector.record(
                method="POST",
                path=f"/v1/test-{i}",
                client_model="deepagent",
                backend_model="gemini-3.8-flash-high",
                status_code=200,
                duration_ms=10.5,
                prompt_tokens=100,
                completion_tokens=50,
            )

        history = self.inspector.get_history()
        self.assertEqual(len(history), 5)
        # Ordered newest first
        self.assertEqual(history[0]["path"], "/v1/test-9")
        self.assertEqual(history[-1]["path"], "/v1/test-5")
        self.assertEqual(history[0]["total_tokens"], 150)

    def test_clear_traffic(self):
        self.inspector.record("GET", "/health", "client", "backend")
        self.assertEqual(len(self.inspector.get_history()), 1)
        self.inspector.clear()
        self.assertEqual(len(self.inspector.get_history()), 0)

    async def test_sse_subscriber(self):
        sub_gen = self.inspector.subscribe()
        initial = await sub_gen.__anext__()
        self.assertIn(": connected", initial)

        # Record event
        self.inspector.record(
            method="POST",
            path="/v1/messages",
            client_model="claude-3-7-sonnet",
            backend_model="gemini-3.8-flash-high",
            status_code=200,
            duration_ms=250.0,
            stream=True,
        )

        event_str = await sub_gen.__anext__()
        self.assertTrue(event_str.startswith("data: "))
        data = json.loads(event_str[6:].strip())
        self.assertEqual(data["path"], "/v1/messages")
        self.assertEqual(data["client_model"], "claude-3-7-sonnet")
        self.assertTrue(data["stream"])

        await sub_gen.aclose()


class TestTrafficAndWebEndpoints(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        self.pool = AccountPool(
            accounts_file=Path(self._temp_dir.name) / "accounts.json",
            api_keys_file=Path(self._temp_dir.name) / "api_keys.json",
            web_sessions_file=Path(self._temp_dir.name) / "web_sessions.json",
        )
        self.app = create_app(account_pool=self.pool)
        self.transport = httpx.ASGITransport(app=self.app)
        self.client = httpx.AsyncClient(transport=self.transport, base_url="http://test")
        traffic_inspector.clear()

    async def asyncTearDown(self):
        await self.client.aclose()
        self._temp_dir.cleanup()
        traffic_inspector.clear()

    async def test_traffic_api_crud(self):
        # 1. Record item
        traffic_inspector.record(
            method="POST",
            path="/v1/chat/completions",
            client_model="deepagent",
            backend_model="gemini-3.8-flash-high",
            status_code=200,
            duration_ms=312.4,
            prompt_tokens=40,
            completion_tokens=20,
        )

        # 2. Query REST endpoint
        resp = await self.client.get("/api/traffic")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(len(data["records"]), 1)
        self.assertEqual(data["records"][0]["client_model"], "deepagent")

        # 3. Clear REST endpoint
        resp_clear = await self.client.post("/api/traffic/clear")
        self.assertEqual(resp_clear.status_code, 200)
        self.assertEqual(resp_clear.json()["status"], "ok")

        resp_after = await self.client.get("/api/traffic")
        self.assertEqual(resp_after.json()["total"], 0)

    async def test_web_restart_endpoint(self):
        with patch("agy_proxy.web_launcher.launch_antigravity_web", return_value=0) as mock_launch:
            resp = await self.client.post("/api/web/restart", json={"port": 44741, "kill_electron": False})
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["status"], "ok")
            mock_launch.assert_called_once()
            _, kwargs = mock_launch.call_args
            self.assertTrue(kwargs.get("restart"))


if __name__ == "__main__":
    unittest.main()
