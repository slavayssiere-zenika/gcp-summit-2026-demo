import os
os.environ["SECRET_KEY"] = "testsecret"
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from main import app
from src.database import get_db

client = TestClient(app, raise_server_exceptions=True)

mock_db = AsyncMock()
mock_result = MagicMock()
mock_result.all.return_value = [(MagicMock(user_id=1), 0.1), (MagicMock(user_id=2), 0.4)]
mock_db.execute.return_value = mock_result
app.dependency_overrides[get_db] = lambda: mock_db

def test_search_candidates():
    # Mock Gemini embedding
    emb_res = MagicMock()
    emb_res.embeddings = [MagicMock(values=[0.1, 0.2, 0.3])]
    import src.services.search_service as search_service
    search_service.genai_client = MagicMock()
    
    # We also need to mock generate_content_with_retry and embed_content_with_retry in gemini_retry?
    import src.gemini_retry as gemini_retry
    gemini_retry.embed_content_with_retry = AsyncMock(return_value=emb_res)
    gemini_retry.generate_content_with_retry = AsyncMock()
    gemini_retry.generate_content_with_retry.return_value.text = "[]"
    
    response = client.get("/search?query=test", headers={"Authorization": "Bearer token"})
    print(response.status_code, response.json())

test_search_candidates()
