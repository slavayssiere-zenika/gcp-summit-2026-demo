import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
import sys
sys.path.append('.')
from src.discovery_service import DiscoveryService
from src.models import DriveFolder, DriveSyncState, DriveSyncStatus

async def main():
    mock_db = AsyncMock()
    mock_redis = MagicMock()
    mock_drive = MagicMock()
    
    with patch('src.discovery_service.TreeResolver') as mock_tree_resolver:
        service = DiscoveryService(mock_db, mock_drive, mock_redis)
        service.tree_resolver = mock_tree_resolver.return_value
        
    roots = [{"id": 1, "google_folder_id": "root1", "tag": "root_tag", "excluded_folders": []}]
    
    async def mock_db_execute(*args, **kwargs):
        mock_result = MagicMock()
        if "DriveSyncState" in str(args[0]):
            if "max" in str(args[0]):
                mock_result.scalar.return_value = datetime.now(timezone.utc)
            else:
                mock_existing_oos = MagicMock()
                mock_existing_oos.status = DriveSyncStatus.PENDING.value
                mock_result.scalars().first.return_value = mock_existing_oos
        return mock_result
    service.db.execute.side_effect = mock_db_execute
    
    service.drive_api.get_about = AsyncMock(return_value={"user": {"emailAddress": "test@test.com"}})
    
    files = [
        {"id": "file1", "name": "cv.docx", "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "modifiedTime": "2023-01-01T00:00:00Z", "version": "1", "parents": ["root1"]},
        {"id": "file2", "name": "cv2.doc", "mimeType": "application/vnd.google-apps.document", "modifiedTime": "2023-01-01T00:00:00Z", "version": "1", "parents": ["root1"], "trashed": True}
    ]
    
    service.drive_api.list_files = AsyncMock(side_effect=[{"files": files}, {}])
    service.tree_resolver.resolve_root_and_parent = AsyncMock(return_value=({"id": 1}, "root1", "root_tag"))
    
    res = await service._discover_delta_bottom_up(roots)
    print("RESULT:", res)

asyncio.run(main())
