import pytest
from unittest.mock import MagicMock, AsyncMock, patch
import json
import asyncio
import os

from src.services.bulk_service import bg_bulk_reanalyse, bg_retry_apply

@pytest.mark.asyncio
async def test_bg_bulk_reanalyse_success():
    """Test the asynchronous bg_bulk_reanalyse function."""
    with patch("src.services.bulk_service.database.SessionLocal") as mock_session_local:
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        
        mock_result = MagicMock()
        mock_result.all.return_value = [(1, "Contenu brut CV", 42)]
        mock_db.execute.return_value = mock_result
        
        with patch("src.services.bulk_service.gcs_storage.Client") as MockClient:
            mock_bucket = MagicMock()
            mock_blob = MagicMock()
            MockClient.return_value.bucket.return_value = mock_bucket
            mock_bucket.blob.return_value = mock_blob
            
            with patch("src.services.bulk_service.vertex_batch_client") as mock_batch_client:
                mock_job = MagicMock()
                mock_job.name = "projects/test/locations/test/batchPredictionJobs/123"
                # For vertex_batch_client.batches.create
                mock_batch_client.batches.create.return_value = mock_job
                # For vertex_batch_client.batches.get
                mock_job_status = MagicMock()
                mock_job_status.state.name = "JOB_STATE_SUCCEEDED"
                mock_batch_client.batches.get.return_value = mock_job_status
                
                with patch("src.services.bulk_service._get_cv_extraction_prompt", new_callable=AsyncMock) as mock_prompt:
                    mock_prompt.return_value = "Prompt"
                    with patch("src.services.bulk_service.bulk_reanalyse_manager.update_progress") as mock_update:
                        await bg_bulk_reanalyse("token")
                        assert mock_batch_client.batches.create.call_count == 1
                        mock_update.assert_called()
