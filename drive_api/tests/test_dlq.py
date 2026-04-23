import pytest
import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from src.schemas import FileStateResponse
from src.models import DriveSyncState, DriveSyncStatus
import json
import base64
from main import app
from database import get_db
import pytest_asyncio

@pytest_asyncio.fixture(autouse=True)
async def override_db_dependency(db_session):
    original = app.dependency_overrides.get(get_db)
    
    # Clean up before test
    from sqlalchemy import delete
    await db_session.execute(delete(DriveSyncState))
    await db_session.commit()
    
    async def override():
        yield db_session
    app.dependency_overrides[get_db] = override
    yield
    if original:
        app.dependency_overrides[get_db] = original
    else:
        app.dependency_overrides.pop(get_db, None)

@pytest.mark.asyncio
async def test_get_dlq_status_empty(async_client, mocker):
    mock_pubsub = mocker.patch("google.cloud.pubsub_v1.SubscriberClient")
    mock_subscriber = mock_pubsub.return_value
    
    mock_pull_response = mocker.Mock()
    mock_pull_response.received_messages = []
    
    async def mock_to_thread(func, *args, **kwargs):
        if func == mock_subscriber.pull:
            return mock_pull_response
        return func(*args, **kwargs)

    mocker.patch("asyncio.to_thread", side_effect=mock_to_thread)

    response = await async_client.get("/dlq/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["message_count"] == 0
    assert len(data["files"]) == 0
    assert mock_subscriber.close.called

@pytest.mark.asyncio
async def test_get_dlq_status_with_messages(async_client, mocker, db_session: AsyncSession):
    # Setup test file in DB
    db_file = DriveSyncState(
        google_file_id="G12345",
        status=DriveSyncStatus.ERROR,
        error_message="Fail"
    )
    db_session.add(db_file)
    await db_session.commit()
    
    mock_pubsub = mocker.patch("google.cloud.pubsub_v1.SubscriberClient")
    mock_subscriber = mock_pubsub.return_value
    
    mock_pull_response = mocker.Mock()
    
    msg_valid = mocker.Mock()
    msg_valid.ack_id = "ack_1"
    msg_valid.message.message_id = "msg_1"
    msg_valid.message.data = base64.b64encode(json.dumps({"google_file_id": "G12345"}).encode())
    
    msg_invalid = mocker.Mock()
    msg_invalid.ack_id = "ack_2"
    msg_invalid.message.message_id = "msg_2"
    msg_invalid.message.data = base64.b64encode(json.dumps({"wrong_key": "val"}).encode())
    
    mock_pull_response.received_messages = [msg_valid, msg_invalid]
    
    async def mock_to_thread(func, *args, **kwargs):
        if func == mock_subscriber.pull:
            return mock_pull_response
        return mocker.Mock()

    mocker.patch("asyncio.to_thread", side_effect=mock_to_thread)

    response = await async_client.get("/dlq/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["message_count"] == 2
    assert len(data["files"]) == 1
    assert data["files"][0]["google_file_id"] == "G12345"
    assert len(data["unknown_files"]) == 1
    assert mock_subscriber.close.called

@pytest.mark.asyncio
async def test_replay_dlq_batches_ack(async_client, mocker, db_session: AsyncSession):
    mock_pubsub = mocker.patch("google.cloud.pubsub_v1.SubscriberClient")
    mock_subscriber = mock_pubsub.return_value
    
    # 2000 messages (forces 2 batches for ack)
    messages = []
    
    for i in range(2000):
        msg = mocker.Mock()
        msg.ack_id = f"ack_{i}"
        msg.message.message_id = f"msg_{i}"
        msg.message.data = base64.b64encode(json.dumps({"google_file_id": f"G_{i}"}).encode())
        messages.append(msg)
        
        db_file = DriveSyncState(
            google_file_id=f"G_{i}",
            status=DriveSyncStatus.ERROR,
            error_message="Fail"
        )
        db_session.add(db_file)
        
    await db_session.commit()

    mock_pull_response_1 = mocker.Mock()
    mock_pull_response_1.received_messages = messages[:1000]
    
    mock_pull_response_2 = mocker.Mock()
    mock_pull_response_2.received_messages = messages[1000:]
    
    mock_pull_response_3 = mocker.Mock()
    mock_pull_response_3.received_messages = []
    
    pull_responses = [mock_pull_response_1, mock_pull_response_2, mock_pull_response_3]
    pull_idx = 0
    
    ack_calls = []

    async def mock_to_thread(func, *args, **kwargs):
        nonlocal pull_idx
        if func == mock_subscriber.pull:
            res = pull_responses[pull_idx]
            pull_idx += 1
            return res
        if func == mock_subscriber.acknowledge:
            ack_calls.append(kwargs["request"]["ack_ids"])
            return None
        return mocker.Mock()

    mocker.patch("asyncio.to_thread", side_effect=mock_to_thread)

    response = await async_client.post("/dlq/replay")
    
    assert response.status_code == 200
    data = response.json()
    assert data["dlq_messages_pulled"] == 2000
    assert data["files_reset_to_pending"] == 2000
    assert len(ack_calls) == 2
    assert len(ack_calls[0]) == 1000
    assert len(ack_calls[1]) == 1000
    
    assert mock_subscriber.close.called

@pytest.mark.asyncio
async def test_delete_dlq_message_direct_ack(async_client, mocker):
    mock_pubsub = mocker.patch("google.cloud.pubsub_v1.SubscriberClient")
    mock_subscriber = mock_pubsub.return_value
    
    ack_called = False
    async def mock_to_thread(func, *args, **kwargs):
        nonlocal ack_called
        if func == mock_subscriber.acknowledge:
            ack_called = True
            return None
        return mocker.Mock()

    mocker.patch("asyncio.to_thread", side_effect=mock_to_thread)

    response = await async_client.delete("/dlq/message?ack_id=my_ack_123")
    
    assert response.status_code == 200
    assert ack_called
    assert mock_subscriber.close.called

@pytest.mark.asyncio
async def test_scheduled_retry_errors(async_client, mocker, db_session: AsyncSession):
    zombie = DriveSyncState(
        google_file_id="ZOMBIE",
        status=DriveSyncStatus.QUEUED,
        last_processed_at=datetime.datetime.utcnow() - datetime.timedelta(minutes=40)
    )
    error = DriveSyncState(
        google_file_id="ERRORFILE",
        status=DriveSyncStatus.ERROR,
        last_processed_at=datetime.datetime.utcnow()
    )
    
    db_session.add(zombie)
    db_session.add(error)
    await db_session.commit()
    
    response = await async_client.post("/scheduled/retry-errors")
    
    assert response.status_code == 200
    data = response.json()
    assert data["errors_reset"] == 1
    assert data["zombies_reset"] == 1
    assert data["total_reset"] == 2
