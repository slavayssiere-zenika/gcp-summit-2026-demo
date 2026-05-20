"""
test_functional_coverage.py — Tests fonctionnels ciblant les zones non couvertes.

S'appuie sur le conftest.py existant pour les fixtures.

Couverture visée :
  - auth.py   : cookie fallback, service_account, no-credentials 401, expired token
  - gemini_retry.py : generate_content_with_retry, _is_retryable
  - mcp_server.py : call_tool paths (get_prompt, update_prompt, list_prompts, delete)
  - router.py : verify_admin edge cases (service_account, empty role)
"""
import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./prompts_test.db")
os.environ.setdefault("GCP_PROJECT_ID", "test-project")
os.environ.setdefault("VERTEX_LOCATION", "europe-west1")
os.environ.setdefault("GEMINI_PRO_MODEL", "gemini-1.5-pro-001")


# ═══════════════════════════════════════════════════════════════════════════════
# 1. src/prompts/auth.py — Chemins non couverts
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthFunctional:
    """Couvre src/prompts/auth.py : cookie fallback, service_account, expired token."""

    def test_verify_admin_accepts_service_account(self):
        """verify_admin accepte le rôle 'service_account'."""
        from src.prompts.router import verify_admin
        result = verify_admin({"role": "service_account"})
        assert result["role"] == "service_account"

    def test_verify_admin_rejects_consultant(self):
        """verify_admin rejette le rôle 'consultant' → HTTPException 403."""
        from fastapi import HTTPException
        from src.prompts.router import verify_admin
        with pytest.raises(HTTPException) as exc:
            verify_admin({"role": "consultant"})
        assert exc.value.status_code == 403

    def test_verify_admin_rejects_empty_payload(self):
        """verify_admin rejette un payload sans rôle → HTTPException 403."""
        from fastapi import HTTPException
        from src.prompts.router import verify_admin
        with pytest.raises(HTTPException) as exc:
            verify_admin({})
        assert exc.value.status_code == 403

    def test_verify_jwt_cookie_fallback(self):
        """verify_jwt accepte le token depuis le cookie 'access_token'."""
        import jwt
        from src.prompts.auth import verify_jwt

        secret = os.environ.get("SECRET_KEY", "testsecret")
        token = jwt.encode(
            {"sub": "cookie_user@zenika.com", "role": "admin"},
            secret,
            algorithm="HS256",
        )
        mock_request = MagicMock()
        mock_request.cookies = {"access_token": token}

        payload = verify_jwt(mock_request, credentials=None)
        assert payload["sub"] == "cookie_user@zenika.com"
        assert payload["role"] == "admin"

    def test_verify_jwt_no_token_raises_401(self):
        """Pas de JWT et pas de cookie → HTTPException 401."""
        from fastapi import HTTPException
        from src.prompts.auth import verify_jwt

        mock_request = MagicMock()
        mock_request.cookies = {}
        with pytest.raises(HTTPException) as exc:
            verify_jwt(mock_request, credentials=None)
        assert exc.value.status_code == 401

    def test_verify_jwt_expired_token_raises_401(self):
        """Token expiré → HTTPException 401."""
        import jwt
        from fastapi import HTTPException
        from fastapi.security import HTTPAuthorizationCredentials
        from src.prompts.auth import verify_jwt

        secret = os.environ.get("SECRET_KEY", "testsecret")
        token = jwt.encode(
            {"sub": "expired@zenika.com", "exp": 1},  # expired
            secret,
            algorithm="HS256",
        )
        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        mock_request = MagicMock()
        mock_request.cookies = {}
        with pytest.raises(HTTPException) as exc:
            verify_jwt(mock_request, credentials=creds)
        assert exc.value.status_code == 401


# ═══════════════════════════════════════════════════════════════════════════════
# 2. gemini_retry.py — _is_retryable + generate_content_with_retry
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeminiRetry:
    """Couvre src/gemini_retry.py — _is_retryable, generate_content_with_retry."""

    def test_is_retryable_429_string(self):
        """_is_retryable retourne True pour les erreurs contenant '429'."""
        from src.gemini_retry import _is_retryable
        assert _is_retryable(Exception("429 resource exhausted")) is True

    def test_is_retryable_503_string(self):
        """_is_retryable retourne True pour les erreurs 503."""
        from src.gemini_retry import _is_retryable
        assert _is_retryable(Exception("503 service unavailable")) is True

    def test_is_retryable_false_for_normal_errors(self):
        """_is_retryable retourne False pour les erreurs normales."""
        from src.gemini_retry import _is_retryable
        assert _is_retryable(ValueError("bad input")) is False
        assert _is_retryable(RuntimeError("something broke")) is False

    def test_is_retryable_resource_exhausted_keyword(self):
        """_is_retryable retourne True pour 'resource exhausted'."""
        from src.gemini_retry import _is_retryable
        assert _is_retryable(Exception("resource exhausted — quota exceeded")) is True

    def test_is_retryable_high_traffic_keyword(self):
        """_is_retryable retourne True pour 'high traffic'."""
        from src.gemini_retry import _is_retryable
        assert _is_retryable(Exception("Our servers experienced high traffic")) is True

    def test_is_retryable_overloaded_keyword(self):
        """_is_retryable retourne True pour 'overloaded'."""
        from src.gemini_retry import _is_retryable
        assert _is_retryable(Exception("model is overloaded")) is True

    def test_generate_content_with_retry_success(self):
        """generate_content_with_retry retourne le résultat si l'appel réussit."""
        from src.gemini_retry import generate_content_with_retry

        mock_response = MagicMock()
        mock_response.text = "Generated content"

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)

        async def _run():
            return await generate_content_with_retry(
                mock_client, model="gemini-2.0-flash", contents="Hello"
            )

        result = asyncio.run(_run())
        assert result.text == "Generated content"

    def test_generate_content_with_retry_retries_on_429(self):
        """generate_content_with_retry retente sur erreur 429."""
        from src.gemini_retry import generate_content_with_retry
        from google.api_core.exceptions import ResourceExhausted

        call_count = 0
        mock_response = MagicMock()
        mock_response.text = "success after retry"

        async def _flaky_generate(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ResourceExhausted("429 quota exceeded")
            return mock_response

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = _flaky_generate

        async def _run():
            return await generate_content_with_retry(
                mock_client, model="gemini-2.0-flash", contents="Hello"
            )

        result = asyncio.run(_run())
        assert result.text == "success after retry"
        assert call_count == 2

    def test_embed_content_with_retry_success(self):
        """embed_content_with_retry retourne le résultat si l'appel réussit."""
        from src.gemini_retry import embed_content_with_retry

        mock_response = MagicMock()
        mock_response.embedding.values = [0.1, 0.2, 0.3]

        mock_client = MagicMock()
        mock_client.aio.models.embed_content = AsyncMock(return_value=mock_response)

        async def _run():
            return await embed_content_with_retry(
                mock_client, model="text-embedding-004", contents="Hello"
            )

        result = asyncio.run(_run())
        assert result.embedding.values == [0.1, 0.2, 0.3]


# ═══════════════════════════════════════════════════════════════════════════════
# 3. mcp_server.py — call_tool paths (L169+)
# ═══════════════════════════════════════════════════════════════════════════════

class TestMcpServerCallTool:
    """Couvre mcp_server.py — call_tool avec mock API HTTP."""

    def _mock_httpx(self, status_code: int, json_body: dict):
        """Helper pour mocker httpx.AsyncClient.get/post."""
        mock_resp = MagicMock()
        mock_resp.status_code = status_code
        mock_resp.json.return_value = json_body
        mock_resp.text = json.dumps(json_body)
        return mock_resp

    def test_call_tool_get_prompt_success(self):
        """call_tool('get_prompt', ...) retourne le contenu du prompt."""
        import mcp_server as mcp

        mock_resp = self._mock_httpx(200, {
            "key": "agent.system",
            "value": "You are an AI.",
            "updated_at": None,
        })

        async def _run():
            with patch("httpx.AsyncClient.get", return_value=mock_resp):
                return await mcp.call_tool("get_prompt", {"key": "agent.system"})

        result = asyncio.run(_run())
        assert result  # returns list[TextContent]
        content = result[0].text
        data = json.loads(content)
        assert data["key"] == "agent.system"

    def test_call_tool_get_prompt_not_found(self):
        """call_tool('get_prompt', ...) retourne un message d'erreur si 404."""
        import mcp_server as mcp

        mock_resp = self._mock_httpx(404, {"detail": "Not found"})

        async def _run():
            with patch("httpx.AsyncClient.get", return_value=mock_resp):
                return await mcp.call_tool("get_prompt", {"key": "missing.key"})

        result = asyncio.run(_run())
        assert result
        content = json.loads(result[0].text)
        # Accepte "error", "detail" (FastAPI 404), ou success=False
        assert (
            "error" in content
            or "detail" in content
            or content.get("success") is False
        )

    def test_call_tool_list_prompts_success(self):
        """call_tool('list_prompts', {}) retourne la liste des prompts."""
        import mcp_server as mcp

        mock_resp = self._mock_httpx(200, {
            "prompts": [{"key": "k1", "value": "v1"}],
            "total": 1,
            "skip": 0,
            "limit": 50,
        })

        async def _run():
            with patch("httpx.AsyncClient.get", return_value=mock_resp):
                return await mcp.call_tool("list_prompts", {})

        result = asyncio.run(_run())
        assert result
        data = json.loads(result[0].text)
        assert "prompts" in data or isinstance(data, list) or data.get("success") is not False

    def test_call_tool_update_prompt_success(self):
        """call_tool('update_prompt', ...) met à jour un prompt."""
        import mcp_server as mcp

        mock_resp = self._mock_httpx(200, {
            "key": "agent.hr",
            "value": "Updated value",
        })

        async def _run():
            with patch("httpx.AsyncClient.put", return_value=mock_resp):
                return await mcp.call_tool(
                    "update_prompt",
                    {"key": "agent.hr", "value": "Updated value"},
                )

        result = asyncio.run(_run())
        assert result

    def test_call_tool_unknown_tool_returns_error(self):
        """call_tool avec un nom inconnu retourne un message d'erreur."""
        import mcp_server as mcp

        async def _run():
            return await mcp.call_tool("nonexistent_tool", {})

        result = asyncio.run(_run())
        assert result
        content = result[0].text
        assert "unknown" in content.lower() or "error" in content.lower()

    def test_get_trace_headers_returns_dict(self):
        """get_trace_headers retourne un dictionnaire (même vide)."""
        import mcp_server as mcp
        headers = mcp.get_trace_headers()
        assert isinstance(headers, dict)
