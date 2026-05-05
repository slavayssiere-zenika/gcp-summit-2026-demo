import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from src.services.tree_resolution import TreeResolver
import json

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def mock_drive_api():
    return AsyncMock()

@pytest.fixture
def mock_redis():
    return MagicMock()

@pytest.fixture
def resolver(mock_db, mock_drive_api, mock_redis):
    return TreeResolver(mock_db, mock_drive_api, mock_redis)

def test_get_cached_roots_hit(resolver, mock_redis):
    mock_redis.get.return_value = b'[{"id": 1}]'
    roots = resolver._get_cached_roots()
    assert roots == [{"id": 1}]

def test_get_cached_roots_corrupt(resolver, mock_redis):
    mock_redis.get.return_value = b'corrupt'
    roots = resolver._get_cached_roots()
    assert roots is None
    mock_redis.delete.assert_called_once()

def test_set_cached_roots(resolver, mock_redis):
    resolver._set_cached_roots([{"id": 1}])
    mock_redis.set.assert_called_once()

def test_invalidate_roots_cache(resolver, mock_redis):
    resolver.invalidate_roots_cache()
    mock_redis.delete.assert_called_once()

@pytest.mark.asyncio
async def test_load_roots_from_cache(resolver, mock_redis):
    mock_redis.get.return_value = b'[{"id": 1}]'
    roots = await resolver.load_roots()
    assert len(roots) == 1

@pytest.mark.asyncio
async def test_load_roots_from_db(resolver, mock_redis, mock_db):
    mock_redis.get.return_value = None
    
    class MockFolder:
        id = 1
        google_folder_id = "folder1"
        tag = "tag1"
        folder_name = "name1"
        excluded_folders = []
        
    mock_result = MagicMock()
    mock_result.scalars().all.return_value = [MockFolder()]
    mock_db.execute.return_value = mock_result
    
    roots = await resolver.load_roots()
    assert len(roots) == 1
    assert roots[0]["google_folder_id"] == "folder1"

@pytest.mark.asyncio
async def test_resolve_root_and_parent_found_in_cache(resolver, mock_redis):
    mock_redis.get.side_effect = lambda k: b"folder1" if "drive:name" in k else None
    
    root, parent_id, parent_name = await resolver.resolve_root_and_parent(
        "f1", [{"id": 1, "google_folder_id": "f1", "tag": "FR"}]
    )
    
    assert root["id"] == 1
    assert parent_id == "f1"

@pytest.mark.asyncio
async def test_resolve_root_and_parent_excluded(resolver, mock_redis, mock_drive_api):
    def redis_get(k):
        if "drive:name" in k: return b"child_folder"
        return None
    mock_redis.get.side_effect = redis_get
    
    mock_drive_api.get_folder_meta.return_value = {"name": "child_folder", "parents": ["f_root"]}
    
    root, parent_id, parent_name = await resolver.resolve_root_and_parent(
        "f_child", [{"id": 1, "google_folder_id": "f_root", "tag": "FR", "excluded_folders": ["child_folder"]}]
    )
    
    assert root is None

@pytest.mark.asyncio
async def test_resolve_root_and_parent_drive_api(resolver, mock_redis, mock_drive_api):
    # Setup redis to miss graph cache but provide name
    def redis_get(k):
        if "drive:name" in k: return b"child"
        return None
    mock_redis.get.side_effect = redis_get
    
    # Drive API will return a parent that is a root
    mock_drive_api.get_folder_meta.return_value = {"name": "child", "parents": ["f_root"]}
    
    roots = [{"id": 1, "google_folder_id": "f_root", "tag": "FR", "excluded_folders": []}]
    
    root, parent_id, parent_name = await resolver.resolve_root_and_parent("f_child", roots)
    
    assert root["id"] == 1
    assert parent_id == "f_child"

@pytest.mark.asyncio
async def test_resolve_root_and_parent_oos(resolver, mock_redis, mock_drive_api):
    def redis_get(k):
        if "drive:name" in k: return b"child"
        if "drive:oos" in k: return b"1"
        return None
    mock_redis.get.side_effect = redis_get
    
    root, parent_id, parent_name = await resolver.resolve_root_and_parent("f_child", [])
    assert root is None
import pytest
from unittest.mock import MagicMock, AsyncMock

def test_set_cached_roots_exception(resolver, mock_redis):
    mock_redis.set.side_effect = Exception("Redis error")
    resolver._set_cached_roots([{"id": 1}])
    # Should catch exception and not raise

@pytest.mark.asyncio
async def test_resolve_root_and_parent_fetch_name_from_drive(resolver, mock_redis, mock_drive_api):
    def redis_get(k):
        if "drive:name" in k: return None
        return None
    mock_redis.get.side_effect = redis_get
    
    mock_drive_api.get_folder_meta.side_effect = [
        {"name": "parent_name"},  # For the start_parent_id name
        {"parents": ["root1"], "name": "parent_name"}  # For the actual folder meta in loop
    ]
    
    roots = [{"id": 1, "google_folder_id": "root1", "tag": "FR", "excluded_folders": []}]
    root, parent_id, parent_name = await resolver.resolve_root_and_parent("start1", roots)
    
    assert root["id"] == 1
    assert parent_name == "parent_name"

@pytest.mark.asyncio
async def test_resolve_root_and_parent_cache_hit(resolver, mock_redis):
    def redis_get(k):
        if "drive:name" in k: return b"parent"
        if "drive:graph:f1" == k: return b"1"
        return None
    mock_redis.get.side_effect = redis_get
    
    roots = [{"id": 1, "google_folder_id": "root1", "tag": "FR", "excluded_folders": []}]
    root, parent_id, parent_name = await resolver.resolve_root_and_parent("f1", roots)
    
    assert root["id"] == 1
    assert parent_id == "f1"

@pytest.mark.asyncio
async def test_resolve_root_and_parent_cache_hit_missing_root(resolver, mock_redis, mock_drive_api):
    def redis_get(k):
        if "drive:name" in k: return b"parent"
        if "drive:graph:f1" == k: return b"2" # root 2 not in roots list
        return None
    mock_redis.get.side_effect = redis_get
    
    mock_drive_api.get_folder_meta.return_value = {"parents": ["root1"], "name": "f1"}
    
    roots = [{"id": 1, "google_folder_id": "root1", "tag": "FR", "excluded_folders": []}]
    root, parent_id, parent_name = await resolver.resolve_root_and_parent("f1", roots)
    
    assert root["id"] == 1
    assert parent_id == "f1"
    mock_redis.delete.assert_called_with("drive:graph:f1")

@pytest.mark.asyncio
async def test_resolve_root_and_parent_empty_meta(resolver, mock_redis, mock_drive_api):
    mock_redis.get.return_value = None
    mock_drive_api.get_folder_meta.return_value = None
    
    roots = [{"id": 1, "google_folder_id": "root1", "tag": "FR", "excluded_folders": []}]
    root, parent_id, parent_name = await resolver.resolve_root_and_parent("f1", roots)
    
    assert root is None
