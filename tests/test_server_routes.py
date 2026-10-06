"""
Unit tests for FastAPI endpoints, routing, and security middleware.
"""

import asyncio
import json
import unittest
from unittest.mock import Mock, AsyncMock, patch
import httpx
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from pathlib import Path
import tempfile
from agy_proxy.auth import AccountPool, AccountSession
from agy_proxy.compactor import compactor_settings
from agy_proxy.server import create_app


class TestServerRoutes(unittest.IsolatedAsyncioTestCase):
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

        # Isolate compactor_settings from touching real user config file
        self._orig_config_file = compactor_settings.config_file
        self._orig_enabled = compactor_settings.enabled
        self._orig_pruning = compactor_settings.pruning_enabled
        self._orig_threshold = compactor_settings.threshold_tokens
        compactor_settings.config_file = Path(self._temp_dir.name) / "compactor_config.json"

    async def asyncTearDown(self):
        await self.client.aclose()
        compactor_settings.config_file = self._orig_config_file
        compactor_settings.enabled = self._orig_enabled
        compactor_settings.pruning_enabled = self._orig_pruning
        compactor_settings.threshold_tokens = self._orig_threshold
        self._temp_dir.cleanup()

    async def test_dashboard_root(self):
        resp = await self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<!DOCTYPE html>", resp.text)
        self.assertIn("Antigravity Proxy", resp.text)

    async def test_dashboard_alias(self):
        resp = await self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("<!DOCTYPE html>", resp.text)

    async def test_hello_endpoint(self):
        for path in ["/api/hello", "/hello", "/v1/hello", "/v1/api/hello", "/v1/oauth/hello", "/oauth/hello"]:
            resp = await self.client.get(path)
            self.assertEqual(resp.status_code, 200, f"Failed on {path}")
            data = resp.json()
            self.assertEqual(data, {"message": "hello"}, f"Failed payload on {path}")

    async def test_claude_cli_bootstrap(self):
        resp = await self.client.get("/api/claude_cli/bootstrap")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertTrue(data["features"]["fast_mode"])

    async def test_context_settings_get_and_post(self):
        # 1. Get settings
        resp = await self.client.get("/api/context/settings")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("threshold_tokens", data)

        # 2. Update settings
        update_resp = await self.client.post(
            "/api/context/settings",
            json={"enabled": True, "threshold_tokens": 75000, "keep_last_n": 8, "model": "gemini-3.1-flash-lite"},
        )
        self.assertEqual(update_resp.status_code, 200)
        up_data = update_resp.json()
        self.assertEqual(up_data["settings"]["threshold_tokens"], 75000)

    async def test_cache_stats(self):
        resp = await self.client.get("/api/cache/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("tokens_saved", data)

    async def test_api_key_middleware_protection(self):
        protected_app = create_app(account_pool=self.pool, api_key="secret-key-123")
        transport = httpx.ASGITransport(app=protected_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Unauthorized request
            resp = await client.post(
                "/v1/chat/completions",
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            self.assertEqual(resp.status_code, 401)

            # 2. Request with invalid key
            resp_inv = await client.post(
                "/v1/chat/completions",
                headers={"Authorization": "Bearer wrong-key"},
                json={"messages": [{"role": "user", "content": "hi"}]},
            )
            self.assertEqual(resp_inv.status_code, 401)

            # 3. Request with valid x-api-key header (fails on empty account pool or client, but passes 401 auth)
            resp_valid = await client.get(
                "/v1/models",
                headers={"x-api-key": "secret-key-123"},
            )
            self.assertEqual(resp_valid.status_code, 200)

    async def test_count_tokens_fallback(self):
        resp = await self.client.post(
            "/v1/messages/count_tokens",
            json={"messages": [{"role": "user", "content": "hello world"}]}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("input_tokens", data)
        self.assertGreater(data["input_tokens"], 0)

    async def test_fetch_url_missing_param(self):
        resp = await self.client.get("/api/fetch-url")
        self.assertEqual(resp.status_code, 400)

    async def test_otlp_telemetry_sink(self):
        """OTLP sink must swallow all telemetry payloads with 200 and never forward."""
        import json as _json
        dummy_payload = _json.dumps({"resourceMetrics": []}).encode()
        for path in [
            "/otlp/v1/metrics",
            "/otlp/v1/traces",
            "/otlp/v1/logs",
            "/v1/traces",
            "/v1/logs",
        ]:
            resp = await self.client.post(
                path,
                content=dummy_payload,
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(resp.status_code, 200, f"OTLP sink failed on {path}")
            data = resp.json()
            self.assertTrue(data.get("success"), f"OTLP sink bad response on {path}")

    async def test_v1_models_returns_only_authentic_models(self):
        resp = await self.client.get("/v1/models")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        model_ids = {m["id"] for m in data.get("data", [])}

        # Real backend models should be present
        self.assertIn("gemini-3.8-flash-high", model_ids)
        self.assertIn("anthropic.claude-sonnet-4-6", model_ids)
        self.assertIn("gpt-oss-120b-medium", model_ids)

        # Available proxy models should also be advertised for ClaudeDev & OpenAI clients
        self.assertIn("gpt-4o", model_ids)
        self.assertIn("gpt-6-astra", model_ids)
        self.assertIn("o1", model_ids)
        self.assertIn("o3-mini", model_ids)
        self.assertIn("deepseek-r1", model_ids)
        self.assertIn("claude-5-5", model_ids)
        self.assertIn("anthropic.claude-sonnet-5-5-high", model_ids)

        # Non-existent / fake models should NOT be advertised in /v1/models
        self.assertNotIn("claude-5-fable", model_ids)
        self.assertNotIn("anthropic.claude-5-fable", model_ids)
        self.assertNotIn("claude-opus-5", model_ids)
        self.assertNotIn("anthropic.claude-opus-5", model_ids)

    async def test_api_models_returns_exact_models_catalog(self):
        resp = await self.client.get("/api/models")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("models", data)
        models = data["models"]

        # Real exact models should be present
        self.assertIn("gemini-3.8-flash-high", models)
        self.assertIn("claude-sonnet-4-6", models)
        self.assertIn("claude-opus-4-6-thinking", models)
        self.assertIn("claude-sonnet-5-5-high", models)
        self.assertIn("claude-opus-5-5-high", models)
        self.assertIn("gpt-oss-120b-medium", models)

        # Internal completion or telemetry endpoints should NOT be present
        for m_id in models.keys():
            self.assertFalse(m_id.startswith("tab_"), f"Unexpected tab model {m_id}")
            self.assertFalse(m_id.startswith("chat_"), f"Unexpected chat stub {m_id}")

        # Display names must be clean and accurate
        self.assertEqual(models["gemini-2.5-flash"]["displayName"], "Gemini 2.5 Flash")
        self.assertEqual(models["gemini-3.8-flash-tiered"]["displayName"], "Gemini 3.8 Flash (Tiered)")

    async def test_write_trajectory_acls(self):
        resp = await self.client.post(
            "/v1internal:writeTrajectoryAcls",
            json={"trajectoryId": "test-trajectory-123"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIsInstance(resp.json(), dict)

    async def test_cloudcode_internal_passthrough_actions(self):
        # 1. POST action with payload
        resp_post = await self.client.post(
            "/v1internal:fetchUserInfo",
            json={"project": "aicode-consumers"},
        )
        self.assertEqual(resp_post.status_code, 200)
        self.assertIsInstance(resp_post.json(), dict)

        # 2. GET action
        resp_get = await self.client.get("/v1internal:fetchAdminControls")
        self.assertEqual(resp_get.status_code, 200)
        self.assertIsInstance(resp_get.json(), dict)

        # 3. GET action with slash path (e.g. cascadeNuxes)
        resp_nux = await self.client.get("/v1internal/cascadeNuxes")
        self.assertEqual(resp_nux.status_code, 200)
        self.assertIsInstance(resp_nux.json(), dict)

    async def test_gemini_web_api_routes(self):
        # 1. Add web account with raw cookies
        add_resp = await self.client.post(
            "/api/accounts/gemini-web",
            json={
                "name": "My Gemini Web Session",
                "cdp_port": 9222,
                "raw_cookies": "__Secure-1PSID=psid_val_999; __Secure-1PSIDTS=ts_val_888",
            },
        )
        self.assertEqual(add_resp.status_code, 200)
        acc_data = add_resp.json()
        acc_id = acc_data["account_id"]
        self.assertEqual(acc_data["name"], "My Gemini Web Session")
        self.assertTrue(acc_data["has_cookies"])
        self.assertGreaterEqual(acc_data["cookies_count"], 2)

        # 2. Verify account appears in /api/accounts
        list_resp = await self.client.get("/api/accounts")
        self.assertEqual(list_resp.status_code, 200)
        accounts = list_resp.json().get("accounts", [])
        gw_accounts = [a for a in accounts if a.get("account_id") == acc_id]
        self.assertEqual(len(gw_accounts), 1)
        self.assertEqual(gw_accounts[0]["auth_method"], "gemini_web")

        # 3. Toggle web account
        toggle_resp = await self.client.post(f"/api/accounts/{acc_id}/toggle")
        self.assertEqual(toggle_resp.status_code, 200)
        self.assertFalse(toggle_resp.json()["enabled"])

        toggle_resp2 = await self.client.post(f"/api/accounts/{acc_id}/toggle")
        self.assertEqual(toggle_resp2.status_code, 200)
        self.assertTrue(toggle_resp2.json()["enabled"])

        # 4. Test account endpoint
        test_resp = await self.client.post(f"/api/accounts/{acc_id}/test")
        self.assertEqual(test_resp.status_code, 200)
        test_data = test_resp.json()
        self.assertEqual(test_data["account_id"], acc_id)
        self.assertEqual(test_data["auth_method"], "gemini_web")
        self.assertEqual(test_data["name"], "My Gemini Web Session")
        self.assertIn("latency_ms", test_data)
        self.assertIn("has_cookies", test_data)

        # 5. Targeting web account with an incompatible model (Claude) should return 400
        comp_resp = await self.client.post(
            "/v1/chat/completions",
            headers={"x-account-id": acc_id},
            json={
                "model": "claude-sonnet-4-6",
                "messages": [{"role": "user", "content": "hello"}],
            },
        )
        self.assertEqual(comp_resp.status_code, 400)
        self.assertIn("does not support model", comp_resp.text)

    async def test_api_accounts_quota_retention_and_cooldown(self):
        from agy_proxy.auth import AccountSession
        acc = AccountSession(
            account_id="acc_live_quota_test",
            refresh_token="ya29.live_refresh",
            auth_method="consumer",
            email="live_quota@example.com",
        )
        acc.quota_summary = {
            "groups": [
                {
                    "displayName": "Gemini Models",
                    "buckets": [
                        {
                            "bucketId": "gemini-weekly",
                            "displayName": "Weekly Limit Remaining",
                            "window": "weekly",
                            "remainingFraction": 0.2274,
                            "resetTime": "2026-09-22T08:00:00Z",
                        },
                        {
                            "bucketId": "gemini-5h",
                            "displayName": "Five Hour Limit Remaining",
                            "window": "5h",
                            "remainingFraction": 1.0,
                            "resetTime": "2026-09-18T22:00:00Z",
                        },
                    ],
                }
            ]
        }
        acc.mark_rate_limited("gemini-2.5-pro", duration=60)
        self.pool.accounts[acc.account_id] = acc

        resp = await self.client.get("/api/accounts")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        target = next((a for a in data["accounts"] if a["account_id"] == acc.account_id), None)
        self.assertIsNotNone(target)
        self.assertTrue(target["rate_limited"])
        self.assertIn("gemini", target["rate_limited_models"])

        q = target["quota_details"]["gemini"]
        self.assertTrue(q["is_rate_limited"])
        self.assertGreater(q["cooldown_seconds"], 0)
        self.assertEqual(q["weekly"]["percent"], 22.74)
        self.assertEqual(q["weekly"]["fraction"], 0.2274)
        self.assertEqual(q["5h"]["percent"], 100.0)
        self.assertEqual(q["5h"]["fraction"], 1.0)
        self.assertEqual(q["percent"], 22.74)

    def test_websocket_responses_auth_enforcement(self):
        protected_app = create_app(account_pool=self.pool, api_key="secret-proxy-key")
        tc = TestClient(protected_app)

        # 1. Unauthenticated connection must be rejected with WebSocketDisconnect (code 1008)
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with tc.websocket_connect("/v1/responses"):
                pass
        self.assertEqual(ctx.exception.code, 1008)

        # 2. Connection with wrong token query parameter must be rejected
        with self.assertRaises(WebSocketDisconnect) as ctx:
            with tc.websocket_connect("/v1/responses?token=wrong-key"):
                pass
        self.assertEqual(ctx.exception.code, 1008)

        # 3. Connection with valid token in query param succeeds
        with tc.websocket_connect("/v1/responses?token=secret-proxy-key") as ws:
            self.assertIsNotNone(ws)

        # 4. Connection with valid Authorization header succeeds
        with tc.websocket_connect("/v1/responses", headers={"Authorization": "Bearer secret-proxy-key"}) as ws:
            self.assertIsNotNone(ws)

    def test_websocket_responses_error_handling(self):
        tc = TestClient(self.app)
        with tc.websocket_connect("/v1/responses") as ws:
            # Send an invalid payload that will raise during parsing
            ws.send_text(json.dumps({"type": "response.create", "response": "malformed_string_payload"}))
            response_raw = ws.receive_text()
            data = json.loads(response_raw)
            self.assertEqual(data.get("type"), "response.failed")
            self.assertIn("error", data.get("response", {}))

    async def test_toggle_account_and_section_endpoints(self):
        import tempfile
        from pathlib import Path
        from agy_proxy.auth import GeminiWebSession

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            web_file = tmp / "web_sessions.json"
            self.pool.web_sessions_file = web_file

            acc = GeminiWebSession(
                account_id="gw_route_test",
                name="Route Test Web",
                cookies={"__Secure-1PSID": "route_test_cookie"},
                enabled=True,
            )
            self.pool.accounts[acc.account_id] = acc
            self.pool.save_accounts()

            # 1. Toggle individual account to disabled
            resp = await self.client.post(
                f"/api/accounts/{acc.account_id}/toggle",
                json={"enabled": False},
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertFalse(data["enabled"])
            self.assertFalse(acc.enabled)

            # Verify saved to web_sessions.json
            with open(web_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            self.assertFalse(saved["web_sessions"][0]["enabled"])

            # 2. Section toggle
            sec_resp = await self.client.post(
                "/api/accounts/section/web/toggle",
                json={"enabled": True},
            )
            self.assertEqual(sec_resp.status_code, 200)
            sec_data = sec_resp.json()
            self.assertTrue(sec_data["enabled"])
            self.assertTrue(acc.enabled)

            # 3. Concurrent section / individual toggle requests
            async def _toggle_task(val):
                return await self.client.post(
                    f"/api/accounts/{acc.account_id}/toggle",
                    json={"enabled": val},
                )

            tasks = [_toggle_task(i % 2 == 0) for i in range(20)]
            results = await asyncio.gather(*tasks)
            for r in results:
                self.assertEqual(r.status_code, 200)

            # File must still be valid JSON
            with open(web_file, "r", encoding="utf-8") as f:
                final_saved = json.load(f)
            self.assertEqual(len(final_saved["web_sessions"]), 1)
            self.assertIsInstance(final_saved["web_sessions"][0]["enabled"], bool)

    async def test_rename_account_with_proxy_url(self):
        oa = AccountSession(
            account_id="acc_rename_test",
            email="rename_test@gmail.com",
            refresh_token="rf_rename",
            name="Original Name",
        )
        self.pool.accounts["acc_rename_test"] = oa
        self.pool.save_accounts()

        resp = await self.client.post(
            "/api/accounts/acc_rename_test/rename",
            json={"name": "New Name", "proxy_url": "http://user:pass@proxy.example.com:8080"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["name"], "New Name")
        self.assertEqual(data["proxy_url"], "http://user:pass@proxy.example.com:8080")
        self.assertEqual(oa.name, "New Name")
        self.assertEqual(oa.proxy_url, "http://user:pass@proxy.example.com:8080")

        # Verify persisted to disk
        with open(self.pool.accounts_file, "r", encoding="utf-8") as f:
            disk_data = json.load(f)
        saved_acc = next(a for a in disk_data["accounts"] if a["account_id"] == "acc_rename_test")
        self.assertEqual(saved_acc["name"], "New Name")
        self.assertEqual(saved_acc["proxy_url"], "http://user:pass@proxy.example.com:8080")

    async def test_cloudcode_passthrough_sanitizes_uppercase_roles(self):
        oa = AccountSession(
            account_id="acc_role_test",
            email="role_test@gmail.com",
            refresh_token="rf_role",
            is_primary=True,
        )
        self.pool.accounts["acc_role_test"] = oa

        captured_requests = []

        class MockResponse:
            status_code = 200
            content = b'{"response": {}}'
            text = '{"response": {}}'
            headers = {"content-type": "application/json"}
            def json(self):
                return {"response": {}}

        class MockHttpClient:
            async def post(self, url, **kwargs):
                captured_requests.append((url, kwargs))
                return MockResponse()

        oa.get_http_client = unittest.mock.AsyncMock(return_value=MockHttpClient())
        oa.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer mock_tok"})

        payload = {
            "model": "claude-3-5-sonnet",
            "request": {
                "contents": [
                    {"role": "USER", "parts": [{"text": "Hello"}]},
                    {"role": "context", "parts": [{"text": "Context info"}]},
                    {"role": "MODEL", "parts": [{"text": "Hi there"}]},
                ]
            }
        }
        resp = await self.client.post("/v1internal:streamGenerateContent", json=payload)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(captured_requests), 1)

        sent_json = captured_requests[0][1]["json"]
        self.assertEqual(sent_json["model"], "claude-sonnet-4-6")
        contents = sent_json["request"]["contents"]
        self.assertEqual(contents[0]["role"], "user")
        self.assertEqual(contents[1]["role"], "user")
        self.assertEqual(contents[2]["role"], "model")

    async def test_cloudcode_passthrough_failover_on_error(self):
        acc1 = AccountSession(
            account_id="acc_fail1",
            email="fail1@gmail.com",
            refresh_token="rf_1",
            is_primary=True,
        )
        acc2 = AccountSession(
            account_id="acc_ok2",
            email="ok2@gmail.com",
            refresh_token="rf_2",
            is_primary=False,
        )
        self.pool.accounts["acc_fail1"] = acc1
        self.pool.accounts["acc_ok2"] = acc2

        class MockResp500:
            status_code = 500
            text = '{"error": {"code": 500, "message": "Unknown Error."}}'
            content = text.encode("utf-8")
            headers = {"content-type": "application/json"}
            def json(self):
                return {"error": {"code": 500, "message": "Unknown Error."}}

        class MockResp200:
            status_code = 200
            text = '{"response": {"text": "Success from acc2"}}'
            content = text.encode("utf-8")
            headers = {"content-type": "application/json"}
            def json(self):
                return {"response": {"text": "Success from acc2"}}

        class Client1:
            async def post(self, url, **kwargs):
                return MockResp500()

        class Client2:
            async def post(self, url, **kwargs):
                return MockResp200()

        acc1.get_http_client = unittest.mock.AsyncMock(return_value=Client1())
        acc1.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer tok1"})
        acc2.get_http_client = unittest.mock.AsyncMock(return_value=Client2())
        acc2.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer tok2"})

        resp = await self.client.post(
            "/v1internal:streamGenerateContent",
            json={"model": "gemini-2.5-flash", "request": {"contents": [{"role": "user", "parts": [{"text": "test"}]}]}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"response": {"text": "Success from acc2"}})
        self.assertEqual(acc2.total_requests, 1)

    async def test_cloudcode_passthrough_matches_authorization_token(self):
        acc1 = AccountSession(
            account_id="acc_a",
            email="user_a@gmail.com",
            access_token="token_a",
            refresh_token="rf_a",
            is_primary=True,
        )
        acc2 = AccountSession(
            account_id="acc_b",
            email="user_b@gmail.com",
            access_token="token_b",
            refresh_token="rf_b",
            is_primary=False,
        )
        self.pool.accounts["acc_a"] = acc1
        self.pool.accounts["acc_b"] = acc2

        called_account = []

        class MockUserClient:
            def __init__(self, acc):
                self.acc = acc
            async def post(self, url, **kwargs):
                called_account.append(self.acc.email)
                return unittest.mock.Mock(status_code=200, json=lambda: {"user": self.acc.email})

        acc1.get_http_client = unittest.mock.AsyncMock(return_value=MockUserClient(acc1))
        acc1.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer token_a"})
        acc2.get_http_client = unittest.mock.AsyncMock(return_value=MockUserClient(acc2))
        acc2.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer token_b"})

        # Call with Authorization matching acc2
        resp = await self.client.post(
            "/v1internal:retrieveUserQuotaSummary",
            headers={"Authorization": "Bearer token_b"},
            json={"project": "aicode-consumers"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(called_account, ["user_b@gmail.com"])

    async def test_cloudcode_passthrough_serves_cached_models_on_network_failure(self):
        """Tests that when network drops, fetchAvailableModels returns full cached models rather than empty dict."""
        acc1 = AccountSession(
            account_id="acc_net_fail",
            email="fail_net@gmail.com",
            refresh_token="rf_net",
            is_primary=True,
        )
        self.pool.accounts["acc_net_fail"] = acc1

        class NetFailClient:
            async def post(self, url, **kwargs):
                raise httpx.ConnectError("Network unreachable")

        acc1.get_http_client = unittest.mock.AsyncMock(return_value=NetFailClient())
        acc1.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer tok"})

        resp = await self.client.post("/v1internal:fetchAvailableModels", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("models", data)
        self.assertTrue(len(data["models"]) > 0)
        self.assertIn("gemini-3.8-flash-high", data["models"])
        # Verify model entry structure
        model_entry = data["models"]["gemini-3.8-flash-high"]
        self.assertIn("displayName", model_entry)
        if "capabilities" in model_entry:
            self.assertTrue(model_entry["capabilities"]["chat"]["boolValue"])
        elif "modelExperiments" in model_entry:
            self.assertIsInstance(model_entry["modelExperiments"], dict)

    async def test_cloudcode_passthrough_serves_cached_codeassist_on_network_failure(self):
        """Tests that when upstream fails, loadCodeAssist returns project info rather than empty dict."""
        acc1 = AccountSession(
            account_id="acc_ca_fail",
            email="fail_ca@gmail.com",
            refresh_token="rf_ca",
            is_primary=True,
        )
        self.pool.accounts["acc_ca_fail"] = acc1

        class NetFailClient:
            async def post(self, url, **kwargs):
                raise httpx.ConnectTimeout("Connection timed out")

        acc1.get_http_client = unittest.mock.AsyncMock(return_value=NetFailClient())
        acc1.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer tok"})

        resp = await self.client.post("/v1internal:loadCodeAssist", json={"metadata": {"ideType": "ANTIGRAVITY"}})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("currentTier", data)
        self.assertIn("cloudaicompanionProject", data)
        self.assertEqual(data["cloudaicompanionProject"], "aicode-consumers")

    async def test_cloudcode_passthrough_failover_on_404(self):
        """Tests that generation requests fail over to next candidate when receiving HTTP 404."""
        acc1 = AccountSession(
            account_id="acc_404",
            email="user_404@gmail.com",
            refresh_token="rf_404",
            is_primary=True,
        )
        acc2 = AccountSession(
            account_id="acc_200",
            email="user_200@gmail.com",
            refresh_token="rf_200",
            is_primary=False,
        )
        self.pool.accounts["acc_404"] = acc1
        self.pool.accounts["acc_200"] = acc2

        class Client404:
            async def post(self, url, **kwargs):
                return unittest.mock.Mock(
                    status_code=404,
                    text='{"error": {"code": 404, "message": "Requested entity was not found."}}',
                    content=b'{"error": {"code": 404, "message": "Requested entity was not found."}}',
                    headers={"content-type": "application/json"},
                    json=lambda: {"error": {"code": 404, "message": "Requested entity was not found."}},
                )

        class Client200:
            async def post(self, url, **kwargs):
                return unittest.mock.Mock(
                    status_code=200,
                    text='{"response": {"text": "Recovered turn"}}',
                    content=b'{"response": {"text": "Recovered turn"}}',
                    headers={"content-type": "application/json"},
                    json=lambda: {"response": {"text": "Recovered turn"}},
                )

        acc1.get_http_client = unittest.mock.AsyncMock(return_value=Client404())
        acc1.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer tok1"})
        acc2.get_http_client = unittest.mock.AsyncMock(return_value=Client200())
        acc2.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer tok2"})

        resp = await self.client.post(
            "/v1internal:streamGenerateContent",
            json={"model": "gemini-2.5-flash", "request": {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"response": {"text": "Recovered turn"}})
        self.assertEqual(acc2.total_requests, 1)

    async def test_cloudcode_passthrough_isolates_candidate_project_id(self):
        """Tests that each account sends its own project_id rather than a cross-account project_id."""
        acc1 = AccountSession(
            account_id="acc_proj1",
            email="proj1@gmail.com",
            project_id="project-alpha",
            refresh_token="rf_1",
            is_primary=False,
        )
        self.pool.accounts["acc_proj1"] = acc1

        posted_bodies = []

        class InspectClient:
            async def post(self, url, **kwargs):
                posted_bodies.append(kwargs.get("json"))
                return unittest.mock.Mock(
                    status_code=200,
                    text='{"ok": true}',
                    content=b'{"ok": true}',
                    headers={"content-type": "application/json"},
                    json=lambda: {"ok": True},
                )

        acc1.get_http_client = unittest.mock.AsyncMock(return_value=InspectClient())
        acc1.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer tok1"})

        # Request arrives with an old/different project
        resp = await self.client.post(
            "/v1internal:streamGenerateContent",
            json={
                "project": "project-from-prior-account",
                "model": "gemini-2.5-flash",
                "request": {"project": "project-from-prior-account", "contents": [{"role": "user", "parts": [{"text": "hi"}]}]},
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(posted_bodies), 1)
        self.assertEqual(posted_bodies[0]["project"], "project-alpha")
        self.assertEqual(posted_bodies[0]["request"]["project"], "project-alpha")

    async def test_cloudcode_passthrough_generation_error_returns_503(self):
        """Tests that when generation fails across all accounts, it returns 503 instead of 200 empty dict."""
        acc1 = AccountSession(
            account_id="acc_dead",
            email="dead@gmail.com",
            refresh_token="rf_dead",
            is_primary=True,
        )
        self.pool.accounts["acc_dead"] = acc1

        class DeadClient:
            async def post(self, url, **kwargs):
                raise httpx.ConnectError("Service unreachable")

        acc1.get_http_client = unittest.mock.AsyncMock(return_value=DeadClient())
        acc1.get_auth_headers = unittest.mock.AsyncMock(return_value={"Authorization": "Bearer tok"})

        resp = await self.client.post(
            "/v1internal:streamGenerateContent",
            json={"model": "gemini-2.5-flash", "request": {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}},
        )
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(resp.json()["error"]["code"], 503)
        self.assertEqual(resp.json()["error"]["status"], "UNAVAILABLE")

    async def test_export_and_import_accounts(self):
        oa = AccountSession(
            account_id="acc_export_test",
            email="export_test@gmail.com",
            refresh_token="rf_export",
            name="Export Account",
        )
        self.pool.accounts["acc_export_test"] = oa
        self.pool.save_accounts()

        # 1. Export
        resp = await self.client.get("/api/accounts/export")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("accounts", data)
        self.assertTrue(any(a["account_id"] == "acc_export_test" for a in data["accounts"]))

        # 2. Import
        import_payload = {
            "accounts": [
                {
                    "account_id": "imported_oa",
                    "email": "imported_oa@gmail.com",
                    "refresh_token": "rf_imp",
                    "auth_method": "consumer",
                },
                {
                    "account_id": "imported_key",
                    "api_key": "AIzaSyImportedKey",
                    "name": "Imported Key",
                },
            ]
        }
        imp_resp = await self.client.post("/api/accounts/import", json=import_payload)
        self.assertEqual(imp_resp.status_code, 200)
        imp_data = imp_resp.json()
        self.assertEqual(imp_data["status"], "ok")
        self.assertEqual(imp_data["imported_count"], 2)
        self.assertIn("imported_oa", self.pool.accounts)
        self.assertIn("imported_key", self.pool.accounts)
        self.assertEqual(self.pool.accounts["imported_key"].auth_method, "api_key")

    async def test_batch_delete_and_refresh(self):
        acc1 = AccountSession(
            account_id="acc_batch_1",
            email="b1@gmail.com",
            refresh_token="rf_b1",
        )
        acc2 = AccountSession(
            account_id="acc_batch_2",
            email="b2@gmail.com",
            refresh_token="rf_b2",
        )
        self.pool.accounts["acc_batch_1"] = acc1
        self.pool.accounts["acc_batch_2"] = acc2
        self.pool.save_accounts()

        # Mock refresh_access_token
        acc1.refresh_access_token = AsyncMock(return_value="new_tok1")
        acc2.refresh_access_token = AsyncMock(return_value="new_tok2")

        # Test batch refresh
        ref_resp = await self.client.post(
            "/api/accounts/batch-refresh",
            json={"account_ids": ["acc_batch_1", "acc_batch_2"]},
        )
        self.assertEqual(ref_resp.status_code, 200)
        self.assertEqual(ref_resp.json()["refreshed"], 2)

        # Test batch delete
        del_resp = await self.client.post(
            "/api/accounts/batch-delete",
            json={"account_ids": ["acc_batch_1"]},
        )
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.json()["deleted"], 1)
        self.assertNotIn("acc_batch_1", self.pool.accounts)
        self.assertIn("acc_batch_2", self.pool.accounts)

    async def test_process_control_endpoints(self):
        # 1. Process status
        status_resp = await self.client.get("/api/processes/status")
        self.assertEqual(status_resp.status_code, 200)
        st_data = status_resp.json()
        self.assertIn("agy", st_data)
        self.assertIn("language_server", st_data)
        self.assertIn("status", st_data["agy"])
        self.assertIn("status", st_data["language_server"])

        # 2. Process start (accepts process or process_name)
        start_resp1 = await self.client.post("/api/processes/start", json={"process": "agy"})
        self.assertEqual(start_resp1.status_code, 200)
        self.assertEqual(start_resp1.json()["action"], "started")

        start_resp2 = await self.client.post("/api/processes/start", json={"process_name": "language_server"})
        self.assertEqual(start_resp2.status_code, 200)
        self.assertEqual(start_resp2.json()["action"], "started")

        # 3. Process kill (supports process or process_name)
        kill_resp = await self.client.post("/api/processes/kill", json={"process_name": "nonexistent_proc_test"})
        self.assertEqual(kill_resp.status_code, 200)
        self.assertEqual(kill_resp.json()["killed_count"], 0)

    async def test_account_test_connection_endpoint(self):
        acc = AccountSession(
            account_id="acc_test_conn",
            email="test_conn@gmail.com",
            refresh_token="rf_tc",
        )
        acc.test_connection = AsyncMock(return_value={"ok": True, "message": "Connection verified"})
        self.pool.accounts["acc_test_conn"] = acc

        resp = await self.client.post("/api/accounts/acc_test_conn/test")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["account_id"], "acc_test_conn")
        self.assertIn("latency_ms", data)

    async def test_editor_endpoints_openai_chat_completions(self):
        acc = AccountSession(
            account_id="acc_editor",
            email="editor@gmail.com",
            refresh_token="rf_ed",
            is_primary=True,
        )
        self.pool.accounts["acc_editor"] = acc

        # Non-streaming chat completion mock
        with patch("agy_proxy.client.CloudCodeClient.generate_openai_chat", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "choices": [{"message": {"role": "assistant", "content": "Hello editor!"}}],
            }

            resp = await self.client.post(
                "/v1/chat/completions",
                json={
                    "model": "gemini-2.5-flash",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "stream": False,
                },
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["choices"][0]["message"]["content"], "Hello editor!")

    async def test_editor_endpoints_anthropic_messages(self):
        acc = AccountSession(
            account_id="acc_editor_claude",
            email="claude_editor@gmail.com",
            refresh_token="rf_cl",
            is_primary=True,
        )
        self.pool.accounts["acc_editor_claude"] = acc

        with patch("agy_proxy.client.CloudCodeClient.generate_anthropic_messages", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {
                "id": "msg_test",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Hello Claude Code!"}],
            }

            resp = await self.client.post(
                "/v1/messages",
                json={
                    "model": "claude-3-7-sonnet",
                    "messages": [{"role": "user", "content": "Hi Claude"}],
                    "max_tokens": 100,
                },
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["content"][0]["text"], "Hello Claude Code!")

    async def test_editor_endpoints_gemini_native(self):
        acc = AccountSession(
            account_id="acc_gem_native",
            email="gemini_native@gmail.com",
            refresh_token="rf_gn",
            is_primary=True,
        )
        self.pool.accounts["acc_gem_native"] = acc

        with patch("agy_proxy.client.CloudCodeClient.generate_gemini_native", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = {
                "candidates": [{"content": {"parts": [{"text": "Hello Gemini Native!"}], "role": "model"}}],
            }

            resp = await self.client.post(
                "/v1beta/models/gemini-2.5-flash:generateContent",
                json={"contents": [{"parts": [{"text": "Hi"}]}]},
            )
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()["candidates"][0]["content"]["parts"][0]["text"], "Hello Gemini Native!")


if __name__ == "__main__":
    unittest.main()

