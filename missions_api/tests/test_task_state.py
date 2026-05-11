import pytest
import json
from unittest.mock import AsyncMock
from src.missions.task_state import MissionTaskState

@pytest.mark.asyncio
async def test_task_state_lifecycle(mocker):
    # Mock redis module
    mock_redis = AsyncMock()
    mocker.patch("src.missions.task_state.redis.from_url", return_value=mock_redis)

    ts = MissionTaskState()

    # Test initialize_task
    task_data = await ts.initialize_task("task123", "My title")
    assert task_data["task_id"] == "task123"
    assert task_data["title"] == "My title"
    assert task_data["status"] == "processing"
    mock_redis.setex.assert_called()

    # Test get_task none
    mock_redis.get.return_value = None
    data = await ts.get_task("task123")
    assert data is None

    # Test get_task exists
    mock_redis.get.return_value = json.dumps(task_data)
    data = await ts.get_task("task123")
    assert data["task_id"] == "task123"

    # Test update_status_success (needs get_task to return valid json)
    mock_redis.get.return_value = json.dumps(task_data)
    await ts.update_status_success("task123", 99)
    # Check what was saved
    saved_json = mock_redis.setex.call_args[0][2]
    saved_data = json.loads(saved_json)
    assert saved_data["status"] == "completed"
    assert saved_data["mission_id"] == 99

    # Test update_status_failed
    mock_redis.get.return_value = json.dumps(task_data)
    await ts.update_status_failed("task123", "Big Error")
    saved_json = mock_redis.setex.call_args[0][2]
    saved_data = json.loads(saved_json)
    assert saved_data["status"] == "failed"
    assert saved_data["error"] == "Big Error"

