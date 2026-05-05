import pytest
from unittest.mock import MagicMock, patch
from src.services.google_api_client import DriveApiClient
import asyncio

@pytest.fixture
def mock_drive():
    return MagicMock()

@pytest.fixture
def client(mock_drive):
    return DriveApiClient(mock_drive)

@pytest.mark.asyncio
async def test_get_folder_meta_success(client, mock_drive):
    mock_drive.files().get().execute.return_value = {"id": "1", "name": "folder1"}
    
    res = await client.get_folder_meta("1")
    assert res["name"] == "folder1"
    mock_drive.files().get.assert_called_with(fileId="1", fields="parents,name", supportsAllDrives=True)

@pytest.mark.asyncio
async def test_get_folder_meta_retry(client, mock_drive):
    mock_drive.files().get().execute.side_effect = [Exception("error"), {"id": "1", "name": "folder1"}]
    
    with patch("asyncio.sleep", return_value=None):
        res = await client.get_folder_meta("1")
        assert res["name"] == "folder1"
        assert mock_drive.files().get().execute.call_count == 2

@pytest.mark.asyncio
async def test_get_folder_meta_failure(client, mock_drive):
    mock_drive.files().get().execute.side_effect = Exception("fatal error")
    
    with patch("asyncio.sleep", return_value=None):
        with pytest.raises(Exception):
            await client.get_folder_meta("1")

@pytest.mark.asyncio
async def test_list_files_success(client, mock_drive):
    mock_drive.files().list().execute.return_value = {"files": [{"id": "1"}], "nextPageToken": None}
    
    res = await client.list_files("q", None)
    assert len(res["files"]) == 1
    mock_drive.files().list.assert_called_with(
        q="q", spaces="drive", corpora="allDrives", includeItemsFromAllDrives=True,
        supportsAllDrives=True, fields="nextPageToken, files(id, name, mimeType, modifiedTime, version, parents, trashed)",
        pageToken=None, pageSize=1000
    )

@pytest.mark.asyncio
async def test_list_files_retry(client, mock_drive):
    mock_drive.files().list().execute.side_effect = [Exception("error"), {"files": []}]
    
    with patch("asyncio.sleep", return_value=None):
        res = await client.list_files("q", None)
        assert "files" in res

@pytest.mark.asyncio
async def test_list_files_failure(client, mock_drive):
    mock_drive.files().list().execute.side_effect = Exception("error")
    
    with patch("asyncio.sleep", return_value=None):
        with pytest.raises(Exception):
            await client.list_files("q", None)

@pytest.mark.asyncio
async def test_get_about(client, mock_drive):
    mock_drive.about().get().execute.return_value = {"user": "test"}
    res = await client.get_about()
    assert res["user"] == "test"
