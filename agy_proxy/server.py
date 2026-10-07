"""
FastAPI Server for Antigravity Proxy.
Provides OpenAI, Anthropic, and Gemini Native APIs,
Multi-Account Pool Management, and Web UI Dashboard.
"""

import asyncio
import copy
import json
import logging
import os
import random
import socket
import time
from contextlib import asynccontextmanager
from typing import Any
import urllib.parse
import httpx
from fastapi import FastAPI, HTTPException, Header, Request, status, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse

import sys
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    STATIC_DIR = Path(sys._MEIPASS) / "agy_proxy" / "static"
    if not STATIC_DIR.exists():
        STATIC_DIR = Path(sys._MEIPASS) / "static"
else:
    STATIC_DIR = Path(__file__).parent / "static"
from pydantic import BaseModel

from agy_proxy.auth import AccountPool, AuthManager, USER_AGENT
from agy_proxy.client import CloudCodeClient
from agy_proxy.models import (
    AnthropicRequest,
    DEFAULT_MODEL,
    ModelCard,
    ModelListResponse,
    VALID_CLOUDCODE_MODELS,
    PROXY_CATALOG_MODELS,
    OpenAIChatRequest,
    normalize_model_name,
    is_claude_5_5_model,
    get_claude_fallback_model,
)
from agy_proxy.converter import anthropic_to_cloudcode_payload
from agy_proxy.responses import (
    responses_payload_to_openai_chat,
    stream_responses_events,
    format_sse_event,
    generate_responses_dict,
)
from agy_proxy.ui import get_dashboard_html
from agy_proxy.experiments import (
    enhance_list_experiments,
    enhance_available_models,
    get_default_experiments_payload,
    get_experiments_status,
    save_experiment_config,
    load_experiment_config,
    reset_experiment_overrides,
)

logger = logging.getLogger("agy_proxy.server")


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str | None = None
    code_verifier: str | None = None
    proxy_url: str | None = None


# -----------------------------------------------------------------------------
# Resilient CloudCode Passthrough Metadata Cache
# Prevents model list wiping, UI resets, and IDE project detachment on network failure
# -----------------------------------------------------------------------------
_PASSTHROUGH_CACHE_FILE = Path.home() / ".config" / "agy-proxy" / "passthrough_cache.json"
_PASSTHROUGH_METADATA_CACHE: dict[str, Any] = {}


def _get_default_passthrough_response(action_key: str) -> dict[str, Any]:
    if action_key == "fetchAvailableModels":
        models_dict = {}
        for m in sorted(list(VALID_CLOUDCODE_MODELS)):
            meta = PROXY_CATALOG_MODELS.get(m, {})
            disp = meta.get("displayName", m)
            max_tok = meta.get("maxTokens", 1048576)
            models_dict[m] = {
                "displayName": disp,
                "maxTokens": max_tok,
                "capabilities": {
                    "chat": {"boolValue": True},
                    "code": {"boolValue": True},
                    "streaming": {"boolValue": True},
                    "toolCalling": {"boolValue": True},
                },
                "modelExperiments": {
                    "experiments": {
                        "extended_context": {"boolValue": True},
                        "reasoning": {"boolValue": True},
                    }
                },
            }
        return {
            "models": models_dict,
            "defaultAgentModelId": "gemini-3.8-flash-high",
            "agentModelSorts": list(models_dict.keys()),
            "commandModelIds": [m for m in models_dict.keys() if "flash" in m],
            "tabModelIds": [m for m in models_dict.keys() if "flash" in m],
            "experimentIds": ["exp-antigravity-models"],
            "tieredModelIds": [m for m in models_dict.keys() if "tiered" in m],
        }
    elif action_key == "loadCodeAssist":
        return {
            "currentTier": {
                "id": "free-tier",
                "name": "Antigravity",
                "description": "Gemini-powered code suggestions and chat in multiple IDEs",
                "privacyNotice": {"showNotice": False},
            },
            "allowedTiers": [
                {
                    "id": "free-tier",
                    "name": "Antigravity",
                    "description": "Gemini-powered code suggestions and chat in multiple IDEs",
                    "isDefault": True,
                }
            ],
            "cloudaicompanionProject": "aicode-consumers",
            "gcpManaged": False,
        }
    elif action_key == "listExperiments":
        return get_default_experiments_payload()
    elif action_key == "fetchUserInfo":
        return {
            "user": {
                "email": "user@antigravity",
                "name": "Antigravity User",
            }
        }
    return {}


def _init_passthrough_cache():
    global _PASSTHROUGH_METADATA_CACHE
    _PASSTHROUGH_METADATA_CACHE = {}
    if _PASSTHROUGH_CACHE_FILE.exists():
        try:
            with open(_PASSTHROUGH_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _PASSTHROUGH_METADATA_CACHE.update(data)
        except Exception as e:
            logger.debug("Could not load passthrough cache: %s", e)
    for k in ("fetchAvailableModels", "loadCodeAssist", "listExperiments"):
        if k not in _PASSTHROUGH_METADATA_CACHE:
            _PASSTHROUGH_METADATA_CACHE[k] = _get_default_passthrough_response(k)


def _save_passthrough_cache():
    try:
        _PASSTHROUGH_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_PASSTHROUGH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(_PASSTHROUGH_METADATA_CACHE, f, indent=2)
    except Exception as e:
        logger.debug("Could not save passthrough cache: %s", e)


def _get_cached_or_default_passthrough(action_key: str) -> dict[str, Any]:
    if action_key in _PASSTHROUGH_METADATA_CACHE:
        return copy.deepcopy(_PASSTHROUGH_METADATA_CACHE[action_key])
    return _get_default_passthrough_response(action_key)


def _process_passthrough_metadata(action_key: str, data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data, dict):
        return data
    if action_key == "listExperiments":
        return enhance_list_experiments(data)
    elif action_key == "fetchAvailableModels":
        return enhance_available_models(data)
    return data


def _extract_error_message(resp: Any) -> str:
    """Extract a clean, concise single-line error message from HTTP response."""
    if hasattr(resp, "json"):
        try:
            data = resp.json()
            if isinstance(data, dict):
                err = data.get("error")
                if isinstance(err, dict):
                    msg = err.get("message")
                    if msg:
                        return str(msg).strip().replace("\n", " ")
                elif isinstance(err, str):
                    return err.strip().replace("\n", " ")
        except Exception:
            pass
    text = getattr(resp, "text", str(resp)) or ""
    text = text.strip().replace("\n", " ")
    return text[:200] if len(text) > 200 else (text or "Unknown Error")


_init_passthrough_cache()


def create_app(
    auth_manager: AuthManager | None = None,
    account_pool: AccountPool | None = None,
    api_key: str | None = None,
    allowed_origins: list[str] | None = None,
) -> FastAPI:
    """Creates and configures the FastAPI application."""

    global _PASSTHROUGH_CACHE_FILE
    if account_pool and getattr(account_pool, "accounts_file", None):
        _PASSTHROUGH_CACHE_FILE = account_pool.accounts_file.parent / "passthrough_cache.json"
        _init_passthrough_cache()

    effective_api_key = (
        api_key
        or os.environ.get("AGY_PROXY_API_KEY")
        or os.environ.get("PROXY_API_KEY")
        or os.environ.get("API_KEY")
    )

    if account_pool:
        pool = account_pool
    elif auth_manager:
        pool = auth_manager.pool
    else:
        pool = AccountPool()

    client = CloudCodeClient(pool)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup: Ensure accounts are loaded and initialized
        try:
            if not pool.accounts:
                pool.load_accounts()
            await pool.initialize_all()
            models_dict = await pool.get_pool_models() if pool.accounts else {}
            logger.info("Antigravity Proxy ready: %d account(s) active, %d model(s) available in catalog", len(pool.accounts), len(models_dict))
        except Exception as e:
            logger.warning("Startup initialization warning: %s", e)

        # Background task for periodic quota refresh with randomized jitter (45-75s)
        bg_refresh_task = None
        async def _periodic_quota_refresh():
            while True:
                try:
                    jitter_sleep = random.uniform(45.0, 75.0)
                    await asyncio.sleep(jitter_sleep)
                    await pool.refresh_all_quotas(min_interval=40.0)
                    try:
                        pool.save_accounts()
                    except Exception:
                        pass
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.debug("Background quota refresh error: %s", e)

        bg_refresh_task = asyncio.create_task(_periodic_quota_refresh())

        yield
        # Shutdown
        try:
            pool.save_accounts()
        except Exception:
            pass
        if bg_refresh_task:
            bg_refresh_task.cancel()
            try:
                await bg_refresh_task
            except asyncio.CancelledError:
                pass

        for acc in pool.accounts.values():
            await acc.close()

    app = FastAPI(
        title="Antigravity Proxy",
        description="Multi-Account OpenAI, Anthropic, and Gemini proxy for Google Antigravity",
        version="1.1.0",
        lifespan=lifespan,
    )

    # Secure CORS configuration
    env_origins = os.environ.get("AGY_PROXY_ALLOWED_ORIGINS") or os.environ.get("CORS_ORIGINS")
    origins_to_allow = allowed_origins
    if origins_to_allow is None and env_origins:
        origins_to_allow = [o.strip() for o in env_origins.split(",") if o.strip()]

    if origins_to_allow and "*" in origins_to_allow:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    elif origins_to_allow:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins_to_allow,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # Default: securely allow localhost and local development origins
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[
                "http://localhost",
                "http://127.0.0.1",
                "http://[::1]",
            ],
            allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def verify_api_key(authorization: str | None = Header(None), x_api_key: str | None = Header(None)):
        if not effective_api_key:
            return
        token = None
        if authorization and authorization.startswith("Bearer "):
            token = authorization[7:].strip()
        elif authorization:
            token = authorization.strip()
        elif x_api_key:
            token = x_api_key.strip()

        if token != effective_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing API key.",
            )

    # -------------------------------------------------------------------------
    # Web UI and Dashboard Endpoints
    # -------------------------------------------------------------------------

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_root():
        return HTMLResponse(content=get_dashboard_html())

    @app.get("/dashboard", response_class=HTMLResponse)
    @app.get("/playground", response_class=HTMLResponse)
    @app.get("/analytics", response_class=HTMLResponse)
    @app.get("/integrations", response_class=HTMLResponse)
    @app.get("/settings", response_class=HTMLResponse)
    async def dashboard_page():
        return HTMLResponse(content=get_dashboard_html())

    @app.get("/favicon.ico")
    async def get_favicon():
        fav_path = STATIC_DIR / "favicon.ico"
        if fav_path.exists():
            return FileResponse(fav_path, media_type="image/x-icon")
        raise HTTPException(status_code=404, detail="Favicon not found")

    @app.get("/assets/image/antigravity-logo.png")
    @app.get("/antigravity-logo.png")
    async def get_antigravity_logo():
        logo_path = STATIC_DIR / "antigravity-logo.png"
        if logo_path.exists():
            return FileResponse(logo_path, media_type="image/png")
        raise HTTPException(status_code=404, detail="Logo not found")

    @app.api_route("/api/hello", methods=["GET", "HEAD"])
    @app.api_route("/hello", methods=["GET", "HEAD"])
    @app.api_route("/v1/hello", methods=["GET", "HEAD"])
    @app.api_route("/v1/api/hello", methods=["GET", "HEAD"])
    @app.api_route("/v1/oauth/hello", methods=["GET", "HEAD"])
    @app.api_route("/oauth/hello", methods=["GET", "HEAD"])
    async def claude_code_hello():
        return {"message": "hello"}

    @app.get("/api/claude_cli/bootstrap")
    async def claude_cli_bootstrap():
        return {
            "status": "ok",
            "features": {
                "fast_mode": True,
                "extended_context": True,
            },
            "model_configs": {},
        }

    @app.get("/api/claude_code_penguin_mode")
    async def claude_code_penguin_mode():
        return {
            "enabled": False,
            "status": "disabled",
        }

    @app.get("/api/web/domain_info")
    async def web_domain_info():
        return {"allowed": True}

    @app.post("/api/web-search")
    @app.post("/v1/web-search")
    @app.post("/web-search")
    async def handle_web_search_route(request: Request):
        """Direct web search endpoint for Claude Code CCR proxy mode."""
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        try:
            from agy_proxy.search import search_multi_engine
            body = await request.json()
            query = body.get("query", "") or body.get("q", "")
            allowed = body.get("allowed_domains", [])
            blocked = body.get("blocked_domains", [])
            results = await search_multi_engine(query, allowed_domains=allowed, blocked_domains=blocked, account_pool=pool)
            return {"results": results}
        except Exception as e:
            logger.warning("Direct web search error: %s", e)
            return {"results": [], "error": {"error_type": "api_error", "error_message": str(e)}}

    @app.post("/api/oauth/claude_cli/create_api_key")
    async def claude_cli_create_api_key():
        return {"api_key": "dummy", "status": "ok"}

    @app.get("/api/claude_code/organizations/metrics_enabled")
    async def claude_code_metrics():
        return {"metrics_enabled": False}

    @app.get("/api/oauth/claude_cli/roles")
    async def claude_code_roles():
        return {"roles": ["admin", "developer"]}

    @app.get("/mcp-registry/v0/servers")
    async def mcp_registry_servers():
        return {"servers": []}

    # -------------------------------------------------------------------------
    # OpenTelemetry / OTLP sink — swallow all Codex/OpenAI telemetry locally.
    # Codex CLI sends metrics to ab.chatgpt.com/otlp/v1/*; by pointing
    # OTEL_EXPORTER_OTLP_ENDPOINT at the proxy we absorb them here and return
    # 200 so the client never retries. Nothing is forwarded externally.
    # -------------------------------------------------------------------------
    @app.api_route("/log", methods=["POST", "OPTIONS"])
    @app.api_route("/api/client/metrics", methods=["POST", "OPTIONS"])
    @app.api_route("/otlp/v1/metrics", methods=["POST", "OPTIONS"])
    @app.api_route("/otlp/v1/traces", methods=["POST", "OPTIONS"])
    @app.api_route("/otlp/v1/logs", methods=["POST", "OPTIONS"])
    @app.api_route("/v1/traces", methods=["POST", "OPTIONS"])
    @app.api_route("/v1/logs", methods=["POST", "OPTIONS"])
    async def otlp_sink(request: Request):
        """Silent OTLP/OpenTelemetry sink — absorbs telemetry without forwarding."""
        return JSONResponse({"success": True}, status_code=200)

    @app.post("/v1/messages/count_tokens")
    @app.post("/messages/count_tokens")
    async def count_tokens(request: Request):
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        body: dict[str, Any] = {}
        try:
            body = await request.json()
        except Exception:
            return {"input_tokens": 10}

        # Fast heuristic fallback
        serialized = json.dumps(body)
        fallback_tokens = max(1, int(len(serialized) / 3.7))

        # Attempt exact native counting via Google CloudCode API
        if pool and pool.accounts:
            try:
                acc = next((a for a in pool.accounts.values() if getattr(a, "enabled", True)), None)
                if acc:
                    req_model = normalize_model_name(body.get("model", DEFAULT_MODEL))
                    anthropic_req = AnthropicRequest.model_validate(body)
                    cloud_payload = anthropic_to_cloudcode_payload(anthropic_req, project_id="aicode-consumers")
                    contents = cloud_payload.get("request", {}).get("contents", [])
                    if contents:
                        token = await acc.get_valid_token()
                        headers = {
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                            "User-Agent": USER_AGENT,
                        }
                        post_data = {
                            "request": {
                                "model": req_model,
                                "contents": contents,
                            }
                        }
                        async with httpx.AsyncClient(timeout=1.5) as http_client:
                            resp = await http_client.post(
                                "https://daily-cloudcode-pa.googleapis.com/v1internal:countTokens",
                                headers=headers,
                                json=post_data,
                            )
                            if resp.status_code == 200:
                                exact_tokens = resp.json().get("totalTokens")
                                if exact_tokens is not None:
                                    return {"input_tokens": int(exact_tokens)}
            except Exception as e:
                logger.debug("Native countTokens error, falling back to estimation: %s", e)

        return {"input_tokens": fallback_tokens}

    @app.api_route("/api/fetch-url", methods=["GET", "POST"])
    async def fetch_url_endpoint(request: Request):
        """Fetches web page content using Google's native crawler (Trawler / Googlebot)."""
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        url = ""
        if request.method == "GET":
            url = request.query_params.get("url", "")
        else:
            try:
                body = await request.json()
                url = body.get("url", "")
            except Exception:
                pass
        if not url:
            raise HTTPException(status_code=400, detail="Missing 'url' parameter")

        from agy_proxy.search import fetch_url_via_trawler
        content = await fetch_url_via_trawler(url, account_pool=pool)
        if content is not None:
            return {"status": "ok", "url": url, "content": content, "source": "google-trawler"}

        # Fallback to direct fetch
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as http_client:
                r = await http_client.get(url)
                return {"status": "ok", "url": url, "content": r.text, "source": "direct"}
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {str(e)}")

    @app.get("/health")
    async def health_check():
        acc_count = len(pool.accounts)
        return {"status": "ok", "accounts_count": acc_count}

    @app.get("/api/info")
    async def get_proxy_info():
        acc = next(iter(pool.accounts.values())) if pool.accounts else None
        return {
            "project_id": acc.project_id if acc else None,
            "tier_name": acc.tier_info.get("name", "Antigravity") if acc else "N/A",
            "auth_method": acc.auth_method if acc else "consumer",
            "expiry_timestamp": acc.expiry_timestamp if acc else 0.0,
            "total_accounts": len(pool.accounts),
        }

    # -------------------------------------------------------------------------
    # Multi-Account Pool API Endpoints
    # -------------------------------------------------------------------------

    @app.get("/api/accounts")
    async def list_accounts():
        if hasattr(pool, "reload_if_modified"):
            pool.reload_if_modified()
        if time.time() - getattr(pool, "last_quota_refresh_time", 0.0) > 60.0:
            asyncio.create_task(pool.refresh_all_quotas(min_interval=45.0))
        accounts_list = [acc.to_dict() for acc in pool.accounts.values()]
        return {"accounts": accounts_list}

    @app.get("/api/accounts/export")
    async def export_accounts():
        import json
        if hasattr(pool, "reload_if_modified"):
            pool.reload_if_modified()
        # Create an export list using internal persistence mechanisms or to_dict
        # We will collect everything from pool.accounts and try to serialize
        # A simpler way is to just return what we have in the pool's storage files
        # Or export the dicts. The frontend imports JSON. Let's just return to_dict() arrays, and frontend can download it. Wait, the prompt says "Hint: interact with pool.accounts and save them" for POST. Let's just return the raw accounts file or a merge of them, OR a list of items to dump. Actually, `pool.accounts` objects have a lot of properties. Let's build a JSON of the basic properties to allow migration.
        # But `BaseAccountSession.to_dict` drops sensitive tokens. Let's just do a dump of what we'd write. Wait, the proxy already writes to files.
        # But we need full export.
        
        # We will manually dump the credentials using the exact format `pool.save_accounts` uses.
        accounts_data = []
        for acc in pool.accounts.values():
            entry = {
                "account_id": acc.account_id,
                "email": acc.email,
                "name": acc.name,
                "picture": acc.picture,
                "auth_method": acc.auth_method,
                "project_id": getattr(acc, "project_id", None),
                "region_code": getattr(acc, "region_code", None),
                "enabled": acc.enabled,
                "is_primary": acc.is_primary,
                "proxy_url": getattr(acc, "proxy_url", None),
                "total_requests": getattr(acc, "total_requests", 0),
                "last_used_timestamp": getattr(acc, "last_used_timestamp", 0.0),
                "last_used_model": getattr(acc, "last_used_model", None),
            }
            if acc.auth_method == "consumer":
                entry["refresh_token"] = getattr(acc, "refresh_token", "")
                entry["access_token"] = getattr(acc, "access_token", "")
                entry["id_token"] = getattr(acc, "id_token", "")
                entry["expiry_timestamp"] = getattr(acc, "expiry_timestamp", 0.0)
            elif acc.auth_method == "api_key":
                entry["api_key"] = getattr(acc, "api_key", "")
            elif acc.auth_method == "gemini_web":
                entry["cdp_port"] = getattr(acc, "cdp_port", 9222)
                entry["cookies"] = getattr(acc, "_cookies", {})
            accounts_data.append(entry)
        return Response(content=json.dumps({"accounts": accounts_data}, indent=2), media_type="application/json")

    @app.post("/api/accounts/import")
    async def import_accounts(request: Request):
        try:
            body = await request.json()
            if isinstance(body, list):
                imported = body
            elif isinstance(body, dict):
                imported = body.get("accounts") or body.get("api_keys") or body.get("web_sessions") or []
            else:
                imported = []

            for item in imported:
                acc_id = item.get("account_id") or f"import_{os.urandom(4).hex()}"
                am = item.get("auth_method")
                if not am:
                    if item.get("api_key"):
                        am = "api_key"
                    elif item.get("cookies") or item.get("cdp_port"):
                        am = "gemini_web"
                    else:
                        am = "consumer"

                if am == "consumer":
                    from agy_proxy.auth.base import AccountSession
                    acc = AccountSession(
                        account_id=acc_id,
                        refresh_token=item.get("refresh_token", ""),
                        access_token=item.get("access_token"),
                        expiry_timestamp=item.get("expiry_timestamp", 0.0),
                        email=item.get("email"),
                        name=item.get("name"),
                        picture=item.get("picture"),
                        auth_method="consumer",
                        project_id=item.get("project_id"),
                        region_code=item.get("region_code"),
                        is_primary=bool(item.get("is_primary", False)),
                        enabled=bool(item.get("enabled", True)),
                        proxy_url=item.get("proxy_url"),
                        id_token=item.get("id_token"),
                        on_token_refreshed=pool.save_accounts,
                    )
                elif am == "api_key":
                    from agy_proxy.auth.api_key import AIStudioApiKeySession
                    acc = AIStudioApiKeySession(
                        account_id=acc_id,
                        api_key=item.get("api_key", ""),
                        name=item.get("name"),
                        email=item.get("email"),
                        picture=item.get("picture"),
                        project_id=item.get("project_id"),
                        region_code=item.get("region_code"),
                        is_primary=bool(item.get("is_primary", False)),
                        enabled=bool(item.get("enabled", True)),
                        proxy_url=item.get("proxy_url"),
                        on_token_refreshed=pool.save_accounts,
                    )
                elif am == "gemini_web":
                    from agy_proxy.auth.gemini_web import GeminiWebSession
                    acc = GeminiWebSession(
                        account_id=acc_id,
                        name=item.get("name"),
                        email=item.get("email"),
                        picture=item.get("picture"),
                        cdp_port=item.get("cdp_port", 9222),
                        cookies=item.get("cookies", {}),
                        is_primary=bool(item.get("is_primary", False)),
                        enabled=bool(item.get("enabled", True)),
                        proxy_url=item.get("proxy_url"),
                        on_token_refreshed=pool.save_accounts,
                    )
                else:
                    continue
                acc.total_requests = item.get("total_requests", 0)
                acc.last_used_timestamp = item.get("last_used_timestamp", 0.0)
                acc.last_used_model = item.get("last_used_model")
                pool.accounts[acc_id] = acc
            pool.save_accounts()
            return {"status": "ok", "imported": len(imported), "imported_count": len(imported)}
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    class BatchAccountsRequest(BaseModel):
        account_ids: list[str]

    @app.post("/api/accounts/batch-delete")
    async def batch_delete_accounts(req: BatchAccountsRequest):
        deleted = 0
        for aid in req.account_ids:
            clean_id = urllib.parse.unquote(aid).strip()
            if pool.remove_account(clean_id) or pool.remove_account(aid):
                deleted += 1
        return {"status": "ok", "deleted": deleted}

    @app.post("/api/accounts/batch-refresh")
    async def batch_refresh_accounts(req: BatchAccountsRequest):
        refreshed = 0
        for aid in req.account_ids:
            clean_id = urllib.parse.unquote(aid).strip()
            acc = pool.get_account(clean_id) or pool.get_account(aid)
            if acc:
                try:
                    if hasattr(acc, "get_at_token"):
                        await acc.get_at_token(force_refresh=True)
                    elif hasattr(acc, "refresh_access_token"):
                        await acc.refresh_access_token(force=True)
                    elif hasattr(acc, "fetch_quota"):
                        await acc.fetch_quota()
                    refreshed += 1
                except Exception as e:
                    logger.warning("Failed to refresh account %s: %s", aid, e)
        pool.save_accounts()
        return {"status": "ok", "refreshed": refreshed}

    @app.post("/api/accounts/oauth/start")
    async def start_account_oauth():
        flow_data = pool.start_oauth_flow()
        return flow_data

    @app.post("/api/accounts/oauth/callback")
    async def complete_account_oauth(req: OAuthCallbackRequest):
        try:
            acc = await pool.complete_oauth_flow(
                code_or_url=req.code,
                verifier=req.code_verifier,
                state=req.state,
                proxy_url=req.proxy_url,
            )
            return acc.to_dict()
        except Exception as e:
            logger.error("OAuth callback error: %s", e)
            raise HTTPException(status_code=400, detail=str(e))

    class ProcessActionRequest(BaseModel):
        process: str | None = None
        process_name: str | None = None

        @property
        def target(self) -> str:
            return (self.process or self.process_name or "").lower().strip()

    @app.get("/api/processes/status")
    async def get_processes_status():
        import psutil
        agy_running = False
        agy_pid = None
        ls_running = False
        ls_pid = None
        my_pid = os.getpid()

        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pid = p.info.get('pid')
                if pid == my_pid:
                    continue
                cmd = p.info.get('cmdline') or []
                cmd_str = " ".join(cmd).lower()
                name = (p.info.get('name') or "").lower()

                # Exclude agy_proxy itself or its worker threads
                if "agy_proxy" in cmd_str or "agy-proxy" in cmd_str:
                    continue

                bin_name = os.path.basename(cmd[0]).lower() if cmd else ""

                if not agy_running and (
                    name in ("antigravity", "agy")
                    or bin_name in ("antigravity", "agy")
                    or (bin_name == "python" and len(cmd) > 1 and "agy" in os.path.basename(cmd[1]).lower())
                ):
                    agy_running = True
                    agy_pid = pid

                if not ls_running and (
                    "language_server" in name
                    or "language-server" in name
                    or any("language_server" in os.path.basename(arg) or "language-server" in os.path.basename(arg) for arg in cmd)
                ):
                    ls_running = True
                    ls_pid = pid
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return {
            "agy": {"status": "running" if agy_running else "stopped", "pid": agy_pid},
            "language_server": {"status": "running" if ls_running else "stopped", "pid": ls_pid},
        }

    @app.post("/api/processes/start")
    async def start_process(req: ProcessActionRequest):
        target = req.target
        return {"status": "ok", "process": target, "action": "started"}

    @app.post("/api/processes/kill")
    async def kill_process(req: ProcessActionRequest):
        import psutil
        killed = 0
        target = req.target
        my_pid = os.getpid()

        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pid = p.info.get('pid')
                if pid == my_pid:
                    continue
                cmd = p.info.get('cmdline') or []
                cmd_str = " ".join(cmd).lower()
                name = (p.info.get('name') or "").lower()

                # Safety guard: never kill agy-proxy itself
                if "agy_proxy" in cmd_str or "agy-proxy" in cmd_str:
                    continue

                bin_name = os.path.basename(cmd[0]).lower() if cmd else ""
                match = False
                if target in ("agy", "antigravity") and (
                    name in ("antigravity", "agy")
                    or bin_name in ("antigravity", "agy")
                    or (bin_name == "python" and len(cmd) > 1 and "agy" in os.path.basename(cmd[1]).lower())
                ):
                    match = True
                elif target in ("language_server", "language-server") and (
                    "language_server" in name
                    or "language-server" in name
                    or any("language_server" in os.path.basename(arg) or "language-server" in os.path.basename(arg) for arg in cmd)
                ):
                    match = True

                if match:
                    p.kill()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
        return {"status": "ok", "process": target, "killed_count": killed}

    class AddApiKeyRequest(BaseModel):
        api_key: str
        name: str | None = "Gemini API Key"
        proxy_url: str | None = None

    @app.post("/api/accounts/apikey")
    async def add_account_api_key(req: AddApiKeyRequest):
        try:
            acc = await pool.add_api_key_account(api_key=req.api_key, name=req.name, proxy_url=req.proxy_url)
            return acc.to_dict()
        except Exception as e:
            logger.error("Error adding API key account: %s", e)
            raise HTTPException(status_code=400, detail=str(e))

    class AddGeminiWebRequest(BaseModel):
        name: str | None = "Gemini Web"
        cdp_port: int | None = 9222
        raw_cookies: str | None = None
        cookies: dict[str, str] | None = None
        proxy_url: str | None = None

    @app.post("/api/accounts/gemini-web")
    async def add_account_gemini_web(req: AddGeminiWebRequest):
        """Adds a Gemini Web browser session account using cookies, HAR, or CDP (experimental)."""
        try:
            acc = await pool.add_gemini_web_account(
                name=req.name,
                cdp_port=req.cdp_port or 9222,
                raw_cookies=req.raw_cookies,
                cookies=req.cookies,
                proxy_url=req.proxy_url,
            )
            d = acc.to_dict()
            if d.get("has_cookies"):
                d["message"] = f"Gemini Web account added with {d.get('cookies_count', 0)} cookies."
            else:
                d["message"] = (
                    "Gemini Web account added but no cookies found — open Chrome/Helium with gemini.google.com logged in, or paste cookies/HAR."
                )
            return d
        except Exception as e:
            logger.error("Error adding Gemini Web account: %s", e)
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/accounts/{account_id}/gemini-web/refresh-cookies")
    async def refresh_gemini_web_cookies(account_id: str):
        """Re-fetches cookies from the browser via CDP for an existing Gemini Web account."""
        from agy_proxy.auth import GeminiWebSession
        acc = pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")
        if not isinstance(acc, GeminiWebSession):
            raise HTTPException(status_code=400, detail="Account is not a Gemini Web session.")
        ok = await acc.refresh_cookies_from_browser()
        if ok:
            await acc.get_at_token(force_refresh=True)
        return {
            "status": "ok" if ok else "no_cookies",
            "account_id": acc.account_id,
            "cookies_refreshed": ok,
            "cdp_port": acc.cdp_port,
            "has_at_token": bool(acc._at_token),
            "cookies_count": len(acc._cookies),
        }

    @app.post("/api/accounts/{account_id}/test")
    async def test_account(account_id: str):
        """Tests connectivity and validity of an account (OAuth, API Key, or Gemini Web)."""
        acc = pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")
        start_t = time.time()
        try:
            res = await acc.test_connection()
            latency_ms = round((time.time() - start_t) * 1000, 1)
            return {
                "account_id": acc.account_id,
                "name": acc.name or acc.email,
                "email": acc.email,
                "auth_method": acc.auth_method,
                "latency_ms": latency_ms,
                "enabled": acc.enabled,
                **res,
            }
        except Exception as e:
            latency_ms = round((time.time() - start_t) * 1000, 1)
            logger.error("Error testing account %s: %s", account_id, e)
            return {
                "account_id": acc.account_id,
                "name": acc.name or acc.email,
                "email": acc.email,
                "auth_method": acc.auth_method,
                "latency_ms": latency_ms,
                "enabled": acc.enabled,
                "ok": False,
                "error": str(e),
            }

    class RenameAccountRequest(BaseModel):
        name: str | None = None
        proxy_url: str | None = None

    @app.post("/api/accounts/{account_id}/rename")
    @app.patch("/api/accounts/{account_id}/rename")
    async def rename_account(account_id: str, req: RenameAccountRequest):
        acc = pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")
        new_name = req.name.strip() if req.name and req.name.strip() else None
        update_proxy = req.proxy_url is not None
        pool.rename_account(
            acc.account_id,
            new_name=new_name,
            proxy_url=req.proxy_url,
            update_proxy=update_proxy,
        )
        return {
            "status": "ok",
            "account_id": acc.account_id,
            "name": acc.name,
            "proxy_url": getattr(acc, "proxy_url", None),
        }

    class ToggleAccountRequest(BaseModel):
        enabled: bool | None = None

    class ToggleSectionRequest(BaseModel):
        auth_method: str | None = None
        enabled: bool | None = None

    @app.post("/api/accounts/{account_id}/toggle")
    async def toggle_account(account_id: str, req: ToggleAccountRequest | None = None):
        acc = pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")
        current_state = acc.enabled
        new_state = req.enabled if (req and req.enabled is not None) else not current_state
        pool.set_account_enabled(acc.account_id, new_state)
        return {"status": "ok", "account_id": acc.account_id, "enabled": new_state}

    @app.post("/api/accounts/toggle_all")
    async def toggle_all_accounts(req: ToggleAccountRequest):
        new_state = req.enabled if req.enabled is not None else True
        pool.set_all_accounts_enabled(new_state)
        return {"status": "ok", "enabled": new_state, "count": len(pool.accounts)}

    @app.post("/api/accounts/section/{section}/toggle")
    @app.post("/api/accounts/toggle_section")
    async def toggle_section_accounts(
        section: str | None = None,
        req: ToggleSectionRequest | None = None,
    ):
        target_section = section or (req.auth_method if req else None) or "consumer"
        new_state = req.enabled if (req and req.enabled is not None) else True
        count = pool.set_section_accounts_enabled(target_section, new_state)
        return {"status": "ok", "section": target_section, "enabled": new_state, "count": count}

    @app.post("/api/accounts/{account_id}/reset-stats")
    async def reset_account_stats_endpoint(account_id: str):
        acc = pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")
        pool.reset_account_stats(acc.account_id)
        return {"status": "ok", "account_id": acc.account_id, "total_requests": 0, "last_used_model": None}

    @app.post("/api/accounts/reset_all_stats")
    async def reset_all_stats_endpoint():
        pool.reset_account_stats()
        return {"status": "ok", "total_requests": 0}

    @app.delete("/api/accounts/{account_id}")
    async def delete_account(account_id: str):
        acc = pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")
        removed = pool.remove_account(acc.account_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Account not found.")
        return {"status": "deleted", "account_id": acc.account_id}

    @app.post("/api/accounts/{account_id}/primary")
    async def set_primary_account(account_id: str):
        acc = pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")
        success = pool.set_primary(acc.account_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to set primary account.")
        return {"status": "ok", "account_id": acc.account_id, "is_primary": True}

    @app.post("/api/accounts/{account_id}/activate-cli")
    async def activate_account_cli(
        account_id: str,
        target: str | None = "all",
        set_primary: bool = True,
    ):
        """Activates the specified OAuth account as the current Google Antigravity CLI, IDE, or both session."""
        unquoted_id = urllib.parse.unquote(account_id).strip()
        acc = pool.get_account(unquoted_id) or pool.get_account(account_id)
        if not acc:
            try:
                pool.load_accounts()
            except Exception:
                pass
            acc = pool.get_account(unquoted_id) or pool.get_account(account_id)

        # Fallback search by ID, email, or name
        if not acc:
            targets = {unquoted_id.lower(), account_id.lower()}
            for a in pool.accounts.values():
                if (
                    a.account_id.lower() in targets
                    or (a.email and a.email.lower() in targets)
                    or (a.name and a.name.lower() in targets)
                ):
                    acc = a
                    break

        if not acc:
            raise HTTPException(status_code=404, detail=f"Account '{unquoted_id}' not found.")

        # If matched account is non-consumer, look for a matching consumer (OAuth) account
        if acc.auth_method != "consumer":
            consumer_match = next(
                (
                    a for a in pool.accounts.values()
                    if a.auth_method == "consumer"
                    and (
                        a.account_id in (unquoted_id, account_id)
                        or (a.email and a.email.lower() in (unquoted_id.lower(), account_id.lower()))
                        or (a.name and a.name.lower() in (unquoted_id.lower(), account_id.lower()))
                    )
                ),
                None,
            )
            if consumer_match:
                acc = consumer_match
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Only Google OAuth accounts can be activated in Antigravity CLI/IDE. Found account '{acc.name or acc.account_id}' is '{acc.auth_method}'.",
                )
        from agy_proxy.switcher import (
            activate_account_in_antigravity,
            format_agy_quota_display,
            resolve_antigravity_destinations,
        )
        if set_primary:
            pool.set_primary(acc.account_id)
        try:
            from agy_proxy.cache import session_affinity
            session_affinity.unpin_all()
        except Exception:
            pass

        target_paths = resolve_antigravity_destinations(target or "all")

        try:
            written = await activate_account_in_antigravity(acc, target_paths=target_paths, target_env=target or "all", allow_overwrite=True)
            try:
                if hasattr(acc, "fetch_quota"):
                    await acc.fetch_quota()
            except Exception:
                pass
            quota_text = format_agy_quota_display(acc)
            return {
                "status": "activated",
                "account_id": acc.account_id,
                "target": target,
                "email": acc.email,
                "destinations": [str(p) for p in written],
                "quota_display": quota_text,
            }
        except PermissionError as pe:
            logger.warning("Permission error activating account %s in Antigravity: %s", acc.account_id, pe)
            raise HTTPException(status_code=403, detail=str(pe))
        except Exception as e:
            logger.error("Failed to activate account in Antigravity: %s", e)
            raise HTTPException(status_code=500, detail=f"Failed to activate session: {e}")

    @app.get("/api/accounts/{account_id}/quota-display")
    async def get_account_quota_display(account_id: str):
        """Returns the official agy ASCII Models & Quota text representation for an account."""
        unquoted_id = urllib.parse.unquote(account_id).strip()
        acc = pool.get_account(unquoted_id) or pool.get_account(account_id)
        if not acc:
            raise HTTPException(status_code=404, detail="Account not found.")
        try:
            if hasattr(acc, "fetch_quota"):
                await acc.fetch_quota()
        except Exception:
            pass
        from agy_proxy.switcher import format_agy_quota_display
        return {
            "account_id": acc.account_id,
            "email": acc.email,
            "quota_display": format_agy_quota_display(acc),
        }

    @app.get("/api/accounts/cli-active")
    async def get_cli_active_account():
        """Reads the AGY CLI and IDE token files and returns which pool accounts are currently active in each."""
        if hasattr(pool, "reload_if_modified"):
            pool.reload_if_modified()

        from agy_proxy.switcher import get_active_antigravity_accounts
        cli_acc, ide_acc, standalone_acc = get_active_antigravity_accounts(pool)

        return {
            "cli": {
                "account_id": cli_acc.account_id if cli_acc else None,
                "email": cli_acc.email if cli_acc else None,
                "name": (cli_acc.name or cli_acc.email) if cli_acc else None,
            },
            "standalone": {
                "account_id": standalone_acc.account_id if standalone_acc else None,
                "email": standalone_acc.email if standalone_acc else None,
                "name": (standalone_acc.name or standalone_acc.email) if standalone_acc else None,
            },
            "ide": {
                "account_id": ide_acc.account_id if ide_acc else None,
                "email": ide_acc.email if ide_acc else None,
                "name": (ide_acc.name or ide_acc.email) if ide_acc else None,
            },
            "account_id": cli_acc.account_id if cli_acc else (standalone_acc.account_id if standalone_acc else None),
            "email": cli_acc.email if cli_acc else (standalone_acc.email if standalone_acc else None),
        }

    @app.post("/api/accounts/switch-next-cli")
    async def switch_next_account_cli(target: str | None = "all"):
        """Switches the Antigravity CLI/IDE session to the next available account with highest quota."""
        from agy_proxy.switcher import switch_antigravity_session
        try:
            acc, written = await switch_antigravity_session(pool=pool, to_next=True, target_env=target or "all", set_primary=True)
            try:
                from agy_proxy.cache import session_affinity
                session_affinity.unpin_all()
            except Exception:
                pass
            return {
                "status": "switched",
                "account_id": acc.account_id,
                "email": acc.email,
                "target": target or "all",
                "destinations": [str(p) for p in written],
            }
        except PermissionError as pe:
            logger.warning("Permission error switching Antigravity session: %s", pe)
            raise HTTPException(status_code=403, detail=str(pe))
        except Exception as e:
            logger.error("Error switching Antigravity session: %s", e)
            raise HTTPException(status_code=400, detail=str(e))

    @app.post("/api/accounts/refresh_all")
    async def refresh_all_accounts():
        await pool.initialize_all()
        return {"status": "refreshed", "count": len(pool.accounts)}


    @app.get("/api/cache/stats")
    async def get_cache_stats():
        from agy_proxy.cache import google_context_cache, session_affinity
        return {
            "tokens_saved": google_context_cache.total_tokens_saved,
            "cache_hits": google_context_cache.cache_hits,
            "cache_misses": google_context_cache.cache_misses,
            "active_sessions": len(session_affinity._sessions),
            "cached_contents_count": len(google_context_cache._cache_map),
        }

    @app.get("/api/context/settings")
    async def get_compactor_settings():
        from agy_proxy.compactor import compactor_settings
        return compactor_settings.to_dict()

    @app.post("/api/context/settings")
    async def update_compactor_settings(request: Request):
        from agy_proxy.compactor import compactor_settings
        body = await request.json()
        if "enabled" in body:
            compactor_settings.enabled = bool(body["enabled"])
        if "threshold_tokens" in body:
            compactor_settings.threshold_tokens = int(body["threshold_tokens"])
        if "keep_last_n" in body:
            compactor_settings.keep_last_n = int(body["keep_last_n"])
        if "model" in body:
            compactor_settings.model = str(body["model"])
        if "pruning_enabled" in body:
            compactor_settings.pruning_enabled = bool(body["pruning_enabled"])
        if "prune_keep_tools" in body:
            compactor_settings.prune_keep_tools = int(body["prune_keep_tools"])
        if "prune_max_chars" in body:
            compactor_settings.prune_max_chars = int(body["prune_max_chars"])
        compactor_settings.save()
        return {"status": "ok", "settings": compactor_settings.to_dict()}

    @app.post("/api/context/prune")
    async def manual_prune_context(request: Request):
        from agy_proxy.compactor import prune_tool_results
        body = await request.json()
        messages = body.get("messages", [])
        if not messages or not isinstance(messages, list):
            raise HTTPException(status_code=400, detail="Messages array is required.")
        keep_last_tools = body.get("keep_last_tools")
        max_chars = body.get("max_chars")
        pruned_msgs, count, tokens_saved = prune_tool_results(
            messages,
            keep_last_tools=keep_last_tools,
            max_chars=max_chars,
            enabled=True,
        )
        return {
            "status": "pruned",
            "messages": pruned_msgs,
            "pruned_count": count,
            "tokens_saved": tokens_saved,
        }

    @app.post("/api/context/compact")
    async def manual_compact_context(request: Request):
        from agy_proxy.compactor import compact_conversation_history
        body = await request.json()
        messages = body.get("messages", [])
        if not messages or not isinstance(messages, list):
            raise HTTPException(status_code=400, detail="Messages array is required.")
        keep_last_n = body.get("keep_last_n")
        compacted, before, after = await compact_conversation_history(pool, messages, keep_last_n=keep_last_n)
        savings_pct = int((1.0 - (after / max(1, before))) * 100) if before > 0 else 0
        return {
            "status": "compacted",
            "messages": compacted,
            "tokens_before": before,
            "tokens_after": after,
            "savings_percent": savings_pct,
        }

    # -------------------------------------------------------------------------
    # Experimental Features & Flags API
    # -------------------------------------------------------------------------
    @app.get("/api/experiments")
    async def get_experiments_api():
        return get_experiments_status()

    @app.post("/api/experiments")
    async def update_experiments_api(request: Request):
        body = await request.json()
        cfg = load_experiment_config()
        if "enabled" in body:
            cfg["enabled"] = bool(body["enabled"])
        if "mode" in body:
            new_mode = str(body["mode"])
            if new_mode in ("curated", "all_safe", "passthrough"):
                cfg["mode"] = new_mode
            else:
                raise HTTPException(status_code=400, detail="Invalid mode. Choose: curated, all_safe, passthrough")
        if "overrides" in body and isinstance(body["overrides"], dict):
            if "custom_overrides" not in cfg or not isinstance(cfg["custom_overrides"], dict):
                cfg["custom_overrides"] = {}
            for k, v in body["overrides"].items():
                if v is None:
                    cfg["custom_overrides"].pop(k, None)
                else:
                    cfg["custom_overrides"][k] = bool(v)
        save_experiment_config(cfg)
        return {"status": "ok", "experiments": get_experiments_status()}

    @app.post("/api/experiments/reset")
    async def reset_experiments_api():
        reset_experiment_overrides()
        return {"status": "ok", "experiments": get_experiments_status()}

    @app.get("/api/models")
    async def get_proxy_models():
        models_dict = await pool.get_pool_models() if pool.accounts else {}
        if not models_dict:
            from agy_proxy.models import EXACT_MODEL_METADATA, VALID_CLOUDCODE_MODELS
            models_dict = {
                m_id: {
                    "displayName": EXACT_MODEL_METADATA.get(m_id, {}).get("displayName", m_id),
                    "maxTokens": EXACT_MODEL_METADATA.get(m_id, {}).get("maxTokens", 1048576),
                    "quotaInfo": {"remainingFraction": 0.0},
                    "accounts": {},
                    "available_accounts": 0,
                    "total_accounts": len(pool.accounts),
                    "pool_remaining_fraction": 0.0,
                }
                for m_id in sorted(VALID_CLOUDCODE_MODELS)
            }
        return {"models": models_dict}

    @app.post("/api/refresh")
    async def force_refresh():
        await pool.initialize_all()
        return {"status": "refreshed", "accounts_count": len(pool.accounts)}

    @app.get("/api/version")
    async def get_version_info(force: bool = False):
        from agy_proxy.updater import check_for_updates
        info = await check_for_updates(force=force)
        return info

    @app.post("/api/update/pull")
    async def update_git_repo():
        from agy_proxy.updater import trigger_git_pull
        res = await trigger_git_pull()
        return res

    # -------------------------------------------------------------------------
    # OpenAI Compatible API
    # -------------------------------------------------------------------------

    @app.get("/v1/models")
    async def list_openai_models(request: Request):
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        models_dict = await pool.get_pool_models() if pool.accounts else {}
        if not models_dict:
            models_dict = {
                m_id: {"displayName": m_id, "maxTokens": 65536, "quotaInfo": {}}
                for m_id in sorted(VALID_CLOUDCODE_MODELS)
            }

        model_cards: list[ModelCard] = []
        seen_ids = set()

        # 1. Live models from pool / editor
        for m_id, info in models_dict.items():
            # Filter internal code-completion or hash models from public chat catalog
            if m_id.startswith(("tab_", "chat_")):
                continue

            seen_ids.add(m_id)
            quota_info = info.get("quotaInfo", {})
            pool_rem = info.get("pool_remaining_fraction", quota_info.get("remainingFraction", 1.0))
            model_cards.append(
                ModelCard(
                    id=m_id,
                    display_name=info.get("displayName", m_id),
                    max_tokens=info.get("maxTokens"),
                    remaining_quota=pool_rem,
                    reset_time=quota_info.get("resetTime"),
                )
            )
            # Claude Code gateway format: anthropic/<model> and anthropic.<model>
            for prefix in (f"anthropic/{m_id}", f"anthropic.{m_id}"):
                if prefix not in seen_ids:
                    seen_ids.add(prefix)
                    model_cards.append(
                        ModelCard(
                            id=prefix,
                            display_name=info.get("displayName", m_id),
                            max_tokens=info.get("maxTokens"),
                            remaining_quota=pool_rem,
                            reset_time=quota_info.get("resetTime"),
                        )
                    )

        # 2. All available proxy models (OpenAI, Codex, Claude aliases, DeepSeek)
        for m_id, info in PROXY_CATALOG_MODELS.items():
            if m_id not in seen_ids:
                seen_ids.add(m_id)
                target_backend = normalize_model_name(m_id)
                target_info = models_dict.get(target_backend, {})
                quota_info = target_info.get("quotaInfo", {})
                pool_rem = target_info.get("pool_remaining_fraction", quota_info.get("remainingFraction", 1.0))
                model_cards.append(
                    ModelCard(
                        id=m_id,
                        display_name=info.get("displayName", m_id),
                        max_tokens=info.get("maxTokens", 128000),
                        remaining_quota=pool_rem,
                        reset_time=quota_info.get("resetTime"),
                    )
                )
            for prefix in (f"anthropic/{m_id}", f"anthropic.{m_id}"):
                if prefix not in seen_ids:
                    seen_ids.add(prefix)
                    model_cards.append(
                        ModelCard(
                            id=prefix,
                            display_name=info.get("displayName", m_id),
                            max_tokens=info.get("maxTokens", 128000),
                            remaining_quota=pool_rem,
                            reset_time=quota_info.get("resetTime"),
                        )
                    )

        return ModelListResponse(data=model_cards)

    @app.get("/api/codex/models.json")
    @app.get("/v1/models/codex.json")
    async def get_codex_models():
        """Serves Codex CLI ModelsResponse catalog containing all proxy models."""
        from agy_proxy.codex_helper import get_catalog_dict
        return get_catalog_dict()

    @app.get("/api/codex/status")
    async def get_codex_status_endpoint(request: Request):
        """Returns installation and configuration status of OpenAI Codex CLI."""
        from agy_proxy.codex_helper import get_codex_status
        port = request.url.port or 8000
        return get_codex_status(port=port)

    class CodexSetupRequest(BaseModel):
        port: int | None = None
        model: str | None = "gemini-3.8-flash-high"

    @app.post("/api/codex/setup")
    async def setup_codex_endpoint(request: Request, req: CodexSetupRequest | None = None):
        """Automatically configures OpenAI Codex CLI with full models catalog and safe backup."""
        from agy_proxy.codex_helper import setup_codex
        target_port = (req.port if req and req.port else None) or request.url.port or 8000
        target_model = (req.model if req and req.model else "gemini-3.8-flash-high")
        return setup_codex(port=target_port, model=target_model)

    @app.post("/api/codex/restore")
    async def restore_codex_endpoint():
        """Restores original OpenAI Codex CLI configuration from backup."""
        from agy_proxy.codex_helper import restore_codex
        return restore_codex()

    @app.get("/v1/models/{model_id}")
    async def get_openai_model(model_id: str, request: Request):
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        normalized = normalize_model_name(model_id)
        models_dict = {}
        if pool.accounts:
            acc = next(iter(pool.accounts.values()))
            models_dict = acc.available_models
        if not models_dict:
            models_dict = {
                m_id: {"displayName": m_id, "maxTokens": 65536, "quotaInfo": {}}
                for m_id in sorted(VALID_CLOUDCODE_MODELS)
            }
        info = models_dict.get(normalized) or PROXY_CATALOG_MODELS.get(model_id) or PROXY_CATALOG_MODELS.get(normalized, {})
        return ModelCard(
            id=model_id,
            display_name=info.get("displayName", model_id),
            max_tokens=info.get("maxTokens"),
        )

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    @app.post("/v1/v1/chat/completions")
    async def openai_chat_completions(req: OpenAIChatRequest, request: Request):
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )

        session_id = (
            request.headers.get("session-id")
            or request.headers.get("anthropic-session-id")
            or request.headers.get("x-session-id")
            or request.headers.get("x-conversation-id")
        )
        target_account_id = (
            request.headers.get("x-account-id")
            or request.headers.get("account-id")
            or request.query_params.get("account_id")
            or getattr(req, "account_id", None)
        )

        try:
            if req.stream:
                return StreamingResponse(
                    client.stream_openai_chat(req, session_key=session_id, specific_account_id=target_account_id),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            else:
                response_data = await client.generate_openai_chat(req, session_key=session_id, specific_account_id=target_account_id)
                return JSONResponse(content=response_data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": "2"},
                    content={
                        "error": {
                            "message": "All accounts in pool have hit rate limit / quota (429). Please wait a few minutes or add more accounts.",
                            "type": "insufficient_quota",
                            "code": 429,
                        }
                    },
                )
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except (ValueError, RuntimeError) as e:
            err_msg = str(e)
            if "does not support model" in err_msg or "not found in pool" in err_msg or "disabled" in err_msg:
                return JSONResponse(
                    status_code=400,
                    content={"error": {"message": err_msg, "type": "invalid_request_error", "code": 400}},
                )
            logger.error("OpenAI Chat Completion Error: %s", e, exc_info=logger.isEnabledFor(logging.DEBUG))
            raise HTTPException(status_code=500, detail=err_msg)
        except Exception as e:
            logger.error("OpenAI Chat Completion Error: %s", e, exc_info=logger.isEnabledFor(logging.DEBUG))
            err_msg = str(e) or f"{type(e).__name__}: Upstream request failed"
            raise HTTPException(status_code=500, detail=err_msg)

    # -------------------------------------------------------------------------
    # OpenAI Responses API (/v1/responses) — Codex CLI & Agent compatibility
    # -------------------------------------------------------------------------

    @app.head("/v1/responses")
    @app.head("/responses")
    @app.head("/v1/v1/responses")
    async def openai_responses_head():
        return Response(status_code=200)

    @app.post("/v1/responses")
    @app.post("/responses")
    @app.post("/v1/v1/responses")
    async def openai_responses_endpoint(request: Request):
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )

        try:
            payload = await request.json()
        except Exception:
            payload = {}

        chat_req, detected_session_key = responses_payload_to_openai_chat(payload)

        session_id = (
            request.headers.get("session-id")
            or request.headers.get("x-session-id")
            or request.headers.get("x-conversation-id")
            or detected_session_key
        )
        target_account_id = (
            request.headers.get("x-account-id")
            or request.headers.get("account-id")
            or request.query_params.get("account_id")
            or payload.get("account_id")
        )

        is_stream = payload.get("stream", True)

        try:
            if is_stream:
                async def event_generator():
                    async for event in stream_responses_events(
                        client=client,
                        chat_req=chat_req,
                        session_key=session_id,
                        specific_account_id=target_account_id,
                    ):
                        yield format_sse_event(event)

                return StreamingResponse(
                    event_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            else:
                resp_data = await generate_responses_dict(
                    client=client,
                    chat_req=chat_req,
                    session_key=session_id,
                    specific_account_id=target_account_id,
                )
                return JSONResponse(content=resp_data)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": "2"},
                    content={
                        "error": {
                            "message": "All accounts in pool have hit rate limit / quota (429). Please wait a few minutes or add more accounts.",
                            "type": "insufficient_quota",
                            "code": 429,
                        }
                    },
                )
            raise HTTPException(status_code=e.response.status_code, detail=str(e))
        except Exception as e:
            logger.error("OpenAI Responses Error: %s", e, exc_info=logger.isEnabledFor(logging.DEBUG))
            err_msg = str(e) or f"{type(e).__name__}: Upstream request failed"
            raise HTTPException(status_code=500, detail=err_msg)

    @app.websocket("/v1/responses")
    @app.websocket("/responses")
    @app.websocket("/v1/v1/responses")
    async def openai_responses_ws(websocket: WebSocket):
        if effective_api_key:
            token = None
            auth_header = websocket.headers.get("authorization") or websocket.headers.get("x-api-key")
            query_token = websocket.query_params.get("token") or websocket.query_params.get("api_key")
            if auth_header and auth_header.startswith("Bearer "):
                token = auth_header[7:].strip()
            elif auth_header:
                token = auth_header.strip()
            elif query_token:
                token = query_token.strip()

            if token != effective_api_key:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or missing API key.")
                return

        await websocket.accept()
        try:
            while True:
                msg_text = await websocket.receive_text()
                if not msg_text:
                    continue
                try:
                    data = json.loads(msg_text)
                except Exception:
                    continue

                req_type = data.get("type")
                if req_type == "response.create" or "input" in data or "model" in data:
                    try:
                        payload = data.get("response", data) if req_type == "response.create" else data
                        chat_req, detected_session_key = responses_payload_to_openai_chat(payload)

                        async for event in stream_responses_events(
                            client=client,
                            chat_req=chat_req,
                            session_key=detected_session_key,
                        ):
                            await websocket.send_text(json.dumps(event, ensure_ascii=False))
                    except Exception as err:
                        logger.error("Responses WebSocket stream error: %s", err, exc_info=True)
                        err_event = {
                            "type": "response.failed",
                            "response": {
                                "status": "failed",
                                "error": {
                                    "message": str(err) or "Internal server error during responses stream",
                                    "type": "server_error",
                                },
                            },
                        }
                        try:
                            await websocket.send_text(json.dumps(err_event, ensure_ascii=False))
                        except Exception:
                            pass
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug("Responses WebSocket closed: %s", e)

    # -------------------------------------------------------------------------
    # Anthropic Compatible API
    # -------------------------------------------------------------------------

    @app.post("/v1/messages")
    @app.post("/messages")
    @app.post("/v1/v1/messages")
    async def anthropic_messages(req: AnthropicRequest, request: Request):
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )

        session_id = (
            request.headers.get("session-id")
            or request.headers.get("anthropic-session-id")
            or request.headers.get("x-session-id")
            or request.headers.get("x-conversation-id")
        )
        target_account_id = (
            request.headers.get("x-account-id")
            or request.headers.get("account-id")
            or request.query_params.get("account_id")
            or getattr(req, "account_id", None)
        )

        try:
            if req.stream:
                return StreamingResponse(
                    client.stream_anthropic_messages(req, session_key=session_id, specific_account_id=target_account_id),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    },
                )
            else:
                response_data = await client.generate_anthropic_messages(req, session_key=session_id, specific_account_id=target_account_id)
                return JSONResponse(content=response_data)
        except httpx.HTTPStatusError as e:
            err_type = "rate_limit_error" if e.response.status_code == 429 else "api_error"
            return JSONResponse(
                status_code=e.response.status_code,
                headers={"Retry-After": "2"},
                content={
                    "type": "error",
                    "error": {
                        "type": err_type,
                        "message": str(e) or f"HTTP {e.response.status_code} Error",
                    },
                },
            )
        except (ValueError, RuntimeError) as e:
            err_msg = str(e)
            if "does not support model" in err_msg or "not found in pool" in err_msg or "disabled" in err_msg:
                return JSONResponse(
                    status_code=400,
                    content={
                        "type": "error",
                        "error": {
                            "type": "invalid_request_error",
                            "message": err_msg,
                        },
                    },
                )
            logger.error("Anthropic Messages Error: %s", e, exc_info=logger.isEnabledFor(logging.DEBUG))
            raise HTTPException(status_code=500, detail=err_msg)
        except Exception as e:
            logger.error("Anthropic Messages Error: %s", e, exc_info=logger.isEnabledFor(logging.DEBUG))
            err_msg = str(e) or f"{type(e).__name__}: Upstream request failed"
            return JSONResponse(
                status_code=500,
                headers={"Retry-After": "2"},
                content={
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": err_msg,
                    },
                },
            )

    # -------------------------------------------------------------------------
    # Gemini Native API
    # -------------------------------------------------------------------------

    @app.post("/v1beta/models/{model_name}:streamGenerateContent")
    async def gemini_stream_native(model_name: str, request: Request):
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        body = await request.json()
        target_account_id = (
            request.headers.get("x-account-id")
            or request.headers.get("account-id")
            or request.query_params.get("account_id")
            or (body.get("account_id") if isinstance(body, dict) else None)
        )
        return StreamingResponse(
            client.stream_gemini_native(model_name, body, specific_account_id=target_account_id),
            media_type="text/event-stream",
        )

    @app.post("/v1beta/models/{model_name}:generateContent")
    async def gemini_generate_native(model_name: str, request: Request):
        verify_api_key(
            authorization=request.headers.get("Authorization"),
            x_api_key=request.headers.get("x-api-key"),
        )
        body = await request.json()
        target_account_id = (
            request.headers.get("x-account-id")
            or request.headers.get("account-id")
            or request.query_params.get("account_id")
            or (body.get("account_id") if isinstance(body, dict) else None)
        )
        res = await client.generate_gemini_native(model_name, body, specific_account_id=target_account_id)
        return JSONResponse(content=res)

    # -------------------------------------------------------------------------
    # Internal CloudCode Compatibility Endpoints
    # -------------------------------------------------------------------------

    @app.api_route("/v1internal:{action}", methods=["GET", "POST", "PUT", "DELETE"])
    @app.api_route("/v1internal/{action_path:path}", methods=["GET", "POST", "PUT", "DELETE"])
    async def cloudcode_internal_passthrough(
        request: Request,
        action: str | None = None,
        action_path: str | None = None,
    ):
        """Universal passthrough / compatibility router for CloudCode v1internal actions:
        (e.g., loadCodeAssist, fetchAvailableModels, fetchUserInfo, fetchAdminControls,
        retrieveUserQuotaSummary, listExperiments, writeTrajectoryAcls, cascadeNuxes)."""
        body = None
        if request.method in ("POST", "PUT", "PATCH"):
            try:
                body = await request.json()
            except Exception:
                try:
                    raw_body = await request.body()
                    body = raw_body.decode("utf-8") if raw_body else None
                except Exception:
                    body = None
        # --- Route to proper account and track usage ---
        is_generation = action in ("streamGenerateContent", "generateContent") or action_path in ("streamGenerateContent", "generateContent")

        # 1. Sanitize roles: rewrite 'context' and 'USER' to lowercase 'user', 'MODEL'/'assistant' to 'model'
        # Crucial: Anthropic Claude models reject 'USER' with HTTP 500 Unknown Error.
        def _sanitize_roles(contents_list):
            if not isinstance(contents_list, list):
                return
            for item in contents_list:
                if isinstance(item, dict):
                    r = item.get("role")
                    if isinstance(r, str):
                        r_lower = r.lower()
                        if r_lower in ("user", "context"):
                            item["role"] = "user"
                        elif r_lower in ("model", "assistant"):
                            item["role"] = "model"

        req_model = DEFAULT_MODEL
        if isinstance(body, dict):
            req_model = body.get("model") or body.get("request", {}).get("model") or DEFAULT_MODEL
            from agy_proxy.models import normalize_model_name
            req_model = normalize_model_name(req_model)
            if "model" in body:
                body["model"] = req_model
            if "request" in body and isinstance(body["request"], dict):
                if "model" in body["request"]:
                    body["request"]["model"] = req_model
                _sanitize_roles(body["request"].get("contents", []))
            _sanitize_roles(body.get("contents", []))

        # 2. Identify target account from Authorization header if present
        target_account = None
        auth_header = request.headers.get("authorization") or ""
        bearer_token = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None
        if bearer_token:
            for candidate in pool.accounts.values():
                if not getattr(candidate, "enabled", True):
                    continue
                if getattr(candidate, "access_token", None) == bearer_token or getattr(candidate, "refresh_token", None) == bearer_token:
                    target_account = candidate
                    break
            if not target_account:
                try:
                    from agy_proxy.auth.token_utils import _decode_jwt_payload
                    claims = _decode_jwt_payload(bearer_token)
                    token_email = (claims.get("email") or "").strip().lower()
                    if token_email:
                        for candidate in pool.accounts.values():
                            if getattr(candidate, "enabled", True) and (getattr(candidate, "email", "") or "").strip().lower() == token_email:
                                target_account = candidate
                                break
                except Exception:
                    pass

        # 3. Build candidate accounts list
        if is_generation:
            try:
                candidates = pool.get_candidate_accounts(model=req_model)
            except Exception as e:
                logger.debug("Failed to get candidate accounts: %s", e)
                candidates = [a for a in pool.accounts.values() if getattr(a, "enabled", True)]

            # Prioritize target_account if requested and healthy
            if target_account and target_account in candidates:
                candidates = [target_account] + [a for a in candidates if a.account_id != target_account.account_id]
            elif target_account and getattr(target_account, "enabled", True):
                candidates = [target_account] + candidates
        else:
            if target_account:
                candidates = [target_account]
            else:
                primary_acc = pool.primary_account if hasattr(pool, "primary_account") else None
                if primary_acc and primary_acc.enabled:
                    candidates = [primary_acc]
                else:
                    candidates = [a for a in pool.accounts.values() if getattr(a, "enabled", True)]

        # Action key normalized
        action_key = (action or action_path or "").split("?")[0].strip(":")
        route_desc = f"/v1internal:{action}" if action else f"/v1internal/{action_path}"
        is_metadata = action_key in (
            "fetchAvailableModels",
            "loadCodeAssist",
            "listExperiments",
            "fetchUserInfo",
            "retrieveUserQuotaSummary",
        )

        if not candidates:
            if is_metadata:
                cached_data = _get_cached_or_default_passthrough(action_key)
                cached_data = _process_passthrough_metadata(action_key, cached_data)
                return JSONResponse(status_code=200, content=cached_data)
            return JSONResponse(status_code=200, content={})

        timeout_sec = 180.0 if is_generation else 8.0
        query_params = dict(request.query_params)
        from agy_proxy.auth import CLOUDCODE_BASE_URL
        if action:
            target_url = f"{CLOUDCODE_BASE_URL}/v1internal:{action}"
        else:
            target_url = f"{CLOUDCODE_BASE_URL}/v1internal/{action_path}"

        last_error = ""

        # 4. Multi-candidate failover loop
        for acc_idx, acc in enumerate(candidates):
            is_last = (acc_idx == len(candidates) - 1)
            acc_label = getattr(acc, "email", acc.account_id)
            if is_generation:
                logger.info("[%s] %s (Antigravity CloudCode)", acc_label, req_model or "streamGenerateContent")
            else:
                logger.debug("[%s] CloudCode passthrough: %s", acc_label, route_desc)

            # Ensure candidate uses its own project ID to avoid 404 permissions error across accounts
            candidate_body = copy.deepcopy(body) if isinstance(body, dict) else body
            if isinstance(candidate_body, dict):
                acc_proj = getattr(acc, "project_id", None) or "aicode-consumers"
                if "project" in candidate_body:
                    candidate_body["project"] = acc_proj
                if "request" in candidate_body and isinstance(candidate_body["request"], dict):
                    if "project" in candidate_body["request"]:
                        candidate_body["request"]["project"] = acc_proj

            try:
                headers = await acc.get_auth_headers()
                if "user-agent" in request.headers:
                    headers["User-Agent"] = request.headers["user-agent"]

                c = await acc.get_http_client()

                if request.method == "POST":
                    if isinstance(candidate_body, dict):
                        resp = await c.post(target_url, headers=headers, json=candidate_body, params=query_params, timeout=timeout_sec)
                    elif candidate_body is not None:
                        resp = await c.post(target_url, headers=headers, content=str(candidate_body).encode("utf-8"), params=query_params, timeout=timeout_sec)
                    else:
                        resp = await c.post(target_url, headers=headers, params=query_params, timeout=timeout_sec)
                elif request.method == "GET":
                    resp = await c.get(target_url, headers=headers, params=query_params, timeout=timeout_sec)
                else:
                    resp = await c.request(request.method, target_url, headers=headers, json=candidate_body if isinstance(candidate_body, dict) else None, params=query_params, timeout=timeout_sec)

                # Retry / failover logic
                if resp.status_code == 401 and not is_last:
                    logger.warning("[%s] Got 401 Unauthorized. Refreshing token...", acc_label)
                    try:
                        await acc.refresh_access_token(force=True)
                    except Exception:
                        pass
                    continue

                if resp.status_code == 429 and not is_last:
                    logger.warning("[%s] Quota reached (429) for %s. Failing over to next account...", acc_label, req_model if is_generation else "default")
                    acc.mark_rate_limited(req_model if is_generation else "default", duration=60.0)
                    continue

                if resp.status_code in (404, 500, 502, 503, 504) and is_generation and not is_last:
                    if resp.status_code == 404:
                        if not hasattr(acc, "unsupported_models"):
                            acc.unsupported_models = set()
                        acc.unsupported_models.add(req_model)
                        if getattr(acc, "available_models", None) and req_model in acc.available_models:
                            acc.available_models.pop(req_model, None)
                    err_hint = _extract_error_message(resp)
                    logger.warning("[%s] CloudCode error %d (%s) for %s. Failing over to next account in pool...", acc_label, resp.status_code, err_hint, req_model)
                    logger.debug("[%s] CloudCode failover raw body: %s", acc_label, resp.text)
                    continue

                # Last candidate got 404 or 429: If Claude 5.5 reached quota or is not enabled, auto-fallback to Claude 4.6 so generation never breaks
                if resp.status_code in (404, 429) and is_generation and is_last:
                    if is_claude_5_5_model(req_model):
                        fallback_model = get_claude_fallback_model(req_model)
                        if resp.status_code == 429:
                            acc.mark_rate_limited(req_model, duration=60.0)
                            reason_msg = "reached quota limit (429)"
                        else:
                            reason_msg = "returned 404 (not enabled on this account)"
                        logger.warning(
                            "[%s] ⚠️ Model %s %s. 🔄 Auto-falling back to Claude 4.6 (%s) so generation continues without error!",
                            acc_label,
                            req_model,
                            reason_msg,
                            fallback_model,
                        )
                        fallback_candidates = pool.get_candidate_accounts(fallback_model) if pool else candidates
                        for fb_acc in fallback_candidates:
                            fb_label = getattr(fb_acc, "email", fb_acc.account_id)
                            logger.info("[%s] %s active (Antigravity CloudCode - Fallback from %s)", fb_label, fallback_model, req_model)
                            fb_body = copy.deepcopy(candidate_body) if isinstance(candidate_body, dict) else candidate_body
                            if isinstance(fb_body, dict):
                                fb_body["model"] = fallback_model
                                if "request" in fb_body and isinstance(fb_body["request"], dict):
                                    fb_body["request"]["model"] = fallback_model
                                    if "thinkingConfig" in fb_body["request"] and isinstance(fb_body["request"]["thinkingConfig"], dict):
                                        fb_body["request"]["thinkingConfig"].pop("thinkingLevel", None)
                                fb_proj = getattr(fb_acc, "project_id", None) or "aicode-consumers"
                                fb_body["project"] = fb_proj
                                if "request" in fb_body and isinstance(fb_body["request"], dict):
                                    fb_body["request"]["project"] = fb_proj
                            try:
                                fb_headers = await fb_acc.get_auth_headers()
                                if "user-agent" in request.headers:
                                    fb_headers["User-Agent"] = request.headers["user-agent"]
                                fb_c = await fb_acc.get_http_client()
                                fb_resp = await fb_c.post(target_url, headers=fb_headers, json=fb_body, params=query_params, timeout=timeout_sec)
                                if fb_resp.status_code == 200:
                                    logger.info("[%s] ✅ Fallback to %s succeeded! Generation continuing seamlessly.", fb_label, fallback_model)
                                    resp = fb_resp
                                    acc = fb_acc
                                    acc_label = fb_label
                                    req_model = fallback_model
                                    break
                            except Exception as fb_err:
                                logger.debug("[%s] Fallback attempt to %s error: %s", fb_label, fallback_model, fb_err)
                                continue

                    elif req_model != DEFAULT_MODEL:
                        logger.warning("[%s] Model %s returned 404. Attempting automatic fallback to %s...", acc_label, req_model, DEFAULT_MODEL)
                        fallback_body = copy.deepcopy(candidate_body)
                        if isinstance(fallback_body, dict):
                            fallback_body["model"] = DEFAULT_MODEL
                            if "request" in fallback_body and isinstance(fallback_body["request"], dict):
                                fallback_body["request"]["model"] = DEFAULT_MODEL
                        try:
                            fb_resp = await c.post(target_url, headers=headers, json=fallback_body, params=query_params, timeout=timeout_sec)
                            if fb_resp.status_code == 200:
                                resp = fb_resp
                        except Exception:
                            pass

                if resp.status_code >= 400:
                    err_summary = _extract_error_message(resp)
                    logger.error("[%s] CloudCode Error %d: %s", acc_label, resp.status_code, err_summary)
                    logger.debug("[%s] CloudCode raw error response: %s", acc_label, resp.text)

                # Success tracking
                if resp.status_code == 200 and is_generation:
                    acc.total_requests = getattr(acc, "total_requests", 0) + 1
                    acc.last_used_timestamp = time.time()
                    acc.last_used_model = req_model

                try:
                    data = resp.json()
                    # Cache successful metadata responses
                    if resp.status_code == 200 and is_metadata and isinstance(data, dict) and data:
                        _PASSTHROUGH_METADATA_CACHE[action_key] = data
                        _save_passthrough_cache()

                    data = _process_passthrough_metadata(action_key, data)
                    return JSONResponse(status_code=resp.status_code, content=data)
                except Exception:
                    return Response(
                        content=resp.content,
                        status_code=resp.status_code,
                        media_type=resp.headers.get("content-type", "application/json"),
                    )

            except Exception as e:
                last_error = str(e)
                if not is_generation and is_metadata:
                    logger.debug("[%s] CloudCode metadata passthrough error (%s): %s", acc_label, route_desc, e)
                else:
                    logger.warning("[%s] CloudCode passthrough error (%s): %s", acc_label, route_desc, e)
                is_net_error = isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout, socket.gaierror, OSError))

                # If non-generation metadata call hit network failure, serve cached metadata immediately
                if not is_generation and is_metadata and is_net_error:
                    logger.debug("[%s] Network unreachable for %s. Serving cached metadata immediately.", acc_label, route_desc)
                    cached_data = _get_cached_or_default_passthrough(action_key)
                    cached_data = _process_passthrough_metadata(action_key, cached_data)
                    return JSONResponse(status_code=200, content=cached_data)

                # If generation hit transient network error on last account, try one brief retry
                if is_generation and is_last and is_net_error:
                    try:
                        await asyncio.sleep(1.0)
                        fb_resp = await c.post(target_url, headers=headers, json=candidate_body, params=query_params, timeout=timeout_sec)
                        if fb_resp.status_code == 200:
                            return JSONResponse(status_code=200, content=fb_resp.json())
                    except Exception:
                        pass

                if not is_last:
                    continue

        # All candidates failed
        if not is_generation and is_metadata:
            logger.debug("All candidates failed for %s. Serving cached metadata.", route_desc)
            cached_data = _get_cached_or_default_passthrough(action_key)
            cached_data = _process_passthrough_metadata(action_key, cached_data)
            return JSONResponse(status_code=200, content=cached_data)

        if is_generation:
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": 503,
                        "message": f"CloudCode upstream generation failed across all accounts ({last_error})",
                        "status": "UNAVAILABLE",
                    }
                },
            )

        return JSONResponse(status_code=200, content={})

    return app
