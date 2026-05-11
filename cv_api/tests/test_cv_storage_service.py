import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.cv_storage_service import CVStorageService
import json

@pytest.mark.asyncio
async def test_sanitize_field():
    assert CVStorageService.sanitize_field(None) is None
    assert CVStorageService.sanitize_field("  ") is None
    assert CVStorageService.sanitize_field(" Unknown ") is None
    assert CVStorageService.sanitize_field("Hello") == "Hello"

@pytest.mark.asyncio
async def test_normalize_str():
    assert CVStorageService.normalize_str("Élève") == "eleve"
    assert CVStorageService.normalize_str(None) == ""

@pytest.mark.asyncio
async def test_is_valid_name():
    assert CVStorageService.is_valid_name("Jean-Pierre") is True
    assert CVStorageService.is_valid_name("123") is False

@pytest.mark.asyncio
async def test_is_valid_email():
    assert CVStorageService.is_valid_email("test@zenika.com") is True
    assert CVStorageService.is_valid_email("not-an-email") is False

@pytest.mark.asyncio
async def test_bg_process_competencies_and_missions():
    bg_user_id = 1
    bg_structured_cv = {
        "competencies": [{"name": "Python", "practiced": True, "parent": "Backend"}],
        "missions": [{"title": "Dev", "description": "Doing dev"}]
    }
    bg_headers = {"Auth": "Bearer x"}
    bg_url = "https://drive.google.com/file/d/123xyz"
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            with patch("httpx.AsyncClient.patch", new_callable=AsyncMock) as mock_patch:
                
                # Mock get
                mock_resp_comps = MagicMock(status_code=200)
                mock_resp_comps.json.return_value = [{"id": 1, "name": "Python"}]
                
                # Mock search
                mock_resp_search = MagicMock(status_code=200)
                mock_resp_search.json.return_value = {"items": [{"id": 1, "name": "Python"}], "total": 1, "skip": 0, "limit": 10}
                
                mock_get.side_effect = [
                    mock_resp_comps,  # user competencies
                    mock_resp_search, # search Python
                    mock_resp_search, # search Backend
                    MagicMock(status_code=200, json=lambda: [{"id": 1, "name": "Missions"}]) # get categories
                ]
                
                # Mock post
                mock_post.return_value = MagicMock(status_code=200, json=lambda: {"id": 1})
                
                await CVStorageService.bg_process_competencies_and_missions(bg_user_id, bg_structured_cv, bg_headers, bg_url)
                
                # Verify that API calls were made
                assert mock_get.call_count >= 1

@pytest.mark.asyncio
async def test_upsert_cv_profile():
    mock_db = AsyncMock()
    mock_db.execute.return_value = MagicMock()
    mock_db.add = MagicMock()
    
    structured_cv = {"competencies": [{"name": "Python"}], "current_role": "Dev"}
    
    await CVStorageService.upsert_cv_profile(
        mock_db, 1, "http://url", "tag", structured_cv, "raw_text", None, None, 100
    )
    
    mock_db.execute.assert_called()
    mock_db.add.assert_called()
    mock_db.commit.assert_called_once()
