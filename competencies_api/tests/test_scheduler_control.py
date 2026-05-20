from unittest.mock import MagicMock, patch

import pytest
from src.competencies.scheduler_control import set_scoring_scheduler_enabled


@pytest.mark.asyncio
@patch("src.competencies.scheduler_control.GCP_PROJECT_ID", "")
async def test_set_scoring_scheduler_enabled_no_project():
    result = await set_scoring_scheduler_enabled(True)
    assert result is False


@pytest.mark.asyncio
@patch("src.competencies.scheduler_control.GCP_PROJECT_ID", "proj1")
@patch("src.competencies.scheduler_control.scheduler_v1")
async def test_set_scoring_scheduler_enabled_success_resume(mock_scheduler_v1):
    mock_client = MagicMock()
    mock_scheduler_v1.CloudSchedulerClient.return_value = mock_client

    result = await set_scoring_scheduler_enabled(True)
    assert result is True
    mock_client.resume_job.assert_called_once()
    mock_client.pause_job.assert_not_called()


@pytest.mark.asyncio
@patch("src.competencies.scheduler_control.GCP_PROJECT_ID", "proj1")
@patch("src.competencies.scheduler_control.scheduler_v1")
async def test_set_scoring_scheduler_enabled_success_pause(mock_scheduler_v1):
    mock_client = MagicMock()
    mock_scheduler_v1.CloudSchedulerClient.return_value = mock_client

    result = await set_scoring_scheduler_enabled(False)
    assert result is True
    mock_client.pause_job.assert_called_once()
    mock_client.resume_job.assert_not_called()


@pytest.mark.asyncio
@patch("src.competencies.scheduler_control.GCP_PROJECT_ID", "proj1")
@patch("src.competencies.scheduler_control.scheduler_v1")
async def test_set_scoring_scheduler_enabled_exception(mock_scheduler_v1):
    mock_scheduler_v1.CloudSchedulerClient.side_effect = Exception("API Error")

    result = await set_scoring_scheduler_enabled(True)
    assert result is False
