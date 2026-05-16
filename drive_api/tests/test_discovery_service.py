import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.discovery_service import DiscoveryService
from src.models import DriveSyncStatus
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture
def mock_db():
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def mock_drive():
    return MagicMock()


@pytest.fixture
def discovery_service(mock_db, mock_drive, mock_redis):
    # Patch TreeResolver to not hit redis/db inside init if needed
    with patch('src.discovery_service.TreeResolver') as mock_tree_resolver:
        service = DiscoveryService(mock_db, mock_drive, mock_redis)
        service.tree_resolver = mock_tree_resolver.return_value
        return service


def test_invalidate_roots_cache(discovery_service):
    discovery_service.invalidate_roots_cache()
    discovery_service.tree_resolver.invalidate_roots_cache.assert_called_once()


def test_is_file_known(discovery_service, mock_redis):
    mock_redis.get.return_value = b"IMPORTED_CV"
    assert discovery_service._is_file_known("test_id") is True
    mock_redis.get.assert_called_with("drive:file:known:test_id")


def test_mark_file_known(discovery_service, mock_redis):
    discovery_service._mark_file_known("test_id")
    mock_redis.set.assert_called_with("drive:file:known:test_id", "IMPORTED_CV", ex=86400)


@pytest.mark.asyncio
async def test_discover_files_no_roots(discovery_service):
    discovery_service.tree_resolver.load_roots = AsyncMock(return_value=[])
    result = await discovery_service.discover_files()
    assert result == 0


@pytest.mark.asyncio
async def test_discover_files_force_full(discovery_service, mock_db):
    roots = [{"id": 1, "google_folder_id": "folder1", "tag": "test"}]
    discovery_service.tree_resolver.load_roots = AsyncMock(return_value=roots)
    discovery_service._discover_full_top_down = AsyncMock(return_value=5)

    result = await discovery_service.discover_files(force_full=True)

    assert result == 5
    discovery_service._discover_full_top_down.assert_called_once_with(roots)


@pytest.mark.asyncio
async def test_discover_files_uninitialized_roots(discovery_service, mock_db):
    roots = [{"id": 1, "google_folder_id": "folder1", "tag": "test"}]
    discovery_service.tree_resolver.load_roots = AsyncMock(return_value=roots)

    mock_folder = MagicMock()
    mock_folder.id = 1
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [mock_folder]
    mock_db.execute.return_value = mock_result

    discovery_service._discover_full_top_down = AsyncMock(return_value=2)
    discovery_service._discover_delta_bottom_up = AsyncMock(return_value=3)

    result = await discovery_service.discover_files(force_full=False)

    assert result == 5
    discovery_service._discover_full_top_down.assert_called_once()
    discovery_service._discover_delta_bottom_up.assert_called_once()


@pytest.mark.asyncio
async def test_discover_files_delta_only(discovery_service, mock_db):
    roots = [{"id": 1, "google_folder_id": "folder1", "tag": "test"}]
    discovery_service.tree_resolver.load_roots = AsyncMock(return_value=roots)

    mock_result = MagicMock()
    mock_result.scalars().all.return_value = []
    mock_db.execute.return_value = mock_result

    discovery_service._discover_delta_bottom_up = AsyncMock(return_value=3)

    result = await discovery_service.discover_files(force_full=False)

    assert result == 3
    discovery_service._discover_delta_bottom_up.assert_called_once()


@pytest.mark.asyncio
async def test_discover_full_top_down(discovery_service, mock_redis):
    roots = [{"id": 1, "google_folder_id": "root1", "tag": "root_tag", "excluded_folders": ["excluded"]}]

    files_page_1 = [
        {"id": "file1", "name": "cv.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "modifiedTime": "2023-01-01T00:00:00Z", "version": "1"},
        {"id": "folder2", "name": "subfolder", "mimeType": "application/vnd.google-apps.folder"}
    ]
    files_page_2 = [
        {"id": "file2", "name": "cv2.doc", "mimeType": "application/vnd.google-apps.document", "modifiedTime": "2023-01-01T00:00:00Z", "version": "1"},
        {"id": "folder3", "name": "Excluded", "mimeType": "application/vnd.google-apps.folder"}
    ]

    # Setup mock to return results based on query (it queries root1 then folder2)
    discovery_service.drive_api.list_files = AsyncMock(side_effect=[
        {"files": files_page_1},  # Results for root1
        {"files": files_page_2}  # Results for folder2
    ])

    result = await discovery_service._discover_full_top_down(roots)

    assert result == 2  # 2 CVs discovered
    assert mock_redis.pipeline.called  # Called for folder caching
    assert mock_redis.set.called  # Called for excluded folder OOS


@pytest.mark.asyncio
async def test_discover_full_top_down_db_error(discovery_service):
    roots = [{"id": 1, "google_folder_id": "root1", "tag": "root_tag", "excluded_folders": []}]

    files_page_1 = [
        {"id": "file1", "name": "cv.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "modifiedTime": "2023-01-01T00:00:00Z", "version": "1"},
    ]

    discovery_service.drive_api.list_files = AsyncMock(return_value={"files": files_page_1})
    discovery_service.db.execute.side_effect = Exception("DB error")

    result = await discovery_service._discover_full_top_down(roots)

    assert result == 0
    discovery_service.db.rollback.assert_called_once()


@pytest.mark.asyncio
async def test_discover_delta_bottom_up(discovery_service, mock_redis):
    roots = [{"id": 1, "google_folder_id": "root1", "tag": "root_tag", "excluded_folders": []}]

    mock_db_result = MagicMock()
    mock_db_result.scalar.return_value = datetime.now(timezone.utc)
    discovery_service.db.execute.return_value = mock_db_result

    discovery_service.drive_api.get_about = AsyncMock(return_value={"user": {"emailAddress": "test@test.com"}})

    files = [
        {"id": "file1", "name": "cv.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "modifiedTime": "2023-01-01T00:00:00Z", "version": "1", "parents": ["root1"]},
        {"id": "file2", "name": "cv2.doc", "mimeType": "application/vnd.google-apps.document", "modifiedTime": "2023-01-01T00:00:00Z", "version": "1", "parents": ["root1"], "trashed": True}
    ]

    # 2 corpora: allDrives, user
    discovery_service.drive_api.list_files = AsyncMock(side_effect=[
        {"files": files},  # allDrives
        {}  # user
    ])

    discovery_service.tree_resolver.resolve_root_and_parent = AsyncMock(return_value=({"id": 1}, "root1", "root_tag"))

    # Mocking existing file check for file2 to put it in OUT_OF_SCOPE
    mock_existing_oos = MagicMock()
    mock_existing_oos.status = DriveSyncStatus.PENDING.value

    async def mock_db_execute(*args, **kwargs):
        mock_result = MagicMock()
        if "drive_sync_states" in str(args[0]).lower() or "drivesyncstate" in str(args[0]).lower():
            if "max" in str(args[0]).lower():
                mock_result.scalar.return_value = datetime.now(timezone.utc)
            mock_result.scalars().first.return_value = mock_existing_oos
        return mock_result
    discovery_service.db.execute.side_effect = mock_db_execute

    result = await discovery_service._discover_delta_bottom_up(roots)

    # 1 file is new/updated, 1 is trashed and put to OOS (but new_discoveries only counts new)
    assert result == 1


@pytest.mark.asyncio
async def test_discover_delta_bottom_up_auth_loss(discovery_service):
    discovery_service.drive_api.get_about = AsyncMock(side_effect=Exception("Auth Loss"))

    mock_db_result = MagicMock()
    mock_db_result.scalar.return_value = None
    discovery_service.db.execute.return_value = mock_db_result

    with pytest.raises(Exception):
        await discovery_service._discover_delta_bottom_up([])


@pytest.mark.asyncio
async def test_discover_full_top_down_with_pagination(discovery_service, mock_redis):
    roots = [{"id": 1, "google_folder_id": "root1", "tag": "root_tag", "excluded_folders": []}]

    files_page_1 = [
        {"id": "file1", "name": "cv1.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "modifiedTime": "2023-01-01T00:00:00Z", "version": "1"},
    ]
    files_page_2 = [
        {"id": "file2", "name": "cv2.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "modifiedTime": "2023-01-01T00:00:00Z", "version": "1"},
    ]

    # Return two pages for the same query using nextPageToken
    discovery_service.drive_api.list_files = AsyncMock(side_effect=[
        {"files": files_page_1, "nextPageToken": "token1"},
        {"files": files_page_2}
    ])

    result = await discovery_service._discover_full_top_down(roots)

    # 2 calls to list_files, one with token=None and one with token="token1"
    assert discovery_service.drive_api.list_files.call_count == 2
    assert result == 2
