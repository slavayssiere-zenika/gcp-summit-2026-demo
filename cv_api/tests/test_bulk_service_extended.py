from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from src.services.bulk_helpers import _acquire_service_token, _get_cv_extraction_prompt
from src.services.bulk_service import bg_retry_apply


@pytest.mark.asyncio
async def test_acquire_service_token_success():
    with patch("src.services.bulk_helpers.httpx.AsyncClient") as mock_ac:
        mock_client = AsyncMock()
        mock_ac.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "token123", "token_type": "bearer"}
        mock_client.post.return_value = mock_resp

        token = await _acquire_service_token("Bearer old")
        assert token == "token123"


@pytest.mark.asyncio
async def test_acquire_service_token_fail():
    with patch("src.services.bulk_helpers.httpx.AsyncClient") as mock_ac:
        mock_client = AsyncMock()
        mock_ac.return_value.__aenter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_client.post.return_value = mock_resp

        token = await _acquire_service_token("Bearer old")
        assert token == "old"


@pytest.mark.asyncio
async def test_get_cv_extraction_prompt_cache():
    with patch("src.services.bulk_helpers.get_cache", return_value="cached_prompt"):
        prompt = await _get_cv_extraction_prompt()
        assert prompt == "cached_prompt"


@pytest.mark.asyncio
async def test_bg_retry_apply_no_results():
    with patch("src.services.bulk_service.database.SessionLocal") as mock_session_local:
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        mock_result = MagicMock()
        mock_result.all.return_value = [(1, 42)]
        mock_db.execute.return_value = mock_result

        with patch("src.services.bulk_service.gcs_storage.Client") as MockClient:
            mock_bucket = MagicMock()
            MockClient.return_value.bucket.return_value = mock_bucket
            mock_bucket.list_blobs.return_value = []  # No blobs

            with patch("src.services.bulk_service.bulk_reanalyse_manager.update_progress", new_callable=AsyncMock) as mock_update:
                await bg_retry_apply("token", "gs://bucket/prefix")
                # Assert error updated
                mock_update.assert_any_call(status="error", error="[retry-apply] Aucun résultat GCS valide trouvé.")


@pytest.mark.asyncio
async def test_bg_retry_apply_success():
    with patch("src.services.bulk_service.database.SessionLocal") as mock_session_local:
        mock_db = AsyncMock()
        mock_session_local.return_value.__aenter__.return_value = mock_db
        mock_result = MagicMock()
        mock_result.all.return_value = [(1, 42)]
        mock_db.execute.return_value = mock_result

        with patch("src.services.bulk_service.gcs_storage.Client") as MockClient:
            mock_bucket = MagicMock()
            mock_blob = MagicMock()
            mock_blob.name = "test.jsonl"
            mock_blob.download_as_text.return_value = '{"id": "cv-1", "response": {"candidates": [{"content": {"parts": [{"text": "{\\"current_role\\": \\"Dev\\"}"}]}}]}}\n'
            MockClient.return_value.bucket.return_value = mock_bucket
            mock_bucket.list_blobs.return_value = [mock_blob]

            with patch("src.services.bulk_service.scale_bulk_dependencies", new_callable=AsyncMock):
                with patch("src.services.bulk_service.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                    mock_resp = MagicMock()
                    mock_resp.status_code = 200
                    mock_get.return_value = mock_resp

                    with patch("src.services.bulk_service.embed_content_with_retry", new_callable=AsyncMock) as mock_embed:
                        mock_emb = MagicMock()
                        mock_emb.embeddings = [MagicMock(values=[0.1]*3072)]
                        mock_embed.return_value = mock_emb

                        with patch("src.services.bulk_service.httpx.AsyncClient.delete", new_callable=AsyncMock) as mock_delete:
                            mock_del_resp = MagicMock()
                            mock_del_resp.status_code = 200
                            mock_delete.return_value = mock_del_resp

                            with patch("src.services.bulk_service.httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
                                mock_post_resp = MagicMock()
                                mock_post_resp.status_code = 200
                                mock_post.return_value = mock_post_resp

                                await bg_retry_apply("token", "gs://bucket/prefix")
