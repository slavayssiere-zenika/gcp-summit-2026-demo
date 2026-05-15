import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.bulk_helpers import _post_missions_bulk
from src.services.bulk_service import bg_bulk_reanalyse

@pytest.mark.asyncio
async def test_post_missions_bulk_success():
    mock_hc = AsyncMock()
    mock_post_resp = MagicMock(status_code=200)
    mock_hc.post.return_value = mock_post_resp
    
    with patch("src.services.bulk_service.log_finops", new_callable=AsyncMock):
        missions = [{"company": "Z", "skills": ["S1"], "start_date": "2020", "end_date": "2021"}]
        await _post_missions_bulk(mock_hc, 1, missions, {"Auth": "Bearer x"})
        mock_hc.post.assert_called()

@pytest.mark.asyncio
async def test_post_missions_bulk_failures():
    mock_hc = AsyncMock()
    mock_hc.post.side_effect = Exception("post err")
    with patch("src.services.bulk_helpers.logger") as mock_logger:
        missions = [{"company": "Z"}]
        await _post_missions_bulk(mock_hc, 1, missions, {"Auth": "Bearer x"})
        mock_logger.warning.assert_called()
        
    # Test empty missions
    mock_hc.post.reset_mock()
    await _post_missions_bulk(mock_hc, 1, [], {"Auth": "Bearer x"})
    mock_hc.post.assert_not_called()

@pytest.mark.asyncio
async def test_bg_bulk_reanalyse_with_filters():
    with patch("src.services.bulk_service.database.SessionLocal") as mock_session_local:
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        
        mock_result = MagicMock()
        mock_result.all.return_value = [(1, "Content", 42)]
        mock_db.execute.return_value = mock_result
        
        with patch("src.services.bulk_service.gcs_storage.Client") as mock_gcs:
            with patch("src.services.bulk_service.vertex_batch_client") as mock_vbg:
                mock_job = MagicMock()
                mock_job.name = "job123"
                mock_job.state.name = "JOB_STATE_SUCCEEDED"
                mock_vbg.batches.create.return_value = mock_job
                mock_vbg.batches.get.return_value = mock_job
                
                with patch("src.services.bulk_service._get_cv_extraction_prompt", new_callable=AsyncMock) as mock_prompt:
                    mock_prompt.return_value = "prompt"
                    with patch("src.services.bulk_service.bulk_reanalyse_manager.update_progress", new_callable=AsyncMock):
                        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                            mock_get.return_value = MagicMock(status_code=200)
                            with patch("src.services.bulk_service.asyncio.sleep", new_callable=AsyncMock):
                                await bg_bulk_reanalyse("token")
                                mock_vbg.batches.create.assert_called()
