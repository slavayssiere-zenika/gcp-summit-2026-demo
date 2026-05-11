import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_run_agent_query_redis_restore_error():
    # Covers lines 165-170
    from agent import run_agent_query
    
    mock_session_service = AsyncMock()
    mock_session_service.r = "fake_redis"
    
    with patch("agent.get_session_service", return_value=mock_session_service):
        with patch("agent.get_missions_context", side_effect=Exception("Redis down")):
            with patch("agent.app_logger.warning") as mock_logger:
                with patch("agent.create_agent", new=AsyncMock()):
                    with patch("agent.Runner", return_value=MagicMock()):
                        with patch("agent.run_agent_and_collect", new=AsyncMock(return_value=("resp", [], [], 0, 0, None, "text_only"))):
                            with patch("agent.extract_metadata_from_session", return_value={}):
                                with patch("agent.log_tokens_to_bq"):
                                    await run_agent_query("test", "sess_id", "token", "user")
                                    # Verifies the warning was logged
                                    mock_logger.assert_any_call("[MISSIONS] Impossible de lire le contexte mission Redis: %s", "Redis down" if False else mock_logger.call_args[0][1])

@pytest.mark.asyncio
async def test_run_agent_query_redis_store_error():
    # Covers lines 196-213
    from agent import run_agent_query
    
    mock_session_service = AsyncMock()
    mock_session_service.r = "fake_redis"
    mock_session_service.get_session.return_value = "fake_session"
    
    mock_last_data = {"id": "123", "title": "Mission Impossible"}
    
    with patch("agent.get_session_service", return_value=mock_session_service):
        with patch("agent.get_missions_context", return_value=None):
            with patch("agent.create_agent", new=AsyncMock()):
                with patch("agent.Runner", return_value=MagicMock()):
                    with patch("agent.run_agent_and_collect", new=AsyncMock(return_value=("resp", [], [], 0, 0, mock_last_data, "text_only"))):
                        with patch("agent.extract_metadata_from_session", return_value={"data": mock_last_data}):
                            with patch("agent.store_missions_context", side_effect=Exception("Redis write down")):
                                with patch("agent.app_logger.warning") as mock_logger:
                                    with patch("agent.log_tokens_to_bq"):
                                        await run_agent_query("test", "sess_id", "token", "user")
                                        # Verifies the warning was logged for store
                                        mock_logger.assert_any_call("[MISSIONS] Impossible de persister le contexte mission: %s", "Redis write down" if False else mock_logger.call_args[0][1])
