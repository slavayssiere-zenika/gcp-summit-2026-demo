import pytest
from unittest.mock import AsyncMock, patch
import json
from src.cvs.task_state import ReanalysisTaskState, TreeTaskState
from datetime import datetime, timedelta


@pytest.fixture
def mock_redis():
    with patch("src.cvs.task_state.get_state_redis_client") as mock_get_client:
        mock_instance = AsyncMock()
        mock_get_client.return_value = mock_instance
        yield mock_instance


@pytest.mark.asyncio
async def test_reanalysis_initialize(mock_redis):
    state = ReanalysisTaskState()
    res = await state.initialize_task(10, "test")
    assert res["status"] == "running"
    mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_reanalysis_update_progress(mock_redis):
    state = ReanalysisTaskState()
    mock_redis.get.return_value = json.dumps(
        {"processed_count": 0, "error_count": 0, "mismatch_count": 0, "logs": [], "errors": [], "total_cvs": 10})
    await state.update_progress(1, 1, 1, "test log", "error")
    mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_reanalysis_mark_failed(mock_redis):
    state = ReanalysisTaskState()
    mock_redis.get.return_value = json.dumps({"status": "running", "logs": [], "errors": []})
    await state.mark_failed("error msg")
    mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_reanalysis_is_task_running(mock_redis):
    state = ReanalysisTaskState()
    mock_redis.get.return_value = json.dumps({"status": "running", "updated_at": datetime.now().isoformat()})
    assert await state.is_task_running() is True

    # Stale
    stale_time = (datetime.now() - timedelta(minutes=40)).isoformat()
    mock_redis.get.return_value = json.dumps({"status": "running", "updated_at": stale_time, "logs": [], "errors": []})
    assert await state.is_task_running() is False


@pytest.mark.asyncio
async def test_reanalysis_force_reset(mock_redis):
    state = ReanalysisTaskState()
    await state.force_reset()
    mock_redis.delete.assert_called_once()


@pytest.mark.asyncio
async def test_tree_initialize(mock_redis):
    state = TreeTaskState()
    res = await state.initialize_task()
    assert res["status"] == "running"
    mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_tree_update_progress(mock_redis):
    state = TreeTaskState()
    mock_redis.get.return_value = json.dumps({"logs": []})

    await state.update_progress(
        new_log="hello", tree={}, usage={}, error="err", status="error",
        map_result={}, res_tree={}, completed_pillar="p1", sweep_result=[],
        missing_competencies=[], mode="batch", batch_job_id="123", batch_step="map",
        completed_pillars=["p1"], service_token="tkn", quality_report={}
    )
    mock_redis.set.assert_called_once()


@pytest.mark.asyncio
async def test_tree_is_task_running(mock_redis):
    state = TreeTaskState()
    mock_redis.get.return_value = json.dumps({"status": "running"})
    assert await state.is_task_running() is True
