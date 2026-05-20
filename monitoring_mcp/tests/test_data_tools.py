import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tools.data_tools import (
    get_redis_invalidation_state_internal,
    execute_read_only_query_internal,
    inspect_pubsub_dlq_internal
)


@pytest.mark.asyncio
@patch('redis.from_url')
async def test_get_redis_invalidation_state_internal(mock_redis_from_url):
    mock_redis = MagicMock()
    mock_redis.scan.return_value = (0, [b"key1", b"key2"])
    mock_redis.ttl.return_value = 3600
    mock_redis_from_url.return_value = mock_redis

    result = await get_redis_invalidation_state_internal()
    assert result["status"] == "ok"
    assert result["matched_keys_count"] == 2
    assert "key1" in result["keys_sample"]
    assert result["keys_sample"]["key1"] == 3600


@pytest.mark.asyncio
async def test_execute_read_only_query_internal_forbidden():
    result = await execute_read_only_query_internal("DELETE FROM users")
    assert "error" in result
    assert "read-only" in result["error"]


@pytest.mark.asyncio
@patch('tools.data_tools.create_async_engine')
async def test_execute_read_only_query_internal_success(mock_create_engine):
    mock_engine = MagicMock()
    mock_engine.dispose = AsyncMock()
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()

    class MockResult:
        def mappings(self):
            class MockMappings:
                def all(self):
                    return [{"id": 1, "name": "test", "created_at": datetime.datetime.now()}]
            return MockMappings()

    mock_conn.execute.return_value = MockResult()
    mock_engine.connect.return_value.__aenter__.return_value = mock_conn
    mock_create_engine.return_value = mock_engine

    result = await execute_read_only_query_internal("SELECT * FROM users")
    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["rows"][0]["id"] == "1"


@pytest.mark.asyncio
@patch('google.cloud.pubsub_v1.SubscriberClient')
async def test_inspect_pubsub_dlq_internal(mock_subscriber_class):
    mock_subscriber = mock_subscriber_class.return_value
    mock_subscriber.subscription_path.return_value = "projects/test/subscriptions/sub"

    class MockMessage:
        def __init__(self, msg_id, data):
            self.message_id = msg_id
            self.publish_time = datetime.datetime.now()
            self.attributes = {"key": "val"}
            self.data = data

    class MockReceivedMessage:
        def __init__(self, ack_id, msg):
            self.ack_id = ack_id
            self.message = msg

    mock_res = MagicMock()
    mock_res.received_messages = [
        MockReceivedMessage("ack1", MockMessage("1", b"test data"))
    ]
    mock_subscriber.pull.return_value = mock_res

    result = await inspect_pubsub_dlq_internal()
    assert result["status"] == "ok"
    assert result["count"] == 1
    assert result["messages"][0]["message_id"] == "1"
    assert result["messages"][0]["data"] == "test data"

    # Verify modify_ack_deadline was called
    mock_subscriber.modify_ack_deadline.assert_called_once()
