"""
test_drive_service.py — Tests de la logique d'offboarding (détection et ingest) dans drive_api.
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from src.drive_service import DriveService
from src.models import DriveSyncState, DriveSyncStatus


@pytest.fixture
def mock_db():
    db = AsyncMock()
    return db

@pytest.fixture
def mock_google_client():
    client = MagicMock()
    return client

@pytest.fixture
def mock_pubsub():
    pubsub = AsyncMock()
    return pubsub

@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.get.return_value = None
    redis.delete.return_value = None
    return redis


@pytest.mark.asyncio
async def test_discover_delta_bottom_up_trashed_file_is_out_of_scope(mock_db, mock_google_client, mock_pubsub, mock_redis):
    """
    Vérifie qu'un fichier avec trashed=True ou sans dossier parent valide est flaggé OUT_OF_SCOPE.
    """
    mock_folders = MagicMock()
    mock_db.execute.return_value.scalars.return_value.all.return_value = []
    
    # Simuler DriveService
    with patch("src.services.tree_resolution.TreeResolver.load_roots", return_value=[{"id": 1, "google_folder_id": "root_id_1", "tag": "tag1", "folder_name": "Root", "excluded_folders": None}]), \
         patch("src.drive_service.get_redis", return_value=mock_redis), \
         patch("src.services.tree_resolution.TreeResolver.resolve_root_and_parent", new_callable=AsyncMock, return_value=(None, None, None)):
        service = DriveService(mock_db)
        
        # Simuler _get_drive_files_generator pour retourner un fichier trashed
        # Et simuler _resolve_root_and_folders
        fake_file = {"id": "trashed_file_id", "name": "CV Trashed", "mimeType": "application/vnd.google-apps.document", "trashed": True, "parents": ["parent1"], "modifiedTime": "2026-05-05T12:00:00Z"}
        
        # We need to mock drive_api.get_about and drive_api.list_files
        service.discovery_service.drive_api = AsyncMock()
        service.discovery_service.drive_api.get_about.return_value = {"user": {"emailAddress": "test@zenika.com"}}
        service.discovery_service.drive_api.list_files.return_value = {"files": [fake_file], "nextPageToken": None}
        
        # Simuler _process_single_file_delta
        # _process_single_file_delta doit marquer le fichier en OUT_OF_SCOPE car il existe déjà en BDD
        # on doit mocker l'existence du fichier
        mock_existing = DriveSyncState()
        mock_existing.google_file_id = "trashed_file_id"
        mock_existing.status = DriveSyncStatus.IMPORTED_CV.value
        mock_existing.google_folder_id = "parent1"
        mock_existing.source_tag = "tag1"
        
        # Le db.execute(select...).scalars().first() dans _process_single_file_delta
        mock_db_result = MagicMock()
        mock_db_result.scalar_one_or_none.return_value = mock_existing
        mock_db_result.scalars.return_value.first.return_value = mock_existing
        mock_db.execute.return_value = mock_db_result
        
        await service.discovery_service._discover_delta_bottom_up([{"id": 1, "google_folder_id": "root_id_1", "tag": "tag1"}])
        
        # Vérifier que le statut a bien été changé en OUT_OF_SCOPE
        assert mock_existing.status == DriveSyncStatus.OUT_OF_SCOPE.value
        mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_ingest_batch_publishes_delete_action_for_out_of_scope(mock_db, mock_google_client, mock_pubsub, mock_redis):
    """
    Vérifie que ingest_batch() publie un message avec action=delete pour les fichiers OUT_OF_SCOPE.
    """
    service = DriveService(mock_db)
    
    # Créer un état mock OUT_OF_SCOPE
    state1 = DriveSyncState()
    state1.google_file_id = "file123"
    state1.status = DriveSyncStatus.OUT_OF_SCOPE.value
    state1.file_name = "CV Sortant"
    state1.source_tag = "tag1"
    state1.folder_id = 1
    state1.file_type = "cv"
    state1.folder = MagicMock()
    state1.folder.tag = "tag1"
    state1.folder.folder_name = "Folder1"
    state1.parent_folder_name = "Folder1"
    
    fake_folder = MagicMock()
    fake_folder.tag = "tag1"
    fake_folder.folder_name = "Folder1"
    
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [state1]
    mock_result.scalars.return_value.first.return_value = fake_folder
    mock_db.execute.return_value = mock_result
    
    mock_publish = AsyncMock(return_value="message_id_1")
    service.pubsub = MagicMock()
    service.pubsub.publish_cv_import = mock_publish
    
    service._check_drive_accessibility = AsyncMock(return_value=True)
    
    with patch("src.ingestion_service.PUBSUB_CV_IMPORT_TOPIC", "projects/test-project/topics/test-topic"), \
         patch("src.ingestion_service.pubsub_v1.PublisherClient") as mock_publisher_class, \
         patch("src.ingestion_service.get_google_oidc_id_token", return_value="fake_oidc"), \
         patch("src.ingestion_service.get_m2m_jwt_token", new_callable=AsyncMock, return_value="fake_jwt"), \
         patch("src.ingestion_service.get_google_access_token", return_value="fake_token"):
         
        mock_publisher = mock_publisher_class.return_value
        mock_future = MagicMock()
        mock_future.result.return_value = "msg_id_1"
        mock_publisher.publish.return_value = mock_future
        
        await service.ingest_batch()
    
    # Vérifie l'appel au publisher
    mock_publisher.publish.assert_called_once()
    args, kwargs = mock_publisher.publish.call_args
    import json
    data = json.loads(args[1].decode("utf-8"))
    assert data["action"] == "delete"
    assert data["google_file_id"] == "file123"
    
    # Vérifie que le statut a été mis à jour après la publication
    assert state1.status == DriveSyncStatus.QUEUED
    mock_db.commit.assert_called()
