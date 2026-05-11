import pytest
from unittest.mock import AsyncMock, MagicMock
from src.missions.document_extractor import extract_document_contents
from google.genai import types
import httpx
import docx

@pytest.mark.asyncio
async def test_extract_url_google_docs():
    http_client = AsyncMock()
    mock_resp = MagicMock(status_code=200)
    mock_resp.text = "Google Doc Content"
    http_client.get.return_value = mock_resp

    url = "https://docs.google.com/document/d/12345ABC/edit"
    contents, desc = await extract_document_contents(url, None, "", "", {}, http_client)
    
    assert "Google Doc Content" in contents[0]
    assert "12345ABC/export?format=txt" in http_client.get.call_args[0][0]
    assert "Document charg" in desc

@pytest.mark.asyncio
async def test_extract_url_generic_fail():
    http_client = AsyncMock()
    mock_resp = MagicMock(status_code=404)
    http_client.get.return_value = mock_resp

    url = "https://example.com/doc"
    contents, desc = await extract_document_contents(url, None, "", "My desc", {}, http_client)
    
    assert len(contents) == 0
    assert desc == "My desc"

@pytest.mark.asyncio
async def test_extract_docx(mocker):
    http_client = AsyncMock()
    
    mock_doc = MagicMock()
    mock_p = MagicMock()
    mock_p.text = "Docx text"
    mock_doc.paragraphs = [mock_p]
    mocker.patch("docx.Document", return_value=mock_doc)

    contents, desc = await extract_document_contents("", b"dummy", "application/msword", "", {}, http_client)
    
    assert "Docx text" in contents[0]
    assert "binaire" in desc

@pytest.mark.asyncio
async def test_extract_pdf(mocker):
    http_client = AsyncMock()
    mocker.patch("google.genai.types.Part.from_bytes", return_value="PDF Part")

    contents, desc = await extract_document_contents("", b"pdf", "application/pdf", "", {}, http_client)
    
    assert contents[0] == "PDF Part"
    assert "binaire" in desc
