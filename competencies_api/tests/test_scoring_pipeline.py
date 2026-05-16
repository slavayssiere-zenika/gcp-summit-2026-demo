import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.competencies import scoring_pipeline

# --- _fetch_missions_for_user ---


@pytest.mark.asyncio
async def test_fetch_missions_for_user_success():
    sem = asyncio.Semaphore(1)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Provide valid MissionsResponse dict
    mock_resp.json.return_value = {"items": [{"id": 1, "title": "Dev Python"}], "total": 1, "skip": 0, "limit": 100}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        uid, missions = await scoring_pipeline._fetch_missions_for_user(1, {}, sem)

        assert uid == 1
        assert len(missions) == 1
        assert missions[0]["id"] == 1


@pytest.mark.asyncio
async def test_fetch_missions_for_user_validation_error():
    sem = asyncio.Semaphore(1)
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # Invalid data structure according to MissionsResponse
    mock_resp.json.return_value = {"bad_key": []}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        uid, missions = await scoring_pipeline._fetch_missions_for_user(2, {}, sem)

        assert uid == 2
        assert len(missions) == 0


@pytest.mark.asyncio
async def test_fetch_missions_for_user_http_error():
    sem = asyncio.Semaphore(1)
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        uid, missions = await scoring_pipeline._fetch_missions_for_user(3, {}, sem)

        assert uid == 3
        assert len(missions) == 0

# --- _prefetch_all_missions ---


@pytest.mark.asyncio
@patch("src.competencies.scoring_pipeline._fetch_missions_for_user", new_callable=AsyncMock)
async def test_prefetch_all_missions(mock_fetch):
    mock_fetch.side_effect = [(1, [{"id": 1, "title": "m1"}]), (2, [{"id": 2, "title": "m2"}])]
    res = await scoring_pipeline._prefetch_all_missions([1, 2], {})
    assert res == {1: [{"id": 1, "title": "m1"}], 2: [{"id": 2, "title": "m2"}]}

# --- _apply_scoring_results ---


@pytest.mark.asyncio
async def test_apply_scoring_results_success():
    mock_db = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    with patch("shared.database.SessionLocal", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_db), __aexit__=AsyncMock())):
        success, errors, sample_err = await scoring_pipeline._apply_scoring_results([
            (1, 10, "Python", 4.0, "Good")
        ])
        assert success == 1
        assert errors == 0
        assert mock_db.commit.called

# --- bg_bulk_scoring_vertex ---


@pytest.mark.asyncio
async def test_bg_bulk_scoring_vertex_no_config():
    with patch("src.competencies.scoring_pipeline.GCP_PROJECT_ID", None):
        with patch("src.competencies.scoring_pipeline.bulk_scoring_manager.update_progress", new_callable=AsyncMock) as mock_progress:
            await scoring_pipeline.bg_bulk_scoring_vertex([1], {})
            mock_progress.assert_called_with(status="error", error="GCP_PROJECT_ID ou BATCH_GCS_BUCKET non configuré — scoring Vertex désactivé.")


@pytest.mark.asyncio
@patch("src.competencies.scoring_pipeline.GCP_PROJECT_ID", "test-project")
@patch("src.competencies.scoring_pipeline.BATCH_GCS_BUCKET", "test-bucket")
@patch("src.competencies.scoring_pipeline.VERTEX_BATCH_MODEL", "gemini-3.1-flash-lite")
@patch("google.genai.Client")
@patch("src.competencies.scoring_pipeline.database.SessionLocal")
@patch("src.competencies.scoring_pipeline._prefetch_all_missions", new_callable=AsyncMock)
@patch("src.competencies.scoring_pipeline.gcs_storage.Client")
@patch("src.competencies.scoring_pipeline.asyncio.sleep", new_callable=AsyncMock)
@patch("src.competencies.scoring_pipeline.set_scoring_scheduler_enabled", new_callable=AsyncMock)
@patch("src.competencies.scoring_pipeline.bulk_scoring_manager.update_progress", new_callable=AsyncMock)
async def test_bg_bulk_scoring_vertex_success(mock_update_progress, mock_set_scheduler, mock_sleep, mock_gcs, mock_prefetch, mock_db_session, mock_genai_client):

    # Mock genai Client
    mock_vertex_client = MagicMock()
    mock_genai_client.return_value = mock_vertex_client

    mock_job = MagicMock()
    mock_job.name = "jobs/123"
    mock_job.state.name = "JOB_STATE_SUCCEEDED"
    mock_vertex_client.batches.create.return_value = mock_job
    mock_vertex_client.batches.get.return_value = mock_job

    # Mock DB to return leaf competencies
    mock_db = MagicMock()
    mock_result_1 = MagicMock()
    mock_result_1.scalars.return_value.all.return_value = [10]
    mock_result_delta = MagicMock()
    mock_result_delta.scalars.return_value.all.return_value = []
    mock_result_2 = MagicMock()
    mock_result_2.all.return_value = [(10, "Python")]
    mock_db.execute = AsyncMock(side_effect=[mock_result_1, mock_result_delta, mock_result_2])

    mock_db_session.return_value = AsyncMock(__aenter__=AsyncMock(return_value=mock_db), __aexit__=AsyncMock())

    # Mock prefetch
    mock_prefetch.return_value = {1: [{"id": 1}]}

    # Mock jsonl build
    with patch("src.competencies.scoring_pipeline._build_jsonl_lines") as mock_build:
        mock_build.return_value = (['{"request": "1"}'], {"r1": (1, 10, "Python")}, 0)

        # Mock GCS Output download
        mock_bucket = MagicMock()
        mock_gcs.return_value.bucket.return_value = mock_bucket
        mock_blob = MagicMock()
        mock_blob.name = "output/file.jsonl"
        mock_blob.download_as_text.return_value = '{"response": {"score": 4.0}}'
        mock_bucket.list_blobs.return_value = [mock_blob]

        with patch("src.competencies.scoring_pipeline._parse_scoring_results_gcs") as mock_parse:
            mock_parse.return_value = ([(1, 10, "Python", 4.0, "Good")], {1: {"total_tokens": 10}})

            with patch("src.competencies.scoring_pipeline._apply_scoring_results", new_callable=AsyncMock) as mock_apply:
                mock_apply.return_value = (1, 0, "")

                with patch("src.competencies.scoring_pipeline.log_finops", new_callable=AsyncMock) as mock_finops:
                    await scoring_pipeline.bg_bulk_scoring_vertex([1], {"Authorization": "Bearer token"})

                    mock_vertex_client.batches.create.assert_called_once()
                    mock_apply.assert_called_once()
                    mock_finops.assert_called_once()
                    from unittest.mock import call
                    mock_set_scheduler.assert_has_calls([call(True), call(False)])
