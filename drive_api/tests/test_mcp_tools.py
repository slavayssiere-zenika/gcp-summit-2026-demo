"""
Tests de contrat MCP (AGENTS.md §8) — drive_api
Vérifie que chaque tool MCP retourne une réponse structurée valide.
"""
import os
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("SECRET_KEY", "test-secret")
os.environ.setdefault("DRIVE_API_URL", "http://localhost:8006")

from mcp_server import call_tool, list_tools, mcp_auth_header_var


# ── Helpers ──────────────────────────────────────────────────────────────────

def _text(result: list) -> str:
    """Extrait le texte du premier TextContent retourné par un tool."""
    assert len(result) == 1, f"Expected 1 TextContent, got {len(result)}"
    assert result[0].type == "text"
    return result[0].text


def _json(result: list) -> dict | list:
    """Parse le JSON du résultat d'un tool."""
    return json.loads(_text(result))


def make_mock_response(status_code: int = 200, json_data: dict | list = None) -> MagicMock:
    """Crée un mock httpx.Response."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data or {}
    mock_resp.text = json.dumps(json_data or {})
    mock_resp.raise_for_status = MagicMock()
    return mock_resp


# ── Tests list_tools ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_tools_returns_all_expected():
    """Vérifie que tous les tools attendus sont enregistrés."""
    tools = await list_tools()
    tool_names = {t.name for t in tools}
    expected = {
        "add_drive_folder",
        "list_drive_folders",
        "delete_drive_folder",
        "get_drive_status",
        "list_drive_files",
        "retry_drive_errors",
        "trigger_drive_sync",
        "get_drive_file_state",
        "reset_drive_folder_sync",
        "get_dlq_status",
        "delete_dlq_message",
        "replay_dlq",
        "update_drive_file",
    }
    assert expected == tool_names, f"Tools manquants ou en trop : {expected.symmetric_difference(tool_names)}"


# ── Tests call_tool ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_drive_folder_success():
    """add_drive_folder — retourne un objet JSON valide sur succès."""
    payload = {"google_folder_id": "abc123", "tag": "Paris", "id": 1}
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, payload)
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await call_tool("add_drive_folder", {"google_folder_id": "abc123", "tag": "Paris"})
    data = _json(result)
    assert data["google_folder_id"] == "abc123"


@pytest.mark.asyncio
async def test_list_drive_folders_success():
    """list_drive_folders — retourne une liste JSON."""
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, [{"id": 1, "tag": "Lyon"}])
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await call_tool("list_drive_folders", {})
    data = _json(result)
    assert isinstance(data, list)
    assert data[0]["tag"] == "Lyon"


@pytest.mark.asyncio
async def test_delete_drive_folder_success():
    """delete_drive_folder — retourne success avec confirmation."""
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, {"status": "deleted"})
        MockClient.return_value.__aenter__.return_value.delete = AsyncMock(return_value=mock_resp)
        result = await call_tool("delete_drive_folder", {"folder_id": 1})
    data = _json(result)
    assert data["status"] == "deleted"


@pytest.mark.asyncio
async def test_get_drive_status_success():
    """get_drive_status — retourne les stats d'ingestion."""
    stats = {"total_files_scanned": 10, "pending": 2, "imported": 7, "errors": 1}
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, stats)
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await call_tool("get_drive_status", {})
    data = _json(result)
    assert "total_files_scanned" in data


@pytest.mark.asyncio
async def test_list_drive_files_success():
    """list_drive_files — retourne une liste de fichiers."""
    files = [{"google_file_id": "file1", "status": "IMPORTED_CV"}]
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, files)
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await call_tool("list_drive_files", {})
    data = _json(result)
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_retry_drive_errors_success():
    """retry_drive_errors — retourne le nombre de fichiers remis en queue."""
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, {"errors_reset": 3, "zombies_reset": 1})
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await call_tool("retry_drive_errors", {})
    data = _json(result)
    assert "errors_reset" in data


@pytest.mark.asyncio
async def test_trigger_drive_sync_success():
    """trigger_drive_sync — retourne status started."""
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, {"status": "started"})
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await call_tool("trigger_drive_sync", {})
    data = _json(result)
    assert data["status"] == "started"


@pytest.mark.asyncio
async def test_get_drive_file_state_success():
    """get_drive_file_state — retourne l'état d'un fichier Drive."""
    state = {"google_file_id": "file1", "status": "IMPORTED_CV", "parent_folder_name": "Marie Dupont"}
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, state)
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await call_tool("get_drive_file_state", {"google_file_id": "file1"})
    data = _json(result)
    assert data["google_file_id"] == "file1"


@pytest.mark.asyncio
async def test_get_drive_file_state_missing_param():
    """get_drive_file_state — retourne success=False si google_file_id absent."""
    result = await call_tool("get_drive_file_state", {})
    data = _json(result)
    assert data["success"] is False
    assert "google_file_id" in data["error"]


@pytest.mark.asyncio
async def test_reset_drive_folder_sync_success():
    """reset_drive_folder_sync — retourne les rows mises à jour."""
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, {"status": "success", "rows_updated": 5})
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await call_tool("reset_drive_folder_sync", {"tag": "Paris"})
    data = _json(result)
    assert data["rows_updated"] == 5


@pytest.mark.asyncio
async def test_get_dlq_status_success():
    """get_dlq_status — retourne l'état de la DLQ."""
    dlq = {"message_count": 2, "files": [], "unknown_files": []}
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, dlq)
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await call_tool("get_dlq_status", {})
    data = _json(result)
    assert "message_count" in data


@pytest.mark.asyncio
async def test_delete_dlq_message_missing_params():
    """delete_dlq_message — retourne success=False si aucun paramètre fourni."""
    result = await call_tool("delete_dlq_message", {})
    data = _json(result)
    assert data["success"] is False


@pytest.mark.asyncio
async def test_replay_dlq_success():
    """replay_dlq — retourne le nombre de fichiers rejoués."""
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, {"files_reset_to_pending": 4, "dlq_messages_pulled": 4})
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await call_tool("replay_dlq", {})
    data = _json(result)
    assert "files_reset_to_pending" in data


@pytest.mark.asyncio
async def test_update_drive_file_success():
    """update_drive_file — retourne le fichier mis à jour."""
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = make_mock_response(200, {"google_file_id": "file1", "status": "PENDING"})
        MockClient.return_value.__aenter__.return_value.patch = AsyncMock(return_value=mock_resp)
        result = await call_tool("update_drive_file", {"file_id": "file1", "status": "PENDING"})
    data = _json(result)
    assert data["google_file_id"] == "file1"


@pytest.mark.asyncio
async def test_update_drive_file_missing_file_id():
    """update_drive_file — retourne success=False si file_id absent."""
    result = await call_tool("update_drive_file", {})
    data = _json(result)
    assert data["success"] is False
    assert "file_id" in data["error"]


@pytest.mark.asyncio
async def test_unknown_tool():
    """Un tool inconnu retourne un message d'erreur explicite (pas d'exception)."""
    result = await call_tool("tool_inexistant", {})
    text = _text(result)
    assert "Unknown tool" in text


@pytest.mark.asyncio
async def test_api_error_returns_structured_error():
    """Une erreur API HTTP retourne success=False avec le code d'erreur, pas une exception."""
    import httpx
    with patch("mcp_server.httpx.AsyncClient") as MockClient:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500 Server Error", request=MagicMock(), response=mock_resp
        )
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await call_tool("get_drive_status", {})
    data = _json(result)
    assert data["success"] is False
    assert "500" in data["error"]
