import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from fastapi.responses import Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from src.services.search_service import execute_search, scale_bulk_dependencies

@pytest.mark.asyncio
async def test_execute_search_with_skills_provided():
    db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    # Mocking rows with user_id=1, distance=0.1
    mock_row = MagicMock()
    mock_row.user_id = 1
    mock_result.all.return_value = [(mock_row, 0.1)]
    db.execute.return_value = mock_result
    
    genai_client = MagicMock()
    token_payload = {"sub": "test_user"}
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake_token")
    request = MagicMock()
    request.headers = {"Authorization": "Bearer fake_token"}
    response = Response()
    
    with patch("src.services.search_service.embed_content_with_retry", new_callable=AsyncMock) as mock_embed:
        mock_emb_res = MagicMock()
        mock_emb_res.embeddings = [MagicMock(values=[0.1]*3072)]
        mock_embed.return_value = mock_emb_res
        
        with patch("src.services.search_service.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            # Mock competencies/search
            mock_comp_resp = MagicMock()
            mock_comp_resp.status_code = 200
            mock_comp_resp.json.return_value = {"items": [{"id": 100}], "total": 1, "skip": 0, "limit": 1}
            
            # Mock competencies/100/users
            mock_users_ids_resp = MagicMock()
            mock_users_ids_resp.status_code = 200
            mock_users_ids_resp.json.return_value = [1]
            
            # Mock users_api/1
            mock_user_resp = MagicMock()
            mock_user_resp.status_code = 200
            mock_user_resp.json.return_value = {"full_name": "Test User", "email": "test@test.com", "username": "test", "is_active": True}
            
            mock_get.side_effect = [mock_comp_resp, mock_users_ids_resp, mock_user_resp]
            
            with patch("src.services.search_service.log_finops", new_callable=AsyncMock):
                res = await execute_search(
                    request=request,
                    response=response,
                    query="test",
                    skip=0,
                    limit=10,
                    skills=["Python"],
                    db=db,
                    token_payload=token_payload,
                    credentials=credentials,
                    genai_client=genai_client,
                    agency="agency_x"
                )
                assert res["total"] == 1
                assert res["items"][0]["user_id"] == 1
                assert res["items"][0]["full_name"] == "Test User"
                assert "X-Fallback-Full-Scan" in response.headers
                assert response.headers["X-Fallback-Full-Scan"] == "false"

@pytest.mark.asyncio
async def test_execute_search_llm_filter_extraction():
    db = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_row = MagicMock()
    mock_row.user_id = 2
    mock_result.all.return_value = [(mock_row, 0.2)]
    # Setup for missing embeddings check
    db.execute.side_effect = [MagicMock(scalar=lambda: 5), mock_result]
    
    genai_client = MagicMock()
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="fake_token")
    request = MagicMock()
    request.headers = {}
    response = Response()
    
    with patch("src.services.search_service.generate_content_with_retry", new_callable=AsyncMock) as mock_gen:
        mock_gen_res = MagicMock()
        mock_gen_res.text = '["Java"]'
        mock_gen_res.usage_metadata = {}
        mock_gen.return_value = mock_gen_res
        
        with patch("src.services.search_service.embed_content_with_retry", new_callable=AsyncMock) as mock_embed:
            mock_emb_res = MagicMock()
            mock_emb_res.embeddings = [MagicMock(values=[0.2]*3072)]
            mock_embed.return_value = mock_emb_res
            
            with patch("src.services.search_service.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                # Mock competencies/search to return empty
                mock_comp_resp = MagicMock()
                mock_comp_resp.status_code = 200
                mock_comp_resp.json.return_value = {"items": [], "total": 0, "skip": 0, "limit": 1}
                
                # Mock enrichment failure (500)
                mock_enrich_resp = MagicMock()
                mock_enrich_resp.status_code = 500
                
                mock_get.side_effect = [mock_comp_resp, mock_enrich_resp]
                
                with patch("src.services.search_service.log_finops", new_callable=AsyncMock):
                    res = await execute_search(
                        request=request,
                        response=response,
                        query="test java developer",
                        skip=0,
                        limit=10,
                        skills=[],
                        db=db,
                        token_payload={"sub": "user"},
                        credentials=credentials,
                        genai_client=genai_client
                    )
                    assert res["total"] == 1
                    assert res["items"][0]["user_id"] == 2
                    assert "full_name" not in res["items"][0]
                    assert response.headers["X-Missing-Embeddings-Count"] == "5"
                    assert response.headers["X-Fallback-Full-Scan"] == "true"

@pytest.mark.asyncio
async def test_scale_bulk_dependencies_success():
    with patch("src.services.search_service.cloudrun_v2.ServicesClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        
        mock_service = MagicMock()
        mock_service.template.scaling.min_instance_count = 0
        mock_client.get_service.return_value = mock_service
        
        mock_op = MagicMock()
        mock_op.operation.name = "op_id"
        mock_client.update_service.return_value = mock_op
        
        with patch("src.services.search_service.cloudrun_v2.UpdateServiceRequest", return_value=MagicMock()):
            with patch("src.services.search_service.GCP_PROJECT_ID", "test-proj"):
                with patch("src.services.search_service.CLOUDRUN_WORKSPACE", "dev"):
                    with patch("src.services.search_service.VERTEX_LOCATION", "europe-west1"):
                        await scale_bulk_dependencies(2)
                        
            assert mock_service.template.scaling.min_instance_count == 2
            assert mock_client.update_service.called

@pytest.mark.asyncio
async def test_scale_bulk_dependencies_error():
    with patch("src.services.search_service.cloudrun_v2.ServicesClient") as MockClient:
        mock_client = MagicMock()
        MockClient.return_value = mock_client
        
        mock_client.get_service.side_effect = Exception("API Down")
        
        with patch("src.services.search_service.GCP_PROJECT_ID", "test-proj"):
            with patch("src.services.search_service.CLOUDRUN_WORKSPACE", "dev"):
                with patch("src.services.search_service.VERTEX_LOCATION", "europe-west1"):
                    # Should not raise exception
                    await scale_bulk_dependencies(2)
