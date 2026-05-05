import pytest
import json
from unittest.mock import MagicMock

from tools.market_tools import handle_get_top_market_skills, handle_get_market_demand_volume

@pytest.mark.asyncio
async def test_handle_get_top_market_skills():
    mock_client = MagicMock()
    mock_query_job = MagicMock()
    
    class MockRow:
        def __init__(self, skill, demand_count):
            self.skill = skill
            self.demand_count = demand_count
            
    mock_query_job.result.return_value = [
        MockRow("Python", 150),
        MockRow("React", 100)
    ]
    mock_client.query.return_value = mock_query_job
    
    args = {"category": "Backend", "limit": 2}
    result = await handle_get_top_market_skills(args, mock_client, "project.dataset.table")
    
    assert len(result) == 1
    assert result[0].type == "text"
    
    data = json.loads(result[0].text)
    assert len(data) == 2
    assert data[0]["skill"] == "Python"
    assert data[0]["demand_count"] == 150
    assert data[1]["skill"] == "React"

@pytest.mark.asyncio
async def test_handle_get_market_demand_volume():
    mock_client = MagicMock()
    mock_query_job = MagicMock()
    
    class MockRow:
        def __init__(self, volume):
            self.volume = volume
            
    mock_query_job.result.return_value = [MockRow(500)]
    mock_client.query.return_value = mock_query_job
    
    args = {"category": "Backend"}
    result = await handle_get_market_demand_volume(args, mock_client, "project.dataset.table")
    
    assert len(result) == 1
    assert result[0].type == "text"
    
    data = json.loads(result[0].text)
    assert data["category"] == "Backend"
    assert data["volume"] == 500

@pytest.mark.asyncio
async def test_handle_get_market_demand_volume_empty():
    mock_client = MagicMock()
    mock_query_job = MagicMock()
    
    mock_query_job.result.return_value = []
    mock_client.query.return_value = mock_query_job
    
    args = {"category": "Unknown"}
    result = await handle_get_market_demand_volume(args, mock_client, "project.dataset.table")
    
    data = json.loads(result[0].text)
    assert data["category"] == "Unknown"
    assert data["volume"] == 0
