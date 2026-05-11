import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.taxonomy_batch_service import TaxonomyBatchService
import os

@pytest.mark.asyncio
async def test_generate_autonomous_service_token_success():
    with patch("src.services.taxonomy_batch_service.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        # First call login, second call service-token
        mock_resp1 = MagicMock()
        mock_resp1.status_code = 200
        mock_resp1.json.return_value = {"access_token": "short", "token_type": "bearer"}
        
        mock_resp2 = MagicMock()
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {"access_token": "long", "token_type": "bearer"}
        
        mock_post.side_effect = [mock_resp1, mock_resp2]
        
        with patch.dict(os.environ, {"USE_IAM_AUTH": "true"}):
            with patch("google.oauth2.id_token.fetch_id_token", return_value="oidc"):
                token = await TaxonomyBatchService.generate_autonomous_service_token()
                assert token == "long"

@pytest.mark.asyncio
async def test_start_batch_already_running():
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"status": "running", "batch_job_id": "test"}
        with patch("src.services.config.vertex_batch_client") as mock_vbg:
            mock_job = MagicMock()
            mock_job.state.name = "JOB_STATE_RUNNING"
            mock_vbg.batches.get.return_value = mock_job
            
            res = await TaxonomyBatchService.start_batch("Bearer x")
            assert res["success"] is False
            assert "déjà en cours" in res["message"]

@pytest.mark.asyncio
async def test_start_batch_success():
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        
        with patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress", new_callable=AsyncMock):
            with patch("src.services.taxonomy_batch_service.tree_task_manager.initialize_task", new_callable=AsyncMock):
                with patch("src.services.taxonomy_batch_service.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_resp.json.return_value = {"deleted_count": 0}
                    mock_post.return_value = mock_resp
                    
                    with patch("src.services.taxonomy_batch_service._get_existing_competencies", new_callable=AsyncMock) as mock_exist:
                        mock_exist.return_value = ["c1"]
                        with patch("src.services.taxonomy_batch_service._fetch_prompt", new_callable=AsyncMock) as mock_fetch:
                            mock_fetch.return_value = "prompt {{EXISTING_COMPETENCIES}}"
                            
                            with patch("src.services.taxonomy_batch_service.gcs_storage.Client"):
                                with patch("src.services.config.vertex_batch_client") as mock_create:
                                    mock_job = MagicMock()
                                    mock_job.name = "job123"
                                    mock_create.batches.create.return_value = mock_job
                                    
                                    with patch.dict(os.environ, {"GEMINI_PRO_MODEL": "test"}):
                                        with patch("src.services.taxonomy_batch_service.BATCH_GCS_BUCKET", "test_bucket"):
                                            res = await TaxonomyBatchService.start_batch("Bearer x")
                                            assert res["success"] is True

@pytest.mark.asyncio
async def test_check_batch_no_batch():
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        res = await TaxonomyBatchService.check_batch("Bearer x", "user")
        assert res["success"] is True
        assert "Aucun batch" in res["message"]

@pytest.mark.asyncio
async def test_check_batch_failed():
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"status": "running", "batch_job_id": "projects/1/locations/eu/batchPredictionJobs/abc", "batch_step": "map"}
        
        with patch("src.services.config.vertex_batch_client") as mock_vbg:
            mock_job = MagicMock()
            mock_job.state.name = "JOB_STATE_FAILED"
            mock_vbg.batches.get.return_value = mock_job
            
            with patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress", new_callable=AsyncMock):
                res = await TaxonomyBatchService.check_batch("Bearer x", "user")
                assert res["success"] is False
