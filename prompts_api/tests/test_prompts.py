import pytest
from fastapi.testclient import TestClient
import os
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./prompts_test.db"
os.environ["SECRET_KEY"] = "testsecret"

from unittest.mock import MagicMock, patch

with patch("opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter", return_value=MagicMock()):
    from main import app
    from database import get_db, engine
    from src.prompts.models import Base
    import database

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

if engine: engine.dispose()
sync_engine = create_engine("sqlite:///./prompts_test.db", connect_args={"check_same_thread": False})
async_engine = create_async_engine("sqlite+aiosqlite:///./prompts_test.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False, bind=async_engine)

async def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        await db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(autouse=True)
def wipe_db():
    Base.metadata.drop_all(bind=sync_engine)
    Base.metadata.create_all(bind=sync_engine)
    yield

@pytest.fixture(autouse=True)
def mock_db_connection(monkeypatch):
    async def mock_check_db_connection():
        return True
    monkeypatch.setattr(database, "check_db_connection", mock_check_db_connection)

with TestClient(app) as c:
    client = c


# Override the verify_admin dependency for simplicity
def override_verify_admin():
    return {"role": "admin"}

def override_verify_jwt():
    return {"role": "admin"}

import src.prompts.router as router
app.dependency_overrides[router.verify_admin] = override_verify_admin
app.dependency_overrides[router.verify_jwt] = override_verify_jwt

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_get_not_found():
    response = client.get("/fake.prompt.unknown")
    assert response.status_code == 404

def test_create_and_read_prompt():
    response = client.post("/", json={"key": "test_prompt", "value": "test_val"})
    assert response.status_code == 200
    assert response.json()["value"] == "test_val"
    
    # Read (DB hit)
    read_resp = client.get("/test_prompt")
    assert read_resp.status_code == 200
    assert read_resp.json()["value"] == "test_val"
    
    # Read (Cache hit)
    read_resp_2 = client.get("/test_prompt")
    assert read_resp_2.status_code == 200

def test_create_prompt_overwrite():
    client.post("/", json={"key": "over_prompt", "value": "val1"})
    resp = client.post("/", json={"key": "over_prompt", "value": "val2"})
    assert resp.status_code == 200
    assert resp.json()["value"] == "val2"

def test_update_prompt():
    # Update not exist ->Upsert
    resp1 = client.put("/upd_prompt", json={"value": "foo"})
    assert resp1.status_code == 200
    assert resp1.json()["value"] == "foo"
    
    # Update exist
    resp2 = client.put("/upd_prompt", json={"value": "bar"})
    assert resp2.status_code == 200
    assert resp2.json()["value"] == "bar"

def test_list_prompts():
    resp = client.get("/")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)

@patch("src.prompts.router.generate_test_cases")
@patch("src.prompts.router.run_promptfoo_analysis")
@patch("src.prompts.router.improve_prompt_with_gemini")
def test_analyze_prompt(mock_improve, mock_run, mock_gen):
    client.post("/", json={"key": "analyze_me", "value": "test"})
    
    mock_gen.return_value = [{"vars": {"input": "test"}, "assert": []}]
    mock_run.return_value = {"results": "mocked"}
    mock_improve.return_value = "Improved test!"
    
    resp = client.post("/analyze_me/analyze")
    assert resp.status_code == 200
    data = resp.json()
    assert data["improved_prompt"] == "Improved test!"
    assert data["original_prompt"] == "test"

@patch("src.prompts.router.generate_test_cases")
def test_analyze_prompt_fail(mock_gen):
    client.post("/", json={"key": "fail_me", "value": "test"})
    
    mock_gen.return_value = []
    
    resp = client.post("/fail_me/analyze")
    assert resp.status_code == 500

def test_analyze_not_found():
    resp = client.post("/not_here/analyze")
    assert resp.status_code == 404

def test_auth_verify_jwt_pass():
    from src.prompts.router import verify_jwt
    from fastapi.security import HTTPAuthorizationCredentials
    import jose.jwt
    import os
    
    secret = os.getenv("SECRET_KEY", "zenika_super_secret_key_change_me_in_production")
    token = jose.jwt.encode({"sub": "1", "role": "admin"}, secret, algorithm="HS256")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    
    payload = verify_jwt(creds)
    assert payload["role"] == "admin"

def test_auth_verify_jwt_fail():
    from src.prompts.router import verify_jwt
    from fastapi.security import HTTPAuthorizationCredentials
    from fastapi import HTTPException
    
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad")
    with pytest.raises(HTTPException) as exc:
        verify_jwt(creds)
    assert exc.value.status_code == 401

def test_auth_verify_admin_fail():
    from src.prompts.router import verify_admin
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        verify_admin({"role": "user"})
    assert exc.value.status_code == 403

def test_auth_verify_admin_pass():
    from src.prompts.router import verify_admin
    assert verify_admin({"role": "admin"}) == {"role": "admin"}

import src.prompts.analyzer as analyzer
import os
import json

def test_analyzer_get_genai_client_fail(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(ValueError):
        analyzer.get_genai_client()

def test_analyzer_generate_test_cases_success(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    with patch("src.prompts.analyzer.genai.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.text = '[{"user_query": "hi", "rubric": "ok"}]'
        mock_client.return_value.models.generate_content.return_value = mock_resp
        
        res = analyzer.generate_test_cases("my prompt")
        assert len(res) == 1
        assert res[0]["user_query"] == "hi"

def test_analyzer_generate_test_cases_fail(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    with patch("src.prompts.analyzer.genai.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.text = '{"bad json'
        mock_client.return_value.models.generate_content.return_value = mock_resp
        
        res = analyzer.generate_test_cases("my prompt")
        assert res == []

def test_analyzer_run_promptfoo_analysis_success(mocker):
    # Check that subprocess.run is called and output.json is parsed
    mock_run = mocker.patch("src.prompts.analyzer.subprocess.run")
    
    # We also mock os.path.exists and open for the output_file
    mocker.patch("src.prompts.analyzer.os.path.exists", return_value=True)
    mocker.patch("builtins.open", mocker.mock_open(read_data='{"results": "ok"}'))
    
    res = analyzer.run_promptfoo_analysis("prompt", [{"user_query": "u1", "rubric": "r1"}])
    assert res == {"results": "ok"}
    mock_run.assert_called_once()

def test_analyzer_run_promptfoo_analysis_no_json(mocker):
    mock_run = mocker.patch("src.prompts.analyzer.subprocess.run")
    mock_run.return_value.stdout = "out"
    mock_run.return_value.stderr = "err"
    
    mocker.patch("src.prompts.analyzer.os.path.exists", return_value=False)
    # the second open is meant for config and prompts
    mocker.patch("builtins.open", mocker.mock_open())
    
    res = analyzer.run_promptfoo_analysis("prompt", [])
    assert "error" in res
    assert "stdout" in res
    assert res["stdout"] == "out"

def test_analyzer_run_promptfoo_analysis_exception(mocker):
    mocker.patch("src.prompts.analyzer.subprocess.run", side_effect=ValueError("subprocess failed"))
    mocker.patch("builtins.open", mocker.mock_open())
    res = analyzer.run_promptfoo_analysis("prompt", [])
    assert res == {"error": "subprocess failed"}

def test_analyzer_improve_prompt_with_gemini_success(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    with patch("src.prompts.analyzer.genai.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.text = "better prompt"
        mock_client.return_value.models.generate_content.return_value = mock_resp
        
        eval_data = {
            "results": {
                "results": [
                    {"success": False, "vars": {"user_query": "bad"}, "error": "failed rubric"}
                ]
            }
        }
        res = analyzer.improve_prompt_with_gemini("orig", eval_data)
        assert res == "better prompt"

def test_analyzer_improve_prompt_with_gemini_markdown(monkeypatch):
    monkeypatch.setenv("GOOGLE_API_KEY", "fake")
    with patch("src.prompts.analyzer.genai.Client") as mock_client:
        mock_resp = MagicMock()
        mock_resp.text = "```\nbetter prompt\nline2\n```"
        mock_client.return_value.models.generate_content.return_value = mock_resp
        
        res = analyzer.improve_prompt_with_gemini("orig", {})
        assert res == "better prompt\nline2"
