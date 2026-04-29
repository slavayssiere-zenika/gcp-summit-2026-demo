import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import json
import os

from src.services.taxonomy_service import fetch_prompt, get_existing_competencies, run_taxonomy_step

@pytest.mark.asyncio
async def test_fetch_prompt_success():
    with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance
        
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"value": "Prompt content"}
        client_instance.get.return_value = mock_resp
        
        result = await fetch_prompt("prompt_name", "fallback.txt", "Bearer token")
        assert result == "Prompt content"

@pytest.mark.asyncio
async def test_get_existing_competencies_success():
    with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
        client_instance = AsyncMock()
        MockClient.return_value.__aenter__.return_value = client_instance
        
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"items": [{"name": "Java"}], "total": 1}
        client_instance.get.return_value = mock_resp
        
        # On ne veut pas tester la DB ici, on mock database.get_db
        with patch("src.services.taxonomy_service.database.get_db", return_value=AsyncMock()):
            # Simulate empty DB result for CV keywords
            result = await get_existing_competencies("Bearer token")
            assert "Java" in result

@pytest.mark.asyncio
async def test_run_taxonomy_step_apply():
    mock_genai_client = MagicMock()
    
    with patch("src.services.taxonomy_service.tree_task_manager.update_progress") as mock_update, \
         patch("src.services.taxonomy_service.tree_task_manager.get_latest_status") as mock_get_status:
        
        mock_get_status.return_value = {
            "res_tree": {"name": "Tech", "merge_from": ["OldTech"]},
            "sweep_result": [{"name": "DevOps", "merge_from": ["Ops"]}]
        }
        
        with patch("src.services.taxonomy_service.httpx.AsyncClient") as MockClient:
            client_instance = AsyncMock()
            MockClient.return_value.__aenter__.return_value = client_instance
            
            mock_resp = MagicMock(status_code=200)
            mock_resp.json.return_value = {"merges": [{"canonical": "Tech"}]}
            client_instance.post.return_value = mock_resp
            
            await run_taxonomy_step("Bearer token", "user_1", "apply", mock_genai_client)
            
            # Vérifie que la mise à jour finale contient status='completed'
            mock_update.assert_called_with(
                new_log="Terminé. 1 doublon(s) fusionné(s).",
                tree={"name": "Tech", "merge_from": ["OldTech"]},
                usage={"merges_applied": 1},
                status="completed"
            )
