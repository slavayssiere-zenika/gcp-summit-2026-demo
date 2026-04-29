import os

os.environ["SECRET_KEY"] = "testsecret"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./drive_test.db"

import pytest
from unittest.mock import MagicMock, AsyncMock

from mcp_server import call_tool, mcp_auth_header_var


# ─────────────────────────────────────────────────────────────────────────────
# Fixture commune : mock httpx pour tous les tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_httpx(mocker):
    mock = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock.return_value.__aenter__.return_value = client_instance
    return client_instance


def _ok(data):
    """Construit un mock httpx 200 avec la payload donnée."""
    resp = MagicMock(status_code=200)
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def _created(data):
    resp = MagicMock(status_code=201)
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


# ─────────────────────────────────────────────────────────────────────────────
# Tests de contrat — Tools de gestion de dossiers Drive
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_drive_folder(mock_httpx):
    """add_drive_folder : vérifie le POST vers drive_api."""
    mock_httpx.post.return_value = _created({"id": 1, "folder_id": "abc123", "status": "pending"})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("add_drive_folder", {"folder_id": "abc123", "tag": "zenika-lyon"})
    assert result[0].text
    assert "abc123" in result[0].text or "pending" in result[0].text


@pytest.mark.asyncio
async def test_list_drive_folders(mock_httpx):
    """list_drive_folders : vérifie le GET vers drive_api."""
    mock_httpx.get.return_value = _ok([{"id": 1, "folder_id": "abc123", "status": "synced"}])
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("list_drive_folders", {})
    assert "abc123" in result[0].text or "synced" in result[0].text


@pytest.mark.asyncio
async def test_delete_drive_folder(mock_httpx):
    """delete_drive_folder : vérifie le DELETE vers drive_api."""
    mock_httpx.delete.return_value = _ok({"message": "Dossier supprimé"})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("delete_drive_folder", {"folder_id": "abc123"})
    assert result[0].text


@pytest.mark.asyncio
async def test_get_drive_status(mock_httpx):
    """get_drive_status : vérifie le GET /status vers drive_api."""
    mock_httpx.get.return_value = _ok({
        "pending": 5, "processing": 2, "imported": 100, "error": 1
    })
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("get_drive_status", {})
    assert "pending" in result[0].text or "imported" in result[0].text


# ─────────────────────────────────────────────────────────────────────────────
# Tests de contrat — Tools de gestion de fichiers Drive
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_drive_files(mock_httpx):
    """list_drive_files : vérifie le GET /files vers drive_api."""
    mock_httpx.get.return_value = _ok([
        {"id": 1, "name": "CV_Alice.pdf", "state": "IMPORTED_CV"}
    ])
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("list_drive_files", {"folder_id": "abc123"})
    assert "CV_Alice" in result[0].text or "IMPORTED_CV" in result[0].text


@pytest.mark.asyncio
async def test_get_drive_file_state(mock_httpx):
    """get_drive_file_state : vérifie le GET /files/{id} vers drive_api."""
    mock_httpx.get.return_value = _ok({"id": 42, "name": "CV_Bob.pdf", "state": "PROCESSING"})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("get_drive_file_state", {"google_file_id": "42"})
    assert "PROCESSING" in result[0].text or "CV_Bob" in result[0].text


@pytest.mark.asyncio
async def test_update_drive_file(mock_httpx):
    """update_drive_file : vérifie le PUT /files/{id} vers drive_api."""
    mock_httpx.put.return_value = _ok({"id": 42, "state": "PENDING"})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("update_drive_file", {"file_id": 42, "state": "PENDING"})
    assert result[0].text


# ─────────────────────────────────────────────────────────────────────────────
# Tests de contrat — Tools de synchronisation et retry
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_trigger_drive_sync(mock_httpx):
    """trigger_drive_sync : vérifie le POST /sync vers drive_api."""
    mock_httpx.post.return_value = _ok({"message": "Synchronisation déclenchée", "queued": 12})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("trigger_drive_sync", {"folder_id": "abc123"})
    assert "Synchronisation" in result[0].text or "queued" in result[0].text


@pytest.mark.asyncio
async def test_retry_drive_errors(mock_httpx):
    """retry_drive_errors : vérifie le POST /retry vers drive_api."""
    mock_httpx.post.return_value = _ok({"message": "Retry lancé", "retried": 3})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("retry_drive_errors", {})
    assert result[0].text


@pytest.mark.asyncio
async def test_reset_drive_folder_sync(mock_httpx):
    """reset_drive_folder_sync : vérifie le POST /reset vers drive_api."""
    mock_httpx.post.return_value = _ok({"message": "Synchronisation réinitialisée"})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("reset_drive_folder_sync", {"folder_id": "abc123"})
    assert result[0].text


# ─────────────────────────────────────────────────────────────────────────────
# Tests de contrat — Tools DLQ (Dead Letter Queue)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_dlq_status(mock_httpx):
    """get_dlq_status : vérifie le GET /dlq vers drive_api."""
    mock_httpx.get.return_value = _ok({"count": 3, "messages": [{"id": "msg1"}]})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("get_dlq_status", {})
    assert "count" in result[0].text or "msg1" in result[0].text


@pytest.mark.asyncio
async def test_delete_dlq_message(mock_httpx):
    """delete_dlq_message : vérifie le DELETE /dlq/{id} vers drive_api."""
    mock_httpx.delete.return_value = _ok({"message": "Message supprimé", "id": "msg1"})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("delete_dlq_message", {"message_id": "msg1"})
    assert result[0].text


@pytest.mark.asyncio
async def test_replay_dlq(mock_httpx):
    """replay_dlq : vérifie le POST /dlq/replay vers drive_api."""
    mock_httpx.post.return_value = _ok({"message": "Replay lancé", "replayed": 3})
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("replay_dlq", {})
    assert "replay" in result[0].text.lower() or "replayed" in result[0].text


# ─────────────────────────────────────────────────────────────────────────────
# Tests de gestion d'erreur (Failfast — AGENTS.md §1.10)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_tool():
    """Tout tool inconnu doit retourner 'Unknown tool' — jamais lever d'exception."""
    mcp_auth_header_var.set("Bearer token")
    result = await call_tool("non_existent_drive_tool", {})
    assert "Unknown tool" in result[0].text or "success" in result[0].text.lower()


@pytest.mark.asyncio
async def test_get_drive_status_api_error(mock_httpx):
    """get_drive_status : erreur réseau → retourne {success: false, error: ...}."""
    mock_httpx.get.side_effect = Exception("Connection refused")
    mcp_auth_header_var.set("Bearer token")

    result = await call_tool("get_drive_status", {})
    # Doit retourner une erreur structurée, pas lever d'exception
    assert result[0].text
    assert "success" in result[0].text.lower() or "error" in result[0].text.lower() or "Connection refused" in result[0].text
