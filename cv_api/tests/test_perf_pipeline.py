"""
test_perf_pipeline.py — Tests unitaires et d'intégration du pipeline perf-test.

Couvre :
  1. Validation du schéma CVImportRequest (model_validator)
  2. Route POST /import en mode perf-test (raw_text + direct_user_id → process_cv_direct)
  3. Route POST /import en mode PRD (url → process_cv_core, branche directe inchangée)
  4. Contenu de mock_cv_pool.json (pool de données valide)
  5. mock_gemini/main.py : endpoints generateContent, embedContent (sans docker)
"""
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from shared.auth.jwt import security, verify_jwt
from shared.database import get_db
from main import app
from src.cvs.schemas import CVImportRequest, CVResponse, CVImportStep

os.environ["SECRET_KEY"] = "testsecret"

# ── Fixtures globales ──────────────────────────────────────────────────────────


async def _override_db():
    db = AsyncMock()
    db.execute.return_value = MagicMock()
    db.execute.return_value.scalars.return_value.first.return_value = None
    yield db


def _override_jwt_admin():
    return {"sub": "test", "role": "admin", "user_id": 1}


@pytest.fixture(autouse=True)
def apply_dependency_overrides():
    prev_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[verify_jwt] = _override_jwt_admin
    app.dependency_overrides[security] = lambda: MagicMock(credentials="testtoken")
    yield
    app.dependency_overrides = prev_overrides


client = TestClient(app)

_AUTH_HEADERS = {"Authorization": "Bearer test-token"}

# ── Section 1 : Validation du schéma CVImportRequest ─────────────────────────


class TestCVImportRequestSchema:
    """Teste le model_validator et la rétrocompatibilité PRD."""

    def test_url_alone_is_valid(self):
        """PRD : url seule → valide."""
        req = CVImportRequest(url="https://docs.google.com/document/d/abc/edit")
        assert req.url == "https://docs.google.com/document/d/abc/edit"
        assert req.raw_text is None
        assert req.direct_user_id is None

    def test_raw_text_and_direct_user_id_valid(self):
        """Perf : raw_text + direct_user_id → valide."""
        req = CVImportRequest(raw_text="Consultant Python senior.", direct_user_id=42)
        assert req.raw_text == "Consultant Python senior."
        assert req.direct_user_id == 42
        assert req.url is None

    def test_neither_url_nor_raw_text_raises_422(self):
        """Ni url ni raw_text → ValueError (→ 422 via FastAPI)."""
        with pytest.raises(ValueError, match="url or raw_text must be provided"):
            CVImportRequest(source_tag="perf-test")

    def test_direct_user_id_alone_without_raw_text_raises_422(self):
        """direct_user_id seul sans raw_text → pas de text à analyser → 422."""
        with pytest.raises(ValueError, match="url or raw_text must be provided"):
            CVImportRequest(direct_user_id=42)

    def test_url_with_all_optional_fields(self):
        """PRD : url + tous les champs optionnels → valide."""
        req = CVImportRequest(
            url="https://docs.google.com/document/d/abc/edit",
            google_access_token="tok",
            source_tag="niort",
            folder_name="Alice Martin",
        )
        assert req.source_tag == "niort"
        assert req.folder_name == "Alice Martin"

    def test_raw_text_alone_without_direct_user_id_valid(self):
        """raw_text seul (sans direct_user_id) → valide (process_cv_core résoudra l'identité)."""
        req = CVImportRequest(raw_text="CV text sans user_id direct.")
        assert req.raw_text is not None
        assert req.direct_user_id is None


# ── Section 2 : Route POST /import — mode perf-test ───────────────────────────


def _make_genai_mock(mocker):
    """Helper : mock le client Gemini avec une réponse CV valide."""
    mock_genai = mocker.patch("src.services.config.client")
    mock_genai.aio.models.generate_content = AsyncMock()
    mock_genai.aio.models.generate_content.return_value.text = json.dumps({
        "is_cv": True, "first_name": "Perf", "last_name": "Test",
        "email": "perf.test@mock.local",
        "summary": "Consultant perf-test.", "current_role": "Senior Dev",
        "years_of_experience": 7, "is_anonymous": False,
        "competencies": [{"name": "Python", "parent": "Langages", "practiced": True}],
        "missions": [], "educations": [],
    })
    mock_genai.aio.models.embed_content = AsyncMock()
    mock_genai.aio.models.embed_content.return_value.embeddings = [MagicMock(values=[0.1] * 10)]
    return mock_genai


_PERF_CV_RESPONSE = CVResponse(
    message="CV importé avec succès (perf-test)",
    user_id=99,
    competencies_assigned=1,
    steps=[
        CVImportStep(step="download", label="bypass perf-test", status="success", duration_ms=0),
        CVImportStep(step="llm_parse", label="Analyse IA mock", status="success", duration_ms=500),
        CVImportStep(step="user_resolve", label="bypass direct_user_id=99", status="success",
                     duration_ms=0, detail="direct_user_id=99"),
        CVImportStep(step="db_save", label="Sauvegarde DB", status="success", duration_ms=10),
    ],
    warnings=[],
)


class TestImportRoutePerfMode:
    """POST /import avec raw_text + direct_user_id → process_cv_direct."""

    def test_import_direct_success(self, mocker):
        """
        Mode perf : raw_text + direct_user_id → HTTP 200.
        Vérifie que process_cv_direct est appelé (pas process_cv_core) et
        que la réponse contient les steps bypass attendus.
        """
        mock_direct = mocker.patch(
            "src.cvs.routers.profile_router.process_cv_direct",
            new_callable=AsyncMock,
            return_value=_PERF_CV_RESPONSE,
        )
        mock_core = mocker.patch(
            "src.cvs.routers.profile_router.process_cv_core",
            new_callable=AsyncMock,
        )

        resp = client.post(
            "/import",
            json={"raw_text": "Consultant Python GCP senior.", "direct_user_id": 99},
            headers=_AUTH_HEADERS,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()

        # process_cv_direct appelé, pas process_cv_core
        mock_direct.assert_called_once()
        mock_core.assert_not_called()

        assert data["user_id"] == 99, "user_id doit être direct_user_id (99)"
        assert data["message"] == "CV importé avec succès (perf-test)"

        step_keys = {s["step"] for s in data["steps"]}
        assert "download" in step_keys, "L'étape 'download' (bypass) doit être présente"
        assert "llm_parse" in step_keys, "L'étape 'llm_parse' doit être présente"
        assert "user_resolve" in step_keys, "L'étape 'user_resolve' (bypass) doit être présente"

        # L'étape download doit avoir duration_ms=0 (bypass)
        dl_step = next(s for s in data["steps"] if s["step"] == "download")
        assert dl_step["duration_ms"] == 0, "download bypass doit avoir duration_ms=0"
        assert "perf-test" in dl_step["label"].lower(), (
            "Le label download doit indiquer le mode perf-test"
        )

        # L'étape user_resolve doit être bypass avec user_id=99
        ur_step = next(s for s in data["steps"] if s["step"] == "user_resolve")
        assert "99" in (ur_step.get("detail") or ""), (
            "user_resolve doit mentionner le direct_user_id dans detail"
        )

    def test_import_direct_not_a_cv_returns_400(self, mocker):
        """Mode perf : si le mock LLM retourne is_cv=False → HTTP 400."""
        mock_genai = mocker.patch("src.services.config.client")
        mock_genai.aio.models.generate_content = AsyncMock()
        mock_genai.aio.models.generate_content.return_value.text = json.dumps({
            "is_cv": False, "first_name": None, "last_name": None,
            "email": None, "competencies": [],
        })
        mocker.patch(
            "src.services.cv_extraction_service.get_cache", return_value="dummy prompt"
        )

        resp = client.post(
            "/import",
            json={"raw_text": "Ceci est une recette de cuisine.", "direct_user_id": 99},
            headers=_AUTH_HEADERS,
        )
        assert resp.status_code == 400
        assert "Not a CV" in resp.json()["detail"]

    def test_import_direct_no_genai_client_returns_503(self, mocker):
        """Mode perf sans mock_gemini démarré : client=None → HTTP 503 clair."""
        mocker.patch("src.services.config.client", None)

        resp = client.post(
            "/import",
            json={"raw_text": "Consultant senior.", "direct_user_id": 99},
            headers=_AUTH_HEADERS,
        )
        assert resp.status_code == 503
        assert "GEMINI_API_BASE_URL" in resp.json()["detail"], (
            "Le message 503 doit mentionner GEMINI_API_BASE_URL pour guider l'opérateur"
        )

    def test_import_direct_role_user_returns_403(self, mocker):
        """Mode perf : rôle 'user' ne peut pas importer (FinOps gate)."""
        app.dependency_overrides[verify_jwt] = lambda: {"sub": "t", "role": "user", "user_id": 1}
        try:
            resp = client.post(
                "/import",
                json={"raw_text": "CV text.", "direct_user_id": 99},
                headers=_AUTH_HEADERS,
            )
            assert resp.status_code == 403
        finally:
            app.dependency_overrides[verify_jwt] = _override_jwt_admin


# ── Section 3 : Route POST /import — mode PRD (url classique) ─────────────────


class TestImportRoutePRDMode:
    """POST /import avec url seule → process_cv_core (chemin PRD inchangé)."""

    def test_import_url_calls_process_cv_core(self, mocker):
        """PRD : url fournie sans raw_text → process_cv_core appelé (pas process_cv_direct)."""
        mock_core = mocker.patch(
            "src.cvs.routers.profile_router.process_cv_core",
            new_callable=AsyncMock,
        )
        mock_direct = mocker.patch(
            "src.cvs.routers.profile_router.process_cv_direct",
            new_callable=AsyncMock,
        )
        mock_core.return_value = CVResponse(
            message="OK", user_id=1, status="success", competencies_assigned=0,
            steps=[], warnings=[],
        )

        client.post(
            "/import",
            json={"url": "https://docs.google.com/document/d/abc/edit"},
            headers=_AUTH_HEADERS,
        )
        mock_core.assert_called_once()
        mock_direct.assert_not_called()

    def test_import_no_url_no_raw_text_returns_422(self):
        """PRD : payload vide (ni url ni raw_text) → 422 Validation Error (model_validator)."""
        resp = client.post(
            "/import",
            json={"source_tag": "niort"},
            headers=_AUTH_HEADERS,
        )
        assert resp.status_code == 422
        body = resp.json()
        assert any(
            "url or raw_text" in str(e.get("msg", "")).lower()
            for e in body.get("detail", [])
        ), f"Erreur attendue 'url or raw_text must be provided'. Reçu: {body}"

    def test_import_url_no_auth_returns_401(self):
        """PRD : appel sans Authorization → 401."""
        original = app.dependency_overrides.pop(verify_jwt, None)
        original_sec = app.dependency_overrides.pop(security, None)
        try:
            resp = client.post("/import", json={"url": "https://docs.google.com/d/abc"})
            assert resp.status_code == 401
        finally:
            if original:
                app.dependency_overrides[verify_jwt] = original
            if original_sec:
                app.dependency_overrides[security] = original_sec


# ── Section 4 : Validation du pool mock_cv_pool.json ──────────────────────────


_POOL_PATH = Path(__file__).parent.parent.parent / "locust" / "data" / "mock_cv_pool.json"

_REQUIRED_CV_FIELDS = {"is_cv", "first_name", "last_name", "email", "summary",
                       "current_role", "years_of_experience", "competencies", "missions"}
_REQUIRED_COMPETENCY_FIELDS = {"name"}


class TestMockCVPool:
    """Valide que mock_cv_pool.json est un pool de données cohérent."""

    @pytest.fixture(scope="class")
    def pool(self):
        if not _POOL_PATH.exists():
            pytest.skip(f"mock_cv_pool.json introuvable: {_POOL_PATH}")
        with _POOL_PATH.open(encoding="utf-8") as f:
            return json.load(f)

    def test_pool_is_list(self, pool):
        assert isinstance(pool, list), "mock_cv_pool.json doit être une liste JSON"

    def test_pool_has_at_least_one_entry(self, pool):
        assert len(pool) >= 1, "Le pool doit contenir au moins 1 entrée CV"

    def test_all_entries_are_cv(self, pool):
        """Tous les CVs doivent avoir is_cv=True (le mock doit toujours retourner un vrai CV)."""
        non_cv = [i for i, cv in enumerate(pool) if not cv.get("is_cv")]
        assert not non_cv, f"Entrées avec is_cv=False aux index: {non_cv}"

    def test_all_entries_have_required_fields(self, pool):
        for i, cv in enumerate(pool):
            missing = _REQUIRED_CV_FIELDS - set(cv.keys())
            assert not missing, f"Entrée {i} manque les champs: {missing}"

    def test_competencies_are_lists_with_name(self, pool):
        for i, cv in enumerate(pool):
            comps = cv.get("competencies", [])
            assert isinstance(comps, list), f"Entrée {i}: competencies doit être une liste"
            for j, comp in enumerate(comps):
                missing = _REQUIRED_COMPETENCY_FIELDS - set(comp.keys())
                assert not missing, f"Entrée {i} compétence {j} manque: {missing}"

    def test_no_duplicate_emails(self, pool):
        emails = [cv.get("email") for cv in pool if cv.get("email")]
        assert len(emails) == len(set(emails)), (
            f"Emails dupliqués dans le pool: {[e for e in emails if emails.count(e) > 1]}"
        )

    def test_years_of_experience_is_positive_int(self, pool):
        for i, cv in enumerate(pool):
            yoe = cv.get("years_of_experience")
            assert isinstance(yoe, int) and yoe > 0, (
                f"Entrée {i}: years_of_experience doit être un entier positif, reçu: {yoe}"
            )


# ── Section 5 : mock_gemini/main.py — tests sans Docker ───────────────────────


class TestMockGeminiService:
    """
    Teste les endpoints de mock_gemini/main.py directement via FastAPI TestClient
    sans démarrer Docker. Valide la conformité du format de réponse avec le SDK google-genai.
    """

    @pytest.fixture(scope="class")
    def mock_app_client(self):
        """Charge l'application mock_gemini et retourne un TestClient."""
        mock_gemini_path = Path(__file__).parent.parent.parent / "mock_gemini"
        if not (mock_gemini_path / "main.py").exists():
            pytest.skip("mock_gemini/main.py introuvable")

        mock_main_file = mock_gemini_path / "main.py"
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("mock_gemini_main", mock_main_file)
            mock_main = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mock_main)
            return TestClient(mock_main.app)
        except Exception as e:
            pytest.skip(f"Impossible de charger mock_gemini/main.py: {e}")

    def test_health_endpoint(self, mock_app_client):
        resp = mock_app_client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "pool_size" in data

    def test_generate_content_returns_valid_gemini_format(self, mock_app_client):
        """generateContent doit retourner le format attendu par le SDK google-genai."""
        payload = {
            "contents": [{"parts": [{"text": "CV de Alice Martin, Cloud Architect GCP."}], "role": "user"}]
        }
        resp = mock_app_client.post("/v1beta/models/gemini-2.0-flash:generateContent", json=payload)
        assert resp.status_code == 200
        data = resp.json()

        # Format SDK google-genai
        assert "candidates" in data, "Réponse doit contenir 'candidates'"
        assert len(data["candidates"]) >= 1
        candidate = data["candidates"][0]
        assert "content" in candidate
        assert "parts" in candidate["content"]
        assert len(candidate["content"]["parts"]) >= 1
        assert "text" in candidate["content"]["parts"][0]

        # Le text doit être un JSON parsable avec is_cv
        text = candidate["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        assert "is_cv" in parsed, "La réponse du mock doit contenir 'is_cv'"
        assert parsed["is_cv"] is True, "Le mock doit toujours retourner is_cv=True"
        assert "competencies" in parsed

        # usageMetadata doit être présent
        assert "usageMetadata" in data
        assert "promptTokenCount" in data["usageMetadata"]

    def test_generate_content_is_deterministic(self, mock_app_client):
        """
        Même input → même extraction (hash déterministe).
        Garantit la reproductibilité des tests de perf.
        """
        payload = {
            "contents": [{"parts": [{"text": "Texte CV reproductible FIXED_INPUT_42"}], "role": "user"}]
        }
        resp1 = mock_app_client.post("/v1beta/models/gemini-3.1-flash:generateContent", json=payload)
        resp2 = mock_app_client.post("/v1beta/models/gemini-3.1-flash:generateContent", json=payload)

        text1 = resp1.json()["candidates"][0]["content"]["parts"][0]["text"]
        text2 = resp2.json()["candidates"][0]["content"]["parts"][0]["text"]
        assert text1 == text2, "generateContent doit être déterministe pour le même input"

    def test_embed_content_returns_correct_dimension(self, mock_app_client):
        """embedContent doit retourner un vecteur de MOCK_LLM_EMBEDDING_DIM dimensions (défaut 3072)."""
        payload = {
            "content": {"parts": [{"text": "Consultant Python senior GCP."}]}
        }
        resp = mock_app_client.post(
            "/v1beta/models/gemini-embedding-001:embedContent", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()

        assert "embedding" in data, "Réponse doit contenir 'embedding'"
        assert "values" in data["embedding"], "embedding doit contenir 'values'"
        values = data["embedding"]["values"]
        assert isinstance(values, list)

        expected_dim = int(os.getenv("MOCK_LLM_EMBEDDING_DIM", "3072"))
        assert len(values) == expected_dim, (
            f"Dimension attendue: {expected_dim}, reçue: {len(values)}"
        )
        # Vecteur unitaire : norme ≈ 1.0
        import math
        norm = math.sqrt(sum(v * v for v in values))
        assert abs(norm - 1.0) < 0.01, f"Le vecteur doit être unitaire (norme≈1), reçu: {norm:.4f}"

    def test_embed_content_is_deterministic(self, mock_app_client):
        """Même texte → même vecteur (reproductibilité des tests de perf)."""
        payload = {"content": {"parts": [{"text": "FIXED_TEXT_DETERMINISM_CHECK"}]}}
        r1 = mock_app_client.post("/v1beta/models/gemini-embedding-001:embedContent", json=payload)
        r2 = mock_app_client.post("/v1beta/models/gemini-embedding-001:embedContent", json=payload)
        assert r1.json()["embedding"]["values"] == r2.json()["embedding"]["values"]

    def test_different_inputs_produce_different_vectors(self, mock_app_client):
        """Deux inputs différents → vecteurs différents (isolation des profils)."""
        p1 = {"content": {"parts": [{"text": "Alice Martin Cloud Architect"}]}}
        p2 = {"content": {"parts": [{"text": "Bruno Leclerc Data Engineer BigQuery"}]}}
        r1 = mock_app_client.post("/v1beta/models/gemini-embedding-001:embedContent", json=p1)
        r2 = mock_app_client.post("/v1beta/models/gemini-embedding-001:embedContent", json=p2)
        assert r1.json()["embedding"]["values"] != r2.json()["embedding"]["values"], (
            "Des inputs différents doivent produire des vecteurs différents"
        )

    def test_batch_embed_returns_multiple_vectors(self, mock_app_client):
        """batchEmbedContents doit retourner autant de vecteurs que de requêtes."""
        payload = {
            "requests": [
                {"content": {"parts": [{"text": "CV 1"}]}},
                {"content": {"parts": [{"text": "CV 2"}]}},
                {"content": {"parts": [{"text": "CV 3"}]}},
            ]
        }
        resp = mock_app_client.post(
            "/v1beta/models/gemini-embedding-001:batchEmbedContents", json=payload
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "embeddings" in data
        assert len(data["embeddings"]) == 3, "batchEmbedContents doit retourner 3 vecteurs"
        for emb in data["embeddings"]:
            assert "values" in emb
            assert len(emb["values"]) == int(os.getenv("MOCK_LLM_EMBEDDING_DIM", "3072"))

    def test_model_list_endpoint(self, mock_app_client):
        """GET /models doit retourner une liste de modèles (health check SDK)."""
        resp = mock_app_client.get("/v1beta/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data
        assert len(data["models"]) >= 1

    def test_batch_prediction_job_lifecycle(self, mock_app_client):
        """
        POST batchPredictionJobs → JOB_STATE_RUNNING
        GET batchPredictionJobs/{id} → JOB_STATE_RUNNING (ou SUCCEEDED après latence).
        """
        payload = {"displayName": "test-batch-job", "inputConfig": {}}
        resp = mock_app_client.post(
            "/v1/projects/my-project/locations/europe-west1/batchPredictionJobs",
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert data["state"] == "JOB_STATE_RUNNING"

        # Extraire l'ID du job
        job_id = data["name"].split("/")[-1]

        # Poll status
        status_resp = mock_app_client.get(
            f"/v1/projects/my-project/locations/europe-west1/batchPredictionJobs/{job_id}"
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["state"] in ("JOB_STATE_RUNNING", "JOB_STATE_SUCCEEDED")
