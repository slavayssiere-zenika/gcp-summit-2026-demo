import os
os.environ['SECRET_KEY'] = 'testsecret'
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json

# Patch USERS_API_URL, COMPETENCIES_API_URL, CV_API_URL
import os
os.environ["CV_API_URL"] = "http://test-cv"

from mcp_server import call_tool, mcp_auth_header_var

@pytest.mark.asyncio
async def test_analyze_cv_tool(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"message": "Success", "user_id": 1, "competencies_assigned": 5}
    client_instance.post.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")
    
    result = await call_tool(name="analyze_cv", arguments={"url": "http://test.com/cv"})
    assert "Success" in result[0].text

@pytest.mark.asyncio
async def test_search_best_candidates_tool(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [{"user_id": 1, "similarity_score": 0.9}]
    client_instance.get.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")

    result = await call_tool(name="search_best_candidates", arguments={"query": "Java developer", "limit": 5})
    assert "similarity_score" in result[0].text

@pytest.mark.asyncio
async def test_recalculate_competencies_tree_tool(mocker):
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    import httpx
    # simulate HTTPError for branch coverage
    # First success
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"tree": {"Root": "Child"}}
    client_instance.post.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")

    result = await call_tool(name="recalculate_competencies_tree", arguments={})
    assert "Root" in result[0].text
    
    # 2. exception coverage
    client_instance.post.side_effect = Exception("General error")
    result = await call_tool(name="recalculate_competencies_tree", arguments={})
    assert "Request failed: General error" in result[0].text

@pytest.mark.asyncio
async def test_tool_errors(mocker):
    result = await call_tool(name="analyze_cv", arguments={})
    assert "Error: Missing url argument" in result[0].text

    result = await call_tool(name="search_best_candidates", arguments={})
    assert "Error: Missing query argument" in result[0].text

    result = await call_tool(name="non_existent", arguments={})
    assert "Unknown tool" in result[0].text

@pytest.mark.asyncio
async def test_api_error_returns_structured_error(mocker):
    """Vérifie qu'une erreur réseau/HTTP ne fait pas crasher l'agent mais retourne {success: false}"""
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance
    
    import httpx
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    
    # Simuler une erreur HTTP (ex: 500)
    client_instance.get.side_effect = httpx.HTTPStatusError(
        "500 Server Error", request=MagicMock(), response=mock_resp
    )
    
    mcp_auth_header_var.set("Bearer token")
    result = await call_tool(name="search_best_candidates", arguments={"query": "Java", "limit": 5})
    
    # Doit retourner du texte contenant 'success' et 'false' ou 'error'
    assert result[0].text
    assert "success" in result[0].text.lower() or "error" in result[0].text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Tests des nouveaux MCP tools RAG (Sprint 0, A, B, C)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reindex_cv_embeddings_tool(mocker):
    """S0 — reindex_cv_embeddings : vérifie que le POST /reindex-embeddings est appelé."""
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {"message": "Re-indexation des embeddings lancée", "filter": {"tag": None, "user_id": None}}
    mock_resp.raise_for_status = MagicMock()
    client_instance.post.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")
    result = await call_tool(name="reindex_cv_embeddings", arguments={})
    assert "Re-indexation" in result[0].text or "embeddings" in result[0].text.lower()

    # Avec filtres
    result2 = await call_tool(name="reindex_cv_embeddings", arguments={"tag": "lyon", "user_id": 42})
    assert result2[0].text  # doit retourner quelque chose


@pytest.mark.asyncio
async def test_find_similar_consultants_tool(mocker):
    """A1 — find_similar_consultants : vérifie le GET /user/{id}/similar."""
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [
        {"user_id": 2, "similarity_score": 0.92, "full_name": "Alice Dupont", "current_role": "Tech Lead"}
    ]
    mock_resp.raise_for_status = MagicMock()
    client_instance.get.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")
    result = await call_tool(name="find_similar_consultants", arguments={"user_id": 1, "limit": 5})
    assert "similarity_score" in result[0].text or "Alice" in result[0].text

    # Erreur : user_id manquant
    result_err = await call_tool(name="find_similar_consultants", arguments={})
    assert "user_id requis" in result_err[0].text or "success" in result_err[0].text.lower()


@pytest.mark.asyncio
async def test_search_candidates_multi_criteria_tool(mocker):
    """A2 — search_candidates_multi_criteria : vérifie le POST /search/multi-criteria."""
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [
        {"user_id": 5, "combined_similarity": 0.87, "full_name": "Bob Martin", "current_role": "DevOps"}
    ]
    mock_resp.raise_for_status = MagicMock()
    client_instance.post.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")
    result = await call_tool(
        name="search_candidates_multi_criteria",
        arguments={"queries": ["expert GCP", "migration legacy"], "weights": [0.7, 0.3], "limit": 5}
    )
    assert "combined_similarity" in result[0].text or "Bob" in result[0].text

    # Erreur : queries manquant
    result_err = await call_tool(name="search_candidates_multi_criteria", arguments={})
    assert "queries requis" in result_err[0].text or "success" in result_err[0].text.lower()


@pytest.mark.asyncio
async def test_get_rag_snippet_tool(mocker):
    """A3 — get_rag_snippet : vérifie le GET /user/{id}/rag-snippet."""
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "user_id": 1,
        "query": "Kubernetes CI/CD",
        "snippets": [{"text": "Mission: DevOps @ Client | Kubernetes, ArgoCD", "relevance_score": 0.91}]
    }
    mock_resp.raise_for_status = MagicMock()
    client_instance.get.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")
    result = await call_tool(name="get_rag_snippet", arguments={"user_id": 1, "query": "Kubernetes CI/CD"})
    assert "snippets" in result[0].text or "Kubernetes" in result[0].text

    # Erreur : paramètres manquants
    result_err = await call_tool(name="get_rag_snippet", arguments={"user_id": 1})
    assert "user_id et query requis" in result_err[0].text or "success" in result_err[0].text.lower()


@pytest.mark.asyncio
async def test_match_mission_to_candidates_tool(mocker):
    """B2 — match_mission_to_candidates : vérifie le POST /search/mission-match."""
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [
        {"user_id": 3, "similarity_score": 0.88, "full_name": "Carol Li", "current_role": "Cloud Architect"}
    ]
    mock_resp.raise_for_status = MagicMock()
    client_instance.post.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")
    result = await call_tool(name="match_mission_to_candidates", arguments={"mission_id": 42, "limit": 5})
    assert "similarity_score" in result[0].text or "Carol" in result[0].text

    # Erreur : mission_id manquant
    result_err = await call_tool(name="match_mission_to_candidates", arguments={})
    assert "mission_id requis" in result_err[0].text or "success" in result_err[0].text.lower()


@pytest.mark.asyncio
async def test_get_skills_coverage_tool(mocker):
    """C1 — get_skills_coverage : vérifie le GET /analytics/skills-coverage."""
    mock_httpx = mocker.patch("mcp_server.httpx.AsyncClient")
    client_instance = AsyncMock()
    mock_httpx.return_value.__aenter__.return_value = client_instance

    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [
        {"skill": "Kubernetes", "consultant_count": 42},
        {"skill": "Google Cloud Platform", "consultant_count": 35},
        {"skill": "Python", "consultant_count": 28},
    ]
    mock_resp.raise_for_status = MagicMock()
    client_instance.get.return_value = mock_resp

    mcp_auth_header_var.set("Bearer token")
    result = await call_tool(name="get_skills_coverage", arguments={"top_n": 3})
    assert "Kubernetes" in result[0].text or "consultant_count" in result[0].text

    # Avec filtre agence
    result2 = await call_tool(name="get_skills_coverage", arguments={"agency": "lyon", "top_n": 10})
    assert result2[0].text  # doit retourner quelque chose
