import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app

client = TestClient(app)


class TestHealth:
    def test_health(self):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


class TestRoot:
    def test_root_returns_html(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


class TestQueryEndpoint:
    @patch('main.get_users_mcp')
    def test_query_list_users(self, mock_get_users_mcp):
        mock_client = MagicMock()
        mock_client.call_tool.return_value = [
            {"type": "text", "text": '{"items": [{"id": 1, "username": "testuser", "email": "test@example.com", "full_name": "Test User", "is_active": true}], "total": 1, "skip": 0, "limit": 10}'}
        ]
        mock_get_users_mcp.return_value = mock_client

        response = client.post("/query", json={"query": "affiche les utilisateurs"})
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "users_api"
        assert "response" in data
        assert data["response"]["total"] == 1

    @patch('main.get_users_mcp')
    def test_query_search_user(self, mock_get_users_mcp):
        mock_client = MagicMock()
        mock_client.call_tool.return_value = [
            {"type": "text", "text": '{"items": [{"id": 1, "username": "john", "email": "john@example.com", "full_name": "John Doe", "is_active": true}], "total": 1, "skip": 0, "limit": 100}'}
        ]
        mock_get_users_mcp.return_value = mock_client

        response = client.post("/query", json={"query": "cherche l'utilisateur nommé john"})
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "users_api"
        assert data["search"] == "john"
        assert data["response"]["total"] == 1

    @patch('main.get_items_mcp')
    def test_query_list_items(self, mock_get_items_mcp):
        mock_client = MagicMock()
        mock_client.call_tool.return_value = [
            {"type": "text", "text": '{"items": [{"id": 1, "name": "Test Item", "user_id": 1}], "total": 1}'}
        ]
        mock_get_items_mcp.return_value = mock_client

        response = client.post("/query", json={"query": "montre les items"})
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "items_api"

    def test_query_help(self):
        response = client.post("/query", json={"query": "bonjour"})
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "help"
        assert "items" in data["response"]

    def test_query_empty_query(self):
        response = client.post("/query", json={"query": ""})
        assert response.status_code == 200

    @patch('main.get_users_mcp')
    def test_query_mcp_error(self, mock_get_users_mcp):
        mock_get_users_mcp.side_effect = Exception("MCP connection failed")

        response = client.post("/query", json={"query": "affiche les utilisateurs"})
        assert response.status_code == 200
        data = response.json()
        assert data["source"] == "error"
        assert "Erreur MCP" in data["response"]


class TestQueryValidation:
    def test_query_requires_query_field(self):
        response = client.post("/query", json={})
        assert response.status_code == 422


class TestMCPClient:
    def test_mcp_client_initialization(self):
        from mcp_client import MCPStdioClient
        
        with patch('subprocess.Popen') as mock_popen:
            mock_popen.return_value.stdout.readline.return_value = '{"jsonrpc": "2.0", "id": 0, "result": {}}'
            
            client = MCPStdioClient(command="python", args=["-m", "test"])
            assert client.command == "python"
            assert client.args == ["-m", "test"]
            client.stop()
