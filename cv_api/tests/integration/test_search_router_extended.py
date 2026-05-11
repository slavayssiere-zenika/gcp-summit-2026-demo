import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
from src.cvs.models import CVProfile
import os
from main import app
from database import get_db

async def override_get_db():
    db = AsyncMock()
    # For scalars().first() or scalars().all()
    mock_result = MagicMock()
    yield db

@pytest.fixture(autouse=True)
def setup_db_mock():
    app.dependency_overrides[get_db] = override_get_db
    yield
    app.dependency_overrides.pop(get_db, None)

@pytest.mark.asyncio
async def test_search_candidates_post(client):
    with patch("src.cvs.routers.search_router.execute_search", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = {"items": [], "total": 0, "skip": 0, "limit": 10}
        resp = client.post("/search", json={"query": "test", "limit": 10, "skip": 0})
        assert resp.status_code == 200

@pytest.mark.asyncio
async def test_find_similar_consultants_missing(client):
    async def override_db_missing():
        db = AsyncMock()
        mock_res = MagicMock()
        mock_res.scalar_one_or_none.return_value = None
        db.execute.return_value = mock_res
        yield db
    
    app.dependency_overrides[get_db] = override_db_missing
    resp = client.get("/user/999/similar")
    assert resp.status_code == 404
    app.dependency_overrides[get_db] = override_get_db

@pytest.mark.asyncio
async def test_find_similar_consultants_success(client):
    async def override_db_success():
        db = AsyncMock()
        mock_res1 = MagicMock()
        mock_res1.scalar_one_or_none.return_value = [0.1]*3072
        
        mock_res2 = MagicMock()
        p1 = CVProfile(user_id=1, current_role="Dev", years_of_experience=5, source_tag="tag")
        mock_res2.all.return_value = [(p1, 0.1)]
        
        db.execute.side_effect = [mock_res1, mock_res2]
        yield db
    
    app.dependency_overrides[get_db] = override_db_success
    
    with patch("src.cvs.routers.search_router.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"id": 1, "full_name": "Test", "email": "test@e.com", "is_anonymous": False}
        mock_get.return_value = mock_resp
        
        resp = client.get("/user/1/similar")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
    
    app.dependency_overrides[get_db] = override_get_db

class MockEmbeddingValue:
    def __init__(self, values):
        self.values = values

class MockEmbeddingResult:
    def __init__(self, values):
        self.embeddings = [MockEmbeddingValue(values)]

@pytest.mark.asyncio
async def test_search_candidates_multi_criteria_success(client):
    async def override_db_success():
        db = AsyncMock()
        mock_res = MagicMock()
        p1 = CVProfile(user_id=1, current_role="Dev", years_of_experience=5, source_tag="tag")
        mock_res.all.return_value = [(p1, 0.1)]
        db.execute.return_value = mock_res
        yield db
    
    app.dependency_overrides[get_db] = override_db_success
    
    with patch("src.cvs.routers.search_router.embed_content_with_retry", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = MockEmbeddingResult([0.1]*3072)
        
        with patch("src.cvs.routers.search_router.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"id": 1, "full_name": "Test", "email": "t@t.com", "is_anonymous": False}
            mock_get.return_value = mock_resp
            
            with patch.dict(os.environ, {"GEMINI_EMBEDDING_MODEL": "test-model"}):
                with patch("src.cvs.routers.search_router._svc_config.client", MagicMock()):
                    resp = client.post("/search/multi-criteria", json={"queries": ["q1", "q2"], "weights": [0.5, 0.5]}, headers={"Authorization": "Bearer token"})
                    assert resp.status_code == 200
    
    app.dependency_overrides[get_db] = override_get_db

@pytest.mark.asyncio
async def test_get_rag_snippet_success(client):
    async def override_db_success():
        db = AsyncMock()
        mock_res = MagicMock()
        p1 = CVProfile(user_id=1, summary="Dev Python", current_role="Dev", competencies_keywords=["python"], educations=[], missions=[])
        mock_res.scalars.return_value.first.return_value = p1
        db.execute.return_value = mock_res
        yield db
    
    app.dependency_overrides[get_db] = override_db_success
    
    with patch("src.cvs.routers.search_router.embed_content_with_retry", new_callable=AsyncMock) as mock_embed:
        mock_embed.return_value = MockEmbeddingResult([0.1]*3072)
        
        with patch.dict(os.environ, {"GEMINI_EMBEDDING_MODEL": "test-model"}):
            with patch("src.cvs.routers.search_router._svc_config.client", MagicMock()):
                resp = client.get("/user/1/rag-snippet?query=python", headers={"Authorization": "Bearer token"})
                assert resp.status_code == 200
                assert "snippets" in resp.json()
    
    app.dependency_overrides[get_db] = override_get_db

@pytest.mark.asyncio
async def test_match_mission_to_candidates_success(client):
    async def override_db_success():
        db = AsyncMock()
        mock_res = MagicMock()
        p1 = CVProfile(user_id=1, current_role="Dev", years_of_experience=5, source_tag="tag")
        mock_res.all.return_value = [(p1, 0.1)]
        db.execute.return_value = mock_res
        yield db
    
    app.dependency_overrides[get_db] = override_db_success
    
    with patch("src.cvs.routers.search_router.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_mission = MagicMock()
        mock_mission.status_code = 200
        mock_mission.json.return_value = {"id": 1, "description": "Mission Test"}
        
        mock_emb = MagicMock()
        mock_emb.status_code = 200
        mock_emb.json.return_value = {"embedding": [0.1]*3072}
        
        mock_user = MagicMock()
        mock_user.status_code = 200
        mock_user.json.return_value = {"id": 1, "full_name": "Test", "email": "t@t.com", "is_anonymous": False}
        
        mock_get.side_effect = [mock_mission, mock_emb, mock_user]
        
        with patch.dict(os.environ, {"MISSIONS_API_URL": "http://test", "PROMPTS_API_URL": "http://test"}):
            resp = client.post("/search/mission-match?mission_id=1", headers={"Authorization": "Bearer token"})
            assert resp.status_code == 200
    
    app.dependency_overrides[get_db] = override_get_db
