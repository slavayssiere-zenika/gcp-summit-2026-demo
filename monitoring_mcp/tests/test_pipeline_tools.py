import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from tools.pipeline_tools import (
    check_component_health_internal,
    check_all_components_health_internal,
    get_ingestion_pipeline_status_internal
)

@pytest.mark.asyncio
@patch('redis.from_url')
async def test_check_component_health_redis_success(mock_redis_from_url):
    mock_redis = MagicMock()
    mock_redis.ping.return_value = True
    mock_redis_from_url.return_value = mock_redis
    
    res = await check_component_health_internal("redis-cache")
    assert res["status"] == "healthy"
    assert "PING successful" in res["message"]

@pytest.mark.asyncio
@patch('google.cloud.bigquery.Client')
async def test_check_component_health_bigquery_success(mock_bq_class):
    mock_bq = mock_bq_class.return_value
    mock_bq.list_datasets.return_value = []
    
    res = await check_component_health_internal("bigquery-finops")
    assert res["status"] == "healthy"

@pytest.mark.asyncio
@patch('httpx.AsyncClient.get', new_callable=AsyncMock)
async def test_check_component_health_ilb_success(mock_get):
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_get.return_value = mock_res
    
    res = await check_component_health_internal("users-api")
    assert res["status"] == "healthy"
    assert "users" in res["url"]

@pytest.mark.asyncio
@patch('tools.infra_tools.list_gcp_services_internal', new_callable=AsyncMock)
async def test_check_component_health_not_found(mock_list):
    mock_list.return_value = []
    res = await check_component_health_internal("unknown-service")
    assert res["status"] == "not_found"

@pytest.mark.asyncio
@patch('tools.pipeline_tools.check_component_health_internal', new_callable=AsyncMock)
@patch('tools.infra_tools.list_gcp_services_internal', new_callable=AsyncMock)
async def test_check_all_components_health(mock_list_services, mock_check):
    mock_list_services.return_value = [{"name": "test-service"}]
    mock_check.return_value = {"status": "healthy"}
    
    res = await check_all_components_health_internal()
    assert isinstance(res, list)
    assert len(res) == 4  # 1 from list + redis + alloydb + bq

@pytest.mark.asyncio
@patch('httpx.AsyncClient.get', new_callable=AsyncMock)
async def test_get_ingestion_pipeline_status_success(mock_get):
    mock_res = MagicMock()
    mock_res.raise_for_status = MagicMock()
    mock_res.json.return_value = {
        "errors": 1,
        "queued": 2,
        "processing": 3,
        "pending": 4,
        "imported": 10,
        "total_files_scanned": 20
    }
    mock_get.return_value = mock_res
    
    res = await get_ingestion_pipeline_status_internal()
    assert res["status"] == "ok"
    assert res["pipeline"]["errors"] == 1
    assert any("en erreur" in r for r in res["recommendations"])
    assert any("en file Pub/Sub" in r for r in res["recommendations"])
