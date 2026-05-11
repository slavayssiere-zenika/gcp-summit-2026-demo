import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.embedding_service import reindex_embeddings_bg

@pytest.mark.asyncio
async def test_reindex_embeddings_bg_no_client():
    # Should exit early
    with patch("src.services.embedding_service.logger.error") as mock_logger:
        await reindex_embeddings_bg("tag", 1, "token", None)
        mock_logger.assert_called_with("[REINDEX] Client Gemini non configuré — re-indexation annulée.")

@pytest.mark.asyncio
async def test_reindex_embeddings_bg_success():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    
    mock_profile = MagicMock()
    mock_profile.user_id = 1
    mock_profile.source_tag = "tag"
    mock_profile.current_role = "Dev"
    mock_profile.years_of_experience = 5
    mock_profile.summary = "Test"
    mock_profile.competencies_keywords = ["Python"]
    mock_profile.educations = []
    mock_profile.missions = []
    mock_profile.raw_content = "Raw Test"
    mock_profile.semantic_embedding = None
    
    mock_result.scalars().all.return_value = [mock_profile]
    mock_db.execute.return_value = mock_result
    
    async def mock_get_db():
        yield mock_db
        
    with patch("src.services.embedding_service.database.get_db", mock_get_db):
        with patch("src.services.embedding_service.embed_content_with_retry", new_callable=AsyncMock) as mock_embed:
            mock_emb_res = MagicMock()
            mock_emb_res.embeddings = [MagicMock(values=[0.1, 0.2])]
            mock_embed.return_value = mock_emb_res
            
            with patch("src.services.embedding_service.log_finops", new_callable=AsyncMock):
                await reindex_embeddings_bg("tag", 1, "token", MagicMock())
                
                assert mock_profile.semantic_embedding == [0.1, 0.2]
                assert hasattr(mock_profile, "extraction_reliability_score")
                assert mock_db.commit.called

@pytest.mark.asyncio
async def test_reindex_embeddings_bg_error():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    
    mock_profile = MagicMock()
    mock_profile.user_id = 1
    mock_result.scalars().all.return_value = [mock_profile]
    mock_db.execute.return_value = mock_result
    
    async def mock_get_db():
        yield mock_db
        
    with patch("src.services.embedding_service.database.get_db", mock_get_db):
        with patch("src.services.embedding_service.embed_content_with_retry", new_callable=AsyncMock) as mock_embed:
            mock_embed.side_effect = Exception("Embed Failed")
            
            with patch("src.services.embedding_service.logger.error") as mock_logger:
                await reindex_embeddings_bg(None, None, None, MagicMock())
                mock_logger.assert_called()
                assert "Embedding échoué" in mock_logger.call_args[0][0]
                assert mock_db.commit.called
