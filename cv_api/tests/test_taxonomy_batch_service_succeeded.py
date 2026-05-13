import pytest
import sys
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.taxonomy_batch_service import TaxonomyBatchService
import os

sys.modules['json_repair'] = MagicMock()
sys.modules['json_repair'].loads.return_value = {"Pillar": {"categories": []}}

_MODEL_ENV = {
    "GEMINI_MODEL": "test",
    "GEMINI_PRO_MODEL": "test_pro",
    "GEMINI_BATCH_MODEL": "test_flash",
}


@pytest.mark.asyncio
async def test_check_batch_succeeded_map():
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status",
               new_callable=AsyncMock) as mock_get:
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

                fake_jsonl = (
                    '{"response": {"candidates": [{"content": {"parts":'
                    ' [{"text": "```json\\n{\\"pillars\\": []}\\n```"}]}}]}}'
                )
                mock_blob.download_as_text.return_value = fake_jsonl
                mock_bucket.list_blobs.return_value = [mock_blob]
                mock_gcs.return_value.bucket.return_value = mock_bucket

                with patch("src.services.taxonomy_batch_service.parse_jsonl_map_result") as mock_parse:
                    mock_parse.return_value = ({"Pillar": [{"name": "Skill"}]}, MagicMock())

                    with patch("src.services.taxonomy_batch_service.log_finops", new_callable=AsyncMock), \
                         patch("src.services.taxonomy_batch_service.TaxonomyBatchService"
                               ".generate_autonomous_service_token",
                               new_callable=AsyncMock, return_value="token"), \
                         patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress",
                               new_callable=AsyncMock), \
                         patch("src.services.taxonomy_batch_service.asyncio.create_task") as mock_create_task, \
                         patch("src.services.taxonomy_batch_service.BATCH_GCS_BUCKET", "test_bucket"), \
                         patch.dict(os.environ, _MODEL_ENV):

                        res = await TaxonomyBatchService.check_batch("Bearer x", "user")
                        assert res["success"] is True
                        assert res["state"] == "PROCESSING_DEDUP"
                        assert mock_create_task.called

                        run_dedup_coro = mock_create_task.call_args[0][0]

                        with patch("src.services.taxonomy_batch_service._fetch_prompt",
                                   new_callable=AsyncMock, return_value="prompt {{MAP_RESULT}} {{CURRENT_PILLAR}}"), \
                             patch("src.services.taxonomy_batch_service.generate_content_with_retry",
                                   new_callable=AsyncMock) as mock_gen_content:

                            mock_resp = MagicMock()
                            mock_resp.text = '{"pillars": [{"name": "Pillar"}]}'
                            mock_resp.candidates = [MagicMock()]
                            mock_resp.candidates[0].finish_reason = "STOP"
                            mock_gen_content.return_value = mock_resp

                            await run_dedup_coro


@pytest.mark.asyncio
async def test_check_batch_succeeded_reduce():
    """
    Vérifie que le batch Reduce réussi → PROCESSING_SWEEP.
    completed_pillars correspond au pilier produit par json_repair.loads mock.
    _svc_config.vertex_batch_client est le seul patch nécessaire (get=état reduce, create=job sweep).
    """
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status",
               new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "status": "running",
            "batch_job_id": "projects/1/locations/eu/batchPredictionJobs/abc",
            "batch_step": "reduce",
            "completed_pillars": [{"name": "Pillar"}],
            "service_token": "persisted-token",
        }

        with patch("src.services.taxonomy_batch_service._svc_config.vertex_batch_client") as mock_vbg:
            reduce_job = MagicMock()
            reduce_job.state.name = "JOB_STATE_SUCCEEDED"
            reduce_job.dest.gcs_uri = "gs://test-bucket/output/"
            sweep_job = MagicMock()
            sweep_job.name = "sweep-job-123"
            mock_vbg.batches.get.return_value = reduce_job
            mock_vbg.batches.create.return_value = sweep_job

            with patch("src.services.taxonomy_batch_service.gcs_storage.Client") as mock_gcs:
                mock_bucket = MagicMock()
                mock_blob = MagicMock()
                mock_blob.name = "output/file.jsonl"
                mock_blob.download_as_text.return_value = (
                    '{"response": {"candidates": [{"content": {"parts":'
                    ' [{"text": "{\\"Pillar\\": {\\"categories\\": []}}"}]}}]}}'
                )
                mock_bucket.list_blobs.return_value = [mock_blob]
                mock_gcs.return_value.bucket.return_value = mock_bucket

                sys.modules["json_repair"].loads.return_value = {"Pillar": {"categories": []}}

                with patch("src.services.taxonomy_batch_service.log_finops", new_callable=AsyncMock), \
                     patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress",
                           new_callable=AsyncMock), \
                     patch("src.services.taxonomy_batch_service._fetch_prompt",
                           new_callable=AsyncMock, return_value="prompt {{REDUCE_RESULT}}"), \
                     patch("src.services.taxonomy_batch_service._get_existing_competencies",
                           new_callable=AsyncMock, return_value=["Skill1", "Skill2"]), \
                     patch("src.services.taxonomy_batch_service.TaxonomyBatchService"
                           ".generate_autonomous_service_token",
                           new_callable=AsyncMock, return_value=""), \
                     patch("src.services.taxonomy_batch_service.TaxonomyBatchService"
                           "._get_oidc_token_for_service",
                           new_callable=AsyncMock, return_value=""), \
                     patch("src.services.taxonomy_batch_service.BATCH_GCS_BUCKET", "test_bucket"), \
                     patch.dict(os.environ, {
                         **_MODEL_ENV,
                         "USE_IAM_AUTH": "false",
                         "PROMPTS_API_URL": "http://api",
                         "COMPETENCIES_API_URL": "http://api",
                     }):

                    res = await TaxonomyBatchService.check_batch("Bearer x", "user")
                    assert res["success"] is True, f"Failed: {res}"
                    assert res["state"] == "PROCESSING_SWEEP"


@pytest.mark.asyncio
async def test_check_batch_succeeded_sweep():
    with patch("src.services.taxonomy_batch_service.tree_task_manager.get_latest_status",
               new_callable=AsyncMock) as mock_get:
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

                fake_jsonl = (
                    '{"response": {"candidates": [{"content": {"parts":'
                    ' [{"text": "{\\"assignments\\": [{\\"competency\\": \\"Skill1\\",'
                    ' \\"target_pillar\\": \\"P1\\", \\"target_category\\": \\"C1\\"}]}"}]}}]}}'
                )
                mock_blob.download_as_text.return_value = fake_jsonl
                mock_bucket.list_blobs.return_value = [mock_blob]
                mock_gcs.return_value.bucket.return_value = mock_bucket

                with patch("src.services.taxonomy_batch_service.log_finops", new_callable=AsyncMock), \
                     patch("src.services.taxonomy_batch_service.tree_task_manager.update_progress",
                           new_callable=AsyncMock), \
                     patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post, \
                     patch.dict(os.environ, {
                         **_MODEL_ENV,
                         "COMPETENCIES_API_URL": "http://api",
                     }):

                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_post.return_value = mock_resp

                    res = await TaxonomyBatchService.check_batch("Bearer x", "user")
                    assert res["success"] is True, f"Failed: {res}"
                    assert res["state"] == "COMPLETED"
