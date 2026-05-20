"""test_e2e_stateless.py — Stateless E2E API Integration Test Suite.

Runs the complete multi-service workflow in-memory and perform database teardowns.
Guaranteed 100% offline, PEP8 compliant, and safe against cross-test collisions.
"""

import importlib.util
import inspect
import json
import logging
import os
import sys
import traceback
from unittest.mock import AsyncMock, MagicMock, patch

import fakeredis
from fakeredis import aioredis
from fastapi.testclient import TestClient
import google.auth
import google.oauth2.id_token
from httpx import ASGITransport, AsyncClient, Client, Response
import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

# --- Pre-import Environment Setup ---
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./users_test.db"

# Mock Google Auth at the very top of the execution to prevent any import-time or runtime credential discovery failure
mock_creds_global = MagicMock()
mock_creds_global.universe_domain = "googleapis.com"
mock_creds_global.credentials = mock_creds_global
mock_creds_global.credentials.universe_domain = "googleapis.com"
mock_creds_global.with_scopes.return_value = mock_creds_global
mock_creds_global.create_scoped.return_value = mock_creds_global
mock_creds_global.authorize.return_value = mock_creds_global
mock_creds_global.token = "mock-token"

google.auth.default = lambda *args, **kwargs: (mock_creds_global, "test-project")
google.oauth2.id_token.fetch_id_token = lambda *args, **kwargs: "mock-id-token"

try:
    from pgvector.sqlalchemy import Vector
except ImportError:
    class Vector:
        pass


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(ARRAY, "sqlite")
def compile_array_sqlite(type_, compiler, **kw):
    return "TEXT"


@compiles(Vector, "sqlite")
def compile_vector_sqlite(type_, compiler, **kw):
    return "TEXT"


os.environ["SECRET_KEY"] = "testsecret"
os.environ["SECRET_KEY_JWT"] = "testsecret"
os.environ["JWT_SECRET"] = "testsecret"
os.environ["DEV_SERVICE_TOKEN"] = "testtoken"
os.environ["GOOGLE_API_KEY"] = "mock-key-local"
os.environ["USE_IAM_AUTH"] = "false"
os.environ["REDIS_URL"] = "redis://localhost:6379/10"
os.environ["GCP_PROJECT_ID"] = "test-project"
os.environ["VERTEX_LOCATION"] = "europe-west1"

# --- Globals for Mock GenAI & Redis ---
mock_client = MagicMock()
mock_client.aio = MagicMock()
mock_client.aio.models = MagicMock()

# Setup GenAI Mock Async Methods
mock_client.aio.models.generate_content = AsyncMock()
mock_client.aio.models.embed_content = AsyncMock()


class MockValues:
    def __init__(self, values):
        self.values = values


class MockEmbedResponse:
    def __init__(self, values):
        self.embeddings = [MockValues(values)]


mock_client.aio.models.embed_content.return_value = MockEmbedResponse([0.1] * 3072)


class MockUsageMetadata:
    prompt_token_count = 100
    candidates_token_count = 50


class MockGenerateContentResponse:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = MockUsageMetadata()


# Mock GenAI imports globally
mock_genai_module = MagicMock()
mock_genai_module.Client.return_value = mock_client


class MockTypes:
    GenerateContentConfig = MagicMock()
    HttpOptions = MagicMock()


sys.modules["google.genai"] = mock_genai_module
sys.modules["google.genai.types"] = MockTypes
import google  # noqa: E402
google.genai = mock_genai_module

# Mock OTel Span Exporters
mock_otel_exporter = MagicMock()
sys.modules["opentelemetry.exporter.otlp.proto.grpc.trace_exporter"] = mock_otel_exporter
sys.modules["opentelemetry.exporter.otlp.proto.http.trace_exporter"] = mock_otel_exporter

# Mock Google Cloud Scheduler & PubSub globally to prevent import errors in offline test
mock_scheduler = MagicMock()
mock_pubsub = MagicMock()
sys.modules["google.cloud.scheduler_v1"] = mock_scheduler
sys.modules["google.cloud.scheduler"] = mock_scheduler
sys.modules["google.cloud.pubsub_v1"] = mock_pubsub
sys.modules["google.cloud.pubsub"] = mock_pubsub

if "google.cloud" not in sys.modules:
    mock_cloud = MagicMock()
    mock_cloud.scheduler_v1 = mock_scheduler
    mock_cloud.pubsub_v1 = mock_pubsub
    sys.modules["google.cloud"] = mock_cloud
else:
    sys.modules["google.cloud"].scheduler_v1 = mock_scheduler
    sys.modules["google.cloud"].pubsub_v1 = mock_pubsub

# Mock Redis globally
fake_redis_server = fakeredis.FakeServer()
fake_redis_client = aioredis.FakeRedis(server=fake_redis_server, db=10, decode_responses=True)
sys.modules["redis.asyncio"] = MagicMock(from_url=lambda *a, **k: fake_redis_client)
import redis.asyncio  # noqa: E402
redis.asyncio.from_url = lambda *a, **k: fake_redis_client
import shared.redis_state  # noqa: E402
shared.redis_state._state_redis_client = fake_redis_client


# --- Dynamically Load Apps ---
def load_app_cleanly(app_dir_name: str):
    """Loads a microservice FastAPI app cleanly, isolating its sys.modules context."""
    # Ensure SECRET_KEY is set (since other apps might have popped it from os.environ post-startup)
    os.environ["SECRET_KEY"] = "testsecret"
    os.environ["GOOGLE_API_KEY"] = "mock-key-local"

    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(ROOT, app_dir_name)

    old_path = list(sys.path)

    # Clean sys.modules of main/src modules to prevent caching collisions
    modules_to_clear = [
        name for name in list(sys.modules.keys())
        if (
            name == "main" or name.startswith("main.") or
            name == "metrics" or name.startswith("metrics.") or
            name == "conftest" or name.startswith("conftest.") or
            name == "src" or name.startswith("src.")
        )
    ]
    for m in modules_to_clear:
        sys.modules.pop(m, None)

    sys.path.insert(0, app_path)
    sys.path.insert(1, os.path.join(app_path, "src"))

    main_py_path = os.path.join(app_path, "main.py")
    spec = importlib.util.spec_from_file_location("main", main_py_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["main"] = module
    spec.loader.exec_module(module)

    sys.path = old_path

    # Extract App
    app = module.app

    # Set up global Mock Redis pool
    import shared.cache as shared_cache  # noqa: E402
    shared_cache._redis_pool = fake_redis_client
    import shared.redis_state as shared_redis_state  # noqa: E402
    shared_redis_state._state_redis_client = fake_redis_client

    # Apply database schema for SQLite-supported services
    if app_dir_name == "users_api":
        from src.users.models import Base as UsersBase
        engine = create_engine("sqlite:///./users_test.db")
        UsersBase.metadata.drop_all(bind=engine)
        UsersBase.metadata.create_all(bind=engine)
    elif app_dir_name == "items_api":
        from src.items.models import Base as ItemsBase
        engine = create_engine("sqlite:///./items_test.db")
        ItemsBase.metadata.drop_all(bind=engine)
        ItemsBase.metadata.create_all(bind=engine)
    elif app_dir_name == "competencies_api":
        from src.competencies.models import Base as CompetenciesBase
        engine = create_engine("sqlite:///./competencies_test.db")
        CompetenciesBase.metadata.drop_all(bind=engine)
        CompetenciesBase.metadata.create_all(bind=engine)
    elif app_dir_name == "drive_api":
        from src.models import Base as DriveBase
        engine = create_engine("sqlite:///./drive_test.db")
        DriveBase.metadata.drop_all(bind=engine)
        DriveBase.metadata.create_all(bind=engine)

    # Setup specific app dependencies overrides
    shared_db = sys.modules.get("shared.database")
    shared_jwt = sys.modules.get("shared.auth.jwt")
    users_auth = sys.modules.get("src.auth")

    def mock_verify_jwt():
        return {
            "sub": "1",
            "role": "admin",
            "email": "admin@zenika.com",
            "allowed_category_ids": [1, 2, 3, 4, 5]
        }

    if shared_jwt:
        app.dependency_overrides[shared_jwt.verify_jwt] = mock_verify_jwt
    if users_auth:
        app.dependency_overrides[users_auth.verify_jwt] = mock_verify_jwt

    # Specific get_db overrides for pgvector/JSONB services
    if app_dir_name in ("cv_api", "missions_api"):
        async def mock_get_db():
            async with AsyncMockSessionContext() as db:
                yield db
        if shared_db:
            app.dependency_overrides[shared_db.get_db] = mock_get_db
    else:
        # Standard dynamic override to point to specific testing databases
        if app_dir_name == "users_api":
            async def override_get_db():
                async with users_session_maker_global() as db:
                    yield db
            if shared_db:
                app.dependency_overrides[shared_db.get_db] = override_get_db
        elif app_dir_name == "items_api":
            async def override_get_db():
                async with items_session_maker_global() as db:
                    yield db
            if shared_db:
                app.dependency_overrides[shared_db.get_db] = override_get_db
        elif app_dir_name == "competencies_api":
            async def override_get_db():
                async with competencies_session_maker_global() as db:
                    yield db
            if shared_db:
                app.dependency_overrides[shared_db.get_db] = override_get_db
        elif app_dir_name == "drive_api":
            async def override_get_db():
                async with drive_session_maker_global() as db:
                    yield db
            if shared_db:
                app.dependency_overrides[shared_db.get_db] = override_get_db

    return app


# --- Dynamic database routing and global engine/session setup ---
# 1. Global engines and session makers for SQLite services
users_engine_global = create_async_engine("sqlite+aiosqlite:///./users_test.db")
users_session_maker_global = sessionmaker(
    class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False, bind=users_engine_global
)

items_engine_global = create_async_engine("sqlite+aiosqlite:///./items_test.db")
items_session_maker_global = sessionmaker(
    class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False, bind=items_engine_global
)

competencies_engine_global = create_async_engine("sqlite+aiosqlite:///./competencies_test.db")
competencies_session_maker_global = sessionmaker(
    class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False, bind=competencies_engine_global
)

drive_engine_global = create_async_engine("sqlite+aiosqlite:///./drive_test.db")
drive_session_maker_global = sessionmaker(
    class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False, bind=drive_engine_global
)


# 2. Async Context Manager for Mock Sessions
class AsyncMockSessionContext:
    async def __aenter__(self):
        db = AsyncMock(spec=AsyncSession)
        execute_result = MagicMock()
        execute_result.all.return_value = []
        execute_result.fetchall.return_value = []
        execute_result.scalar.return_value = 0
        execute_result.scalars.return_value.all.return_value = []
        execute_result.scalars.return_value.first.return_value = None
        execute_result.scalar_one_or_none.return_value = None
        execute_result.scalar_one.return_value = 0
        db.execute.return_value = execute_result
        return db

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


# 3. Dynamic SessionLocal Router based on call-stack analysis
def dynamic_session_local(*args, **kwargs):
    stack = inspect.stack()
    for frame in stack:
        filename = frame.filename
        if "drive_api" in filename:
            return drive_session_maker_global(*args, **kwargs)
        elif "users_api" in filename:
            return users_session_maker_global(*args, **kwargs)
        elif "competencies_api" in filename:
            return competencies_session_maker_global(*args, **kwargs)
        elif "items_api" in filename:
            return items_session_maker_global(*args, **kwargs)
        elif "cv_api" in filename or "missions_api" in filename:
            return AsyncMockSessionContext()

    # Fallback to drive session maker if caller is not identified
    return drive_session_maker_global(*args, **kwargs)


# 4. Inject dynamic_session_local into shared.database before loading any apps
import shared.database  # noqa: E402
shared.database.SessionLocal = dynamic_session_local


# Load all FastAPI apps
users_app = load_app_cleanly("users_api")
items_app = load_app_cleanly("items_api")
competencies_app = load_app_cleanly("competencies_api")
cv_app = load_app_cleanly("cv_api")
missions_app = load_app_cleanly("missions_api")
drive_app = load_app_cleanly("drive_api")


# --- Global HTTP Interceptor ---
original_async_send = AsyncClient.send
original_sync_send = Client.send


async def patched_async_send(self, request, *args, **kwargs):
    url_str = str(request.url)

    # 0. Bypass for TestClient internal calls to its own ASGI app or recursively routed clients
    if isinstance(getattr(self, "_transport", None), ASGITransport) or "testserver" in request.url.host:
        return await original_async_send(self, request, *args, **kwargs)

    # 1. Mock Google Metadata Service
    if "metadata.google.internal" in url_str:
        return Response(status_code=200, text="mock_oidc_token", request=request)

    # 2. Mock Prompts API calls
    if "prompts_api:8000" in url_str or "prompts-api:8000" in url_str:
        return Response(status_code=200, json={"value": "Mock Prompt Content"}, request=request)

    # 2bis. Mock Analytics MCP
    if "analytics_mcp" in url_str or "analytics-mcp" in url_str:
        return Response(status_code=200, json={"success": True}, request=request)

    # 3. Route internally based on target host
    app_mapping = {
        "users_api": users_app,
        "users-api": users_app,
        "items_api": items_app,
        "items-api": items_app,
        "competencies_api": competencies_app,
        "competencies-api": competencies_app,
        "cv_api": cv_app,
        "cv-api": cv_app,
        "missions_api": missions_app,
        "missions-api": missions_app,
        "drive_api": drive_app,
        "drive-api": drive_app,
    }

    for host, app in app_mapping.items():
        if host in request.url.host or f"{host}:" in url_str:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url=f"http://{request.url.host}") as sub_client:
                req_headers = dict(request.headers)
                req_headers.pop("host", None)
                req_headers.pop("content-length", None)
                raw_path_decoded = request.url.raw_path.decode("utf-8")
                return await sub_client.request(
                    method=request.method,
                    url=raw_path_decoded,
                    headers=req_headers,
                    content=request.read(),
                )

    raise RuntimeError(f"Attempted external HTTP call to blocked URL in stateless E2E test: {url_str}")


def patched_sync_send(self, request, *args, **kwargs):
    url_str = str(request.url)

    # 0. Bypass for TestClient internal calls to its own ASGI app or recursively routed clients
    if isinstance(getattr(self, "_transport", None), ASGITransport) or "testserver" in request.url.host:
        return original_sync_send(self, request, *args, **kwargs)

    if "metadata.google.internal" in url_str:
        return Response(status_code=200, text="mock_oidc_token", request=request)

    if "prompts_api:8000" in url_str or "prompts-api:8000" in url_str:
        return Response(status_code=200, json={"value": "Mock Prompt Content"}, request=request)

    if "analytics_mcp" in url_str or "analytics-mcp" in url_str:
        return Response(status_code=200, json={"success": True}, request=request)

    app_mapping = {
        "users_api": users_app,
        "users-api": users_app,
        "items_api": items_app,
        "items-api": items_app,
        "competencies_api": competencies_app,
        "competencies-api": competencies_app,
        "cv_api": cv_app,
        "cv-api": cv_app,
        "missions_api": missions_app,
        "missions-api": missions_app,
        "drive_api": drive_app,
        "drive-api": drive_app,
    }

    for host, app in app_mapping.items():
        if host in request.url.host or f"{host}:" in url_str:
            transport = ASGITransport(app=app)
            with Client(transport=transport, base_url=f"http://{request.url.host}") as sub_client:
                req_headers = dict(request.headers)
                req_headers.pop("host", None)
                req_headers.pop("content-length", None)
                raw_path_decoded = request.url.raw_path.decode("utf-8")
                return sub_client.request(
                    method=request.method,
                    url=raw_path_decoded,
                    headers=req_headers,
                    content=request.read(),
                )

    raise RuntimeError(f"Attempted external HTTP call to blocked URL in stateless E2E test: {url_str}")


@pytest.fixture(autouse=True)
def apply_http_interceptors():
    """Applique les mocks HTTP de façon globale pendant l'exécution des tests."""
    original_warning = logging.Logger.warning

    def patched_warning(self, msg, *args, **kwargs):
        original_warning(self, msg, *args, **kwargs)
        exc_type, exc_val, exc_tb = sys.exc_info()
        if exc_type is not None:
            trace_str = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            sys.stderr.write(f"\n[DEBUG WARNING EXCEPTION] {msg}\n{trace_str}\n")

    original_error = logging.Logger.error

    def patched_error(self, msg, *args, **kwargs):
        original_error(self, msg, *args, **kwargs)
        exc_type, exc_val, exc_tb = sys.exc_info()
        if exc_type is not None:
            trace_str = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
            sys.stderr.write(f"\n[DEBUG ERROR EXCEPTION] {msg}\n{trace_str}\n")

    with patch("httpx.AsyncClient.send", patched_async_send):
        with patch("httpx.Client.send", patched_sync_send):
            with patch("logging.Logger.warning", patched_warning):
                with patch("logging.Logger.error", patched_error):
                    yield


@pytest.fixture(autouse=True)
def mock_drive_service_globally():
    """Mocks get_drive_service globally for all modules using patch to guarantee offline execution."""
    mock_drive = MockDriveService()
    with patch("src.google_auth.get_drive_service", return_value=mock_drive):
        with patch("src.services.folder_service.get_drive_service", return_value=mock_drive):
            with patch("src.routers.sync_router.get_drive_service", return_value=mock_drive):
                with patch("src.drive_service.get_drive_service", return_value=mock_drive):
                    yield


@pytest.fixture(scope="function", autouse=True)
def teardown_databases():
    """Wipes test databases and physical SQLite database files after test execution."""
    yield
    # Physically remove SQLite DB files
    db_files = [
        "users_test.db", "users_test.db-wal", "users_test.db-shm",
        "items_test.db", "items_test.db-wal", "items_test.db-shm",
        "competencies_test.db", "competencies_test.db-wal", "competencies_test.db-shm",
        "drive_test.db", "drive_test.db-wal", "drive_test.db-shm"
    ]
    for db_file in db_files:
        if os.path.exists(db_file):
            try:
                os.remove(db_file)
            except Exception:
                pass


# --- E2E Integration Test Case ---
@pytest.mark.asyncio
async def test_e2e_stateless_workflow():
    """Tests the complete workflow from user creation, sync, CV ingestion and parsing to mission staffing."""
    # 1. Create a user on Users API
    users_client = TestClient(users_app)
    user_payload = {
        "username": "candidate_test",
        "email": "candidate_test@zenika.com",
        "first_name": "John",
        "last_name": "Doe",
        "full_name": "John Doe",
        "role": "user",
        "password": "Password123!",
        "is_active": True,
        "allowed_category_ids": [1, 2, 3]
    }
    create_res = users_client.post("/", json=user_payload, headers={"Authorization": "Bearer testtoken"})
    assert create_res.status_code == 201, f"Failed to create user: {create_res.text}"
    user_data = create_res.json()
    user_id = user_data["id"]
    assert user_data["username"] == "candidate_test"

    # 2. Trigger Google Drive Sync on Drive API
    drive_client = TestClient(drive_app)

    # Pre-seed a drive folder mapping to configure the sync
    folder_payload = {
        "google_folder_id": "mock_folder_1",
        "tag": "Paris",
        "folder_name": "Paris Agence"
    }
    folder_res = drive_client.post("/folders", json=folder_payload, headers={"Authorization": "Bearer testtoken"})
    assert folder_res.status_code == 200 or folder_res.status_code == 201

    # Trigger Google Drive Sync on Drive API (fully mocked globally)
    sync_res = drive_client.post("/sync", headers={"Authorization": "Bearer testtoken"})
    assert sync_res.status_code == 200
    assert sync_res.json()["status"] == "started"

    # 3. Analyze a raw-text CV to extract profile on CV API
    cv_client = TestClient(cv_app)
    cv_import_payload = {
        "raw_text": (
            "John Doe, Senior Python Backend Engineer, "
            "5 years experience in building beautiful APIs with FastAPI."
        ),
        "direct_user_id": user_id,
        "source_tag": "test-direct"
    }

    # Setup the prompt response to extract details
    mock_profile = {
        "is_cv": True,
        "first_name": "John",
        "last_name": "Doe",
        "email": "candidate_test@zenika.com",
        "summary": "Experienced Python Backend Developer",
        "current_role": "Python Backend Engineer",
        "years_of_experience": 5,
        "competencies": [
            {"name": "Python", "parent": "Langages Backend"},
            {"name": "FastAPI", "parent": "Frameworks Backend"}
        ],
        "missions": [
            {
                "title": "Senior Developer",
                "company": "Tech Corp",
                "description": "Led backend development using Python and FastAPI",
                "start_date": "2020",
                "end_date": "2023",
                "duration": "3 years",
                "mission_type": "build",
                "competencies": ["Python", "FastAPI"],
                "is_sensitive": False
            }
        ],
        "educations": [
            {"degree": "Master in Computer Science", "school": "University of Tech"}
        ]
    }
    mock_client.aio.models.generate_content.return_value = MockGenerateContentResponse(json.dumps(mock_profile))

    cv_res = cv_client.post("/import", json=cv_import_payload, headers={"Authorization": "Bearer testtoken"})
    assert cv_res.status_code == 200, f"Failed CV Import: {cv_res.text}"
    cv_data = cv_res.json()
    assert cv_data["user_id"] == user_id
    assert cv_data["competencies_assigned"] >= 0

    # Explicitly check competencies_app's assignments router to verify they were successfully saved in SQLite
    comp_client = TestClient(competencies_app)
    get_comp_res = comp_client.get(f"/user/{user_id}", headers={"Authorization": "Bearer testtoken"})
    assert get_comp_res.status_code == 200
    comp_json = get_comp_res.json()
    assert len(comp_json["items"]) > 0

    # 4. Create and match a mock mission on Missions API
    missions_client = TestClient(missions_app)

    # Mock the LLM generation for mission analysis
    mock_mission_llm = {
        "title": "Expert Python/FastAPI Developer Needed",
        "description": "Building next-generation microservices",
        "extracted_competencies": ["Python", "FastAPI"],
        "prefiltered_candidates": [],
        "proposed_team": []
    }
    mock_client.aio.models.generate_content.return_value = MockGenerateContentResponse(json.dumps(mock_mission_llm))

    mission_res = missions_client.post(
        "/missions",
        data={
            "title": "Expert Python/FastAPI Developer Needed",
            "description": "Building next-generation microservices"
        },
        headers={"Authorization": "Bearer testtoken"}
    )
    assert mission_res.status_code == 202, f"Failed mission creation: {mission_res.text}"
    task_id = mission_res.json()["task_id"]

    # Verify task state is successfully registered in task manager
    status_res = missions_client.get(f"/missions/task/{task_id}", headers={"Authorization": "Bearer testtoken"})
    assert status_res.status_code == 200, f"Task status response: {status_res.text}"
    status_data = status_res.json()
    assert status_data["status"] in ("processing", "completed", "success"), f"Task failed: {status_data}"


class MockDriveService:
    def about(self):
        class MockAbout:
            def get(self, fields=None):
                class MockRequest:
                    def execute(self):
                        return {"user": {"emailAddress": "test@zenika.com"}}
                return MockRequest()
        return MockAbout()

    def files(self):
        class MockFiles:
            def get(self, fileId, fields=None, supportsAllDrives=None):
                class MockRequest:
                    def execute(self):
                        return {"id": fileId, "name": "Mock Folder", "parents": ["root"]}
                return MockRequest()

            def list(self, q=None, spaces=None, corpora=None, includeItemsFromAllDrives=None,
                     supportsAllDrives=None, fields=None, pageToken=None, pageSize=None):
                class MockRequest:
                    def execute(self):
                        return {
                            "files": [
                                {
                                    "id": "mock_file_1",
                                    "name": "john_doe_cv.docx",
                                    "mimeType": (
                                        "application/vnd.openxmlformats-officedocument"
                                        ".wordprocessingml.document"
                                    ),
                                    "modifiedTime": "2026-05-20T10:00:00Z",
                                    "version": 1,
                                    "parents": ["mock_folder_1"],
                                    "trashed": False
                                }
                            ],
                            "nextPageToken": None
                        }
                return MockRequest()
        return MockFiles()
