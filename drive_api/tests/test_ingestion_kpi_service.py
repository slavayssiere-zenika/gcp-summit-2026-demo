import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.ingestion_kpi_service import IngestionKpiService
import datetime


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def service(mock_db):
    return IngestionKpiService(mock_db)


@pytest.mark.asyncio
@patch('src.services.ingestion_kpi_service._compute_kpi_metric')
@patch('src.services.ingestion_kpi_service.get_cache', new_callable=AsyncMock)
async def test_get_ingestion_stats(mock_get_cache, mock_compute, service, mock_db):
    mock_get_cache.return_value = None

    mock_compute.return_value = {"pct": 100, "status": "ok"}

    mock_result = MagicMock()
    mock_result.scalar.side_effect = [
        100,  # total
        90,  # imported
        5,   # errors
        2,   # pending
        1,   # queued
        1,   # processing
        1,   # ignored
        80,  # named
        70,  # linked
        15000,  # avg_ms
        datetime.datetime.now(datetime.timezone.utc),  # last_imported
        datetime.datetime.now(datetime.timezone.utc),  # last_processed
    ]
    mock_db.execute.return_value = mock_result

    res = await service.get_ingestion_stats()
    assert res["total_files"] == 100
    assert res["imported"] == 90
    assert res["grade"] in ["A", "B", "C", "D", "F"]


@pytest.mark.asyncio
async def test_get_folder_kpis(service, mock_db):
    class MockFolder:
        id = 1
        folder_name = "test"
        tag = "t"

    mock_result_folders = MagicMock()
    mock_result_folders.scalars().all.return_value = [MockFolder()]

    mock_result_scalars = MagicMock()
    mock_result_scalars.scalar.side_effect = [
        10,  # total
        8,  # imported
        1,  # errors
        1,  # pending
        0,  # queued
        0,  # processing
        0,  # ignored
        7,  # linked
        1000,  # avg_ms
        datetime.datetime.now(datetime.timezone.utc),  # last_import
    ]

    # We need execute to return different mocks based on the query.
    # A simple way is to use a side_effect that returns mock_result_folders on the first call,
    # and mock_result_scalars on subsequent calls.
    mock_db.execute.side_effect = [mock_result_folders] + [mock_result_scalars] * 10

    res = await service.get_folder_kpis()
    assert len(res) == 1
    assert res[0]["total"] == 10
    assert res[0]["imported"] == 8


@pytest.mark.asyncio
async def test_get_ingestion_history(service, mock_db):
    class MockRow:
        google_file_id = "1"
        file_name = "test"
        parent_folder_name = "test"
        user_id = 1
        queued_at = datetime.datetime.now(datetime.timezone.utc)
        imported_at = datetime.datetime.now(datetime.timezone.utc)
        processing_duration_ms = 1000

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [MockRow()]
    mock_db.execute.return_value = mock_result

    res = await service.get_ingestion_history()
    assert len(res) == 1
    assert res[0]["google_file_id"] == "1"


@pytest.mark.asyncio
@patch('src.services.ingestion_kpi_service._reset_errors_to_pending', new_callable=AsyncMock)
async def test_batch_retry(mock_reset, service):
    mock_reset.return_value = {"status": "ok"}
    res = await service.batch_retry()
    assert res["status"] == "ok"


@pytest.mark.asyncio
@patch('src.services.ingestion_kpi_service.delete_cache', new_callable=AsyncMock)
async def test_quality_gate_batch(mock_delete_cache, service, mock_db):

    mock_result = MagicMock()
    mock_result.fetchall.side_effect = [
        [("1",)],  # ids_no_user
        [("2",)],  # ids_no_name
        [("3",)],  # ids_errors
    ]
    mock_db.execute.return_value = mock_result

    res = await service.quality_gate_batch()
    assert res["total_queued"] == 3
    assert res["reason_breakdown"]["user_id_manquant"] == 1
    mock_db.commit.assert_called_once()
