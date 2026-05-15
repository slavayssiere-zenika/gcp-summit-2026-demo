import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
from main import app, seed_admin, get_service_token_fallback, report_exception_to_prompts_api, proxy_mcp_fallback
from unittest.mock import patch, AsyncMock, MagicMock
import os
from fastapi import Request

client = TestClient(app)

def test_get_spec():
    resp = client.get("/spec")
    assert resp.status_code in [200, 404]

def test_proxy_mcp():
    with patch("main.httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"success"
        mock_resp.headers = {"content-type": "text/plain"}
        mock_req.return_value = mock_resp
        
        resp = client.post("/mcp/test-tool", json={"arg": 1})
        assert resp.status_code == 200
        assert resp.content == b"success"

@pytest.mark.asyncio
async def test_proxy_mcp_fallback():
    with patch("main.httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fallback"
        mock_resp.headers = {"content-type": "text/plain"}
        mock_req.return_value = mock_resp
        
        req = MagicMock()
        req.method = "POST"
        req.url.query = ""
        req.headers = {}
        req.body = AsyncMock(return_value=b"body")
        
        resp = await proxy_mcp_fallback("test-tool", req)
        assert resp.status_code == 200

def test_proxy_mcp_error():
    with patch("main.httpx.AsyncClient.request", new_callable=AsyncMock) as mock_req:
        mock_req.side_effect = Exception("Proxy Error")
        
        resp = client.post("/mcp/test-tool", json={"arg": 1})
        assert resp.status_code == 502
        assert b"Proxy Error" in resp.content

@pytest.mark.asyncio
async def test_get_service_token_fallback():
    with patch.dict(os.environ, {"DEV_SERVICE_TOKEN": "dev-token-123"}):
        token = await get_service_token_fallback()
        assert token == "dev-token-123"

@pytest.mark.asyncio
async def test_report_exception_to_prompts_api():
    with patch("main.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = MagicMock(status_code=200)
        await report_exception_to_prompts_api("test_service", "error message", "trace context", "test-token")
        mock_post.assert_called_once()

@pytest.mark.asyncio
async def test_global_exception_handler():
    """Le handler global retourne 500 pour toute exception non-HTTP."""
    # La closure est enregistrée via register_global_exception_handler(app)
    # On la récupère depuis le registre interne FastAPI
    handler = app.exception_handlers.get(Exception)
    assert handler is not None, "global_exception_handler non enregistré sur app"

    req = MagicMock(spec=Request)
    req.method = "GET"
    req.url.path = "/test"
    req.headers = {}

    with patch("shared.exception_handler._report_to_prompts_api", new_callable=AsyncMock):
        resp = await handler(req, Exception("Boom"))
        assert resp.status_code == 500

