import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from src.services.folder_service import FolderService
from src.schemas import FolderCreate, FolderUpdate


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def service(mock_db):
    return FolderService(mock_db)


@pytest.mark.asyncio
@patch('src.services.folder_service.delete_cache', new_callable=AsyncMock)
@patch('src.services.folder_service.get_drive_service')
async def test_add_folder_success(mock_get_drive, mock_delete_cache, service, mock_db):

    mock_drive = MagicMock()
    mock_get_drive.return_value = mock_drive
    mock_drive.files().get().execute.return_value = {"name": "Test Folder"}

    mock_result_existing = MagicMock()
    mock_result_existing.scalars().first.side_effect = [None, None]
    mock_db.execute.return_value = mock_result_existing

    folder_create = FolderCreate(google_folder_id="folders/123", tag="tag1", folder_name="Test")
    res = await service.add_folder(folder_create)

    assert res.google_folder_id == "123"
    assert res.tag == "tag1"
    assert res.folder_name == "Test Folder"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_add_folder_already_exists(service, mock_db):
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = True  # Folder exists
    mock_db.execute.return_value = mock_result

    folder_create = FolderCreate(google_folder_id="123", tag="tag1", folder_name="Test")
    with pytest.raises(HTTPException, match="already registered"):
        await service.add_folder(folder_create)


@pytest.mark.asyncio
@patch('src.services.folder_service.delete_cache', new_callable=AsyncMock)
async def test_update_folder_success(mock_delete_cache, service, mock_db):

    class MockFolder:
        id = 1
        tag = "old"
        excluded_folders = []

    existing_folder = MockFolder()

    mock_result = MagicMock()
    mock_result.scalars().first.side_effect = [existing_folder, None]  # Found folder, tag not conflicting
    mock_db.execute.return_value = mock_result

    update_data = FolderUpdate(tag="new_tag", excluded_folders=["excl"])
    res = await service.update_folder(1, update_data)

    assert res.tag == "new_tag"
    assert res.excluded_folders == ["excl"]
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_update_folder_not_found(service, mock_db):
    mock_result = MagicMock()
    mock_result.scalars().first.return_value = None
    mock_db.execute.return_value = mock_result

    with pytest.raises(HTTPException, match="not found"):
        await service.update_folder(1, FolderUpdate())


@pytest.mark.asyncio
async def test_list_folders_with_stats(service, mock_db):
    mock_scalar = MagicMock()
    mock_scalar.scalar.return_value = 1

    class MockFolder:
        id = 1

    mock_folders = MagicMock()
    mock_folders.scalars().all.return_value = [MockFolder()]

    class StatusMock:
        name = "PENDING"

    mock_stats = MagicMock()
    mock_stats.all.return_value = [(1, StatusMock(), 5)]

    mock_db.execute.side_effect = [mock_scalar, mock_folders, mock_stats]

    folders, stats, total = await service.list_folders_with_stats()

    assert total == 1
    assert len(folders) == 1
    assert stats[1]["PENDING"] == 5


@pytest.mark.asyncio
async def test_reset_folder_sync(service, mock_db):
    mock_result = MagicMock()
    mock_result.rowcount = 5
    mock_db.execute.return_value = mock_result

    res = await service.reset_folder_sync("tag1")
    assert res == 5
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
@patch('src.services.folder_service.delete_cache', new_callable=AsyncMock)
async def test_delete_folder(mock_delete_cache, service, mock_db):

    class MockFolder:
        id = 1

    mock_folder_res = MagicMock()
    mock_folder_res.scalars().first.return_value = MockFolder()

    mock_count = MagicMock()
    mock_count.scalar.return_value = 5

    mock_db.execute.side_effect = [mock_folder_res, mock_count, None]

    res = await service.delete_folder(1)
    assert res == 5
    mock_db.delete.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
@patch('shared.cache.clear_namespace', new_callable=AsyncMock)
@patch('shared.cache.delete_cache', new_callable=AsyncMock)
async def test_invalidate_drive_cache(mock_delete_cache, mock_clear_namespace):
    mock_clear_namespace.side_effect = [1, 1, 0]

    res = await FolderService.invalidate_drive_cache()
    assert res == 2
    mock_delete_cache.assert_called_with("drive:sync:rebuild_running")
