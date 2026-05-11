import pytest
import sys
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.taxonomy_batch_service import TaxonomyBatchService
import os

sys.modules['json_repair'] = MagicMock()
sys.modules['json_repair'].loads.return_value = {"Pillar": {"categories": []}}

@pytest.mark.asyncio
async def test_check_batch_succeeded_map():
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "status": "running", 
            "batch_job_id": "projects/1/locations/eu/batchPredictionJobs/abc", 
            "batch_step": "map"
        }
        
        with patch("src.services.config.vertex_batch_client") as mock_vbg:
            mock_job = MagicMock()
            mock_job.state.name = "JOB_STATE_SUCCEEDED"
            mock_job.dest.gcs_uri = "gs://test-bucket/output/"
            mock_vbg.batches.get.return_value = mock_job
            
            with patch("src.services.taxonomy_batch_service.gcs_storage.Client") as mock_gcs:
                mock_bucket = MagicMock()
                mock_blob = MagicMock()
                mock_blob.name = "output/file.jsonl"
                
                # Mock parse_jsonl_map_result
                fake_jsonl = '{"response": {"candidates": [{"content": {"parts": [{"text": "```json\\n{\\"pillars\\": []}\\n```"}]}}]}}'
                mock_blob.download_as_text.return_value = fake_jsonl
                mock_bucket.list_blobs.return_value = [mock_blob]
                mock_gcs.return_value.bucket.return_value = mock_bucket
                
                with patch("src.services.taxonomy_batch_service.parse_jsonl_map_result") as mock_parse:
                    mock_parse.return_value = ({"Pillar": [{"name": "Skill"}]}, MagicMock())
                    
                    with patch("src.services.taxonomy_batch_service.log_finops", new_callable=AsyncMock):
                        with patch("src.services.taxonomy_batch_service.TaxonomyBatchService.generate_autonomous_service_token", new_callable=AsyncMock) as mock_gen_token:
                            mock_gen_token.return_value = "token"
                            
                            with patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress", new_callable=AsyncMock):
                                # It spawns a background task `run_dedup`.
                                # We want to test run_dedup directly. We can mock run_dedup or let it be defined.
                                # Let's patch asyncio.create_task to execute it immediately or just not wait.
                                with patch("src.services.taxonomy_batch_service.asyncio.create_task") as mock_create_task:
                                    with patch.dict(os.environ, {"GEMINI_MODEL": "test"}):
                                        with patch("src.services.taxonomy_batch_service.BATCH_GCS_BUCKET", "test_bucket"):
                                            res = await TaxonomyBatchService.check_batch("Bearer x", "user")
                                            assert res["success"] is True
                                            assert res["state"] == "PROCESSING_DEDUP"
                                            assert mock_create_task.called
                                            
                                            # Now run the run_dedup coroutine to get coverage
                                            run_dedup_coro = mock_create_task.call_args[0][0]
                                            
                                            with patch("src.services.taxonomy_batch_service._fetch_prompt", new_callable=AsyncMock) as mock_fetch:
                                                mock_fetch.return_value = "prompt {{MAP_RESULT}} {{CURRENT_PILLAR}}"
                                                
                                                with patch("src.services.taxonomy_batch_service.generate_content_with_retry", new_callable=AsyncMock) as mock_gen_content:
                                                    mock_resp = MagicMock()
                                                    mock_resp.text = '{"pillars": [{"name": "Pillar"}]}'
                                                    mock_resp.candidates = [MagicMock()]
                                                    mock_resp.candidates[0].finish_reason = "STOP"
                                                    mock_gen_content.return_value = mock_resp
                                                    
                                                    with patch.dict(os.environ, {"GEMINI_PRO_MODEL": "test"}):
                                                        await run_dedup_coro

@pytest.mark.asyncio
async def test_check_batch_succeeded_reduce():
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "status": "running", 
            "batch_job_id": "projects/1/locations/eu/batchPredictionJobs/abc", 
            "batch_step": "reduce",
            "completed_pillars": [{"name": "Pillar"}]
        }
        
        with patch("src.services.config.vertex_batch_client") as mock_vbg:
            mock_job = MagicMock()
            mock_job.state.name = "JOB_STATE_SUCCEEDED"
            mock_job.dest.gcs_uri = "gs://test-bucket/output/"
            mock_vbg.batches.get.return_value = mock_job
            
            with patch("src.services.taxonomy_batch_service.gcs_storage.Client") as mock_gcs:
                mock_bucket = MagicMock()
                mock_blob = MagicMock()
                mock_blob.name = "output/file.jsonl"
                
                fake_jsonl = '{"response": {"candidates": [{"content": {"parts": [{"text": "```json\\n{\\"Pillar\\": {\\"categories\\": []}}\\n```"}]}}]}}'
                mock_blob.download_as_text.return_value = fake_jsonl
                mock_bucket.list_blobs.return_value = [mock_blob]
                mock_gcs.return_value.bucket.return_value = mock_bucket
                
                with patch("src.services.taxonomy_batch_service.parse_jsonl_map_result") as mock_parse:
                    mock_parse.return_value = ({"Pillar": {"categories": []}}, MagicMock())
                    with patch("src.services.taxonomy_batch_service.log_finops", new_callable=AsyncMock):
                        with patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress", new_callable=AsyncMock):
                            with patch("src.services.taxonomy_batch_service._fetch_prompt", new_callable=AsyncMock) as mock_fetch:
                                mock_fetch.return_value = "prompt {{REDUCE_RESULT}}"
                                with patch("src.services.taxonomy_batch_service._get_existing_competencies", new_callable=AsyncMock) as mock_exist:
                                    mock_exist.return_value = ["Skill1", "Skill2"]
                                    with patch.dict(os.environ, {"GEMINI_MODEL": "test", "GEMINI_PRO_MODEL": "test_pro"}):
                                        with patch("src.services.taxonomy_batch_service.BATCH_GCS_BUCKET", "test_bucket"):
                                            # Also mock gcs upload
                                            res = await TaxonomyBatchService.check_batch("Bearer x", "user")
                                            assert res["success"] is True, f"Failed: {res}"
                                            assert res["state"] == "PROCESSING_SWEEP"
@pytest.mark.asyncio
async def test_check_batch_succeeded_sweep():
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "status": "running", 
            "batch_job_id": "projects/1/locations/eu/batchPredictionJobs/abc", 
            "batch_step": "sweep",
            "res_tree": {"Pillar": {"categories": []}}
        }
        
        with patch("src.services.config.vertex_batch_client") as mock_vbg:
            mock_job = MagicMock()
            mock_job.state.name = "JOB_STATE_SUCCEEDED"
            mock_job.dest.gcs_uri = "gs://test-bucket/output/"
            mock_vbg.batches.get.return_value = mock_job
            
            with patch("src.services.taxonomy_batch_service.gcs_storage.Client") as mock_gcs:
                mock_bucket = MagicMock()
                mock_blob = MagicMock()
                mock_blob.name = "output/file.jsonl"
                
                fake_jsonl = '{"response": {"candidates": [{"content": {"parts": [{"text": "```json\\n{\\"assignments\\": [{\\"competency\\": \\"Skill1\\", \\"target_pillar\\": \\"P1\\", \\"target_category\\": \\"C1\\"}]}\\n```"}]}}]}}'
                mock_blob.download_as_text.return_value = fake_jsonl
                mock_bucket.list_blobs.return_value = [mock_blob]
                mock_gcs.return_value.bucket.return_value = mock_bucket
                
                with patch("src.services.taxonomy_batch_service.log_finops", new_callable=AsyncMock):
                    with patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress", new_callable=AsyncMock):
                        with patch.dict(os.environ, {"GEMINI_MODEL": "test", "GEMINI_PRO_MODEL": "test_pro", "COMPETENCIES_API_URL": "http://api"}):
                            with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                                mock_resp = MagicMock()
                                mock_resp.status_code = 200
                                mock_post.return_value = mock_resp
                                
                                res = await TaxonomyBatchService.check_batch("Bearer x", "user")
                                assert res["success"] is True, f"Failed: {res}"
                                assert res["state"] == "COMPLETED"

