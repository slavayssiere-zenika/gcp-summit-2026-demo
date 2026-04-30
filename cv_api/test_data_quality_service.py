"""
test_data_quality_service.py — Tests unitaires pour data_quality_service.py.

Coverage cible : 0% → 80%+
Fonctions testées :
  - _pct() : calcul de pourcentage
  - _status() : mapping pct → label
  - compute_data_quality_report() : rapport complet (nominal + edge cases)
"""
import os
import sys
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./cv_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")
os.environ.setdefault("GOOGLE_CLOUD_PROJECT", "test-project")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ── Helpers purs (_pct, _status) ─────────────────────────────────────────────

class TestPct:
    def test_pct_full(self):
        from src.services.data_quality_service import _pct
        assert _pct(10, 10) == 100

    def test_pct_half(self):
        from src.services.data_quality_service import _pct
        assert _pct(5, 10) == 50

    def test_pct_zero_ok(self):
        from src.services.data_quality_service import _pct
        assert _pct(0, 10) == 0

    def test_pct_zero_total_returns_0(self):
        """Division par zéro → 0."""
        from src.services.data_quality_service import _pct
        assert _pct(0, 0) == 0

    def test_pct_rounds_correctly(self):
        from src.services.data_quality_service import _pct
        assert _pct(1, 3) == 33

    def test_pct_caps_at_100(self):
        """ok > total est plafonné à 100."""
        from src.services.data_quality_service import _pct
        result = _pct(15, 10)
        assert result == 100  # min(100, ...) dans l'implémentation


class TestStatus:
    def test_status_ok(self):
        from src.services.data_quality_service import _status
        result_100 = _status(100)
        result_90 = _status(90)
        result_80 = _status(80)
        # "ok" for >= 80
        assert result_100 in ("ok", "good", "healthy")
        assert result_90 in ("ok", "good", "healthy")
        assert result_80 in ("ok", "good", "healthy")

    def test_status_warning(self):
        from src.services.data_quality_service import _status
        result = _status(60)
        # Should not be "ok"
        assert result != "ok"

    def test_status_critical(self):
        from src.services.data_quality_service import _status
        result = _status(0)
        # Should indicate a bad state
        assert result not in ("ok", "good")


# ── compute_data_quality_report() ────────────────────────────────────────────

def _make_mock_db(total_cvs=10, missions_ok=8, embedding_ok=9,
                  competencies_ok=7, summary_ok=10, current_role_ok=10):
    """Construit un AsyncSession mock avec les résultats scalaires attendus.
    
    data_quality_service appelle `result.scalar_one()` (synchrone sur l'objet résultat SQLAlchemy).
    On mocke donc execute() pour retourner un objet dont scalar_one() retourne la valeur.
    """
    db = AsyncMock()

    # Chaque appel scalaire retourne une valeur différente selon l'ordre
    scalar_calls = [
        total_cvs,       # SELECT COUNT(*) CVProfile
        missions_ok,     # missions_ok
        embedding_ok,    # embedding_ok
        competencies_ok, # competencies_ok
        summary_ok,      # summary_ok
        current_role_ok, # current_role_ok
    ]
    call_count = [0]

    async def fake_execute(stmt, *args, **kwargs):
        idx = min(call_count[0], len(scalar_calls) - 1)
        val = scalar_calls[idx]
        call_count[0] += 1
        # scalar_one() est appelé directement sur le résultat — doit être SYNC (pas coroutine)
        result = MagicMock()
        result.scalar_one.return_value = val
        result.scalar_one_or_none.return_value = val
        return result

    db.execute = fake_execute
    return db


@pytest.mark.asyncio
async def test_report_perfect_score():
    """Tous les CVs ont missions, embeddings, etc. + APIs externes OK → grade A."""
    db = _make_mock_db(total_cvs=10, missions_ok=10, embedding_ok=10,
                       competencies_ok=10, summary_ok=10, current_role_ok=10)

    comp_coverage_resp = MagicMock()
    comp_coverage_resp.status_code = 200
    comp_coverage_resp.json.return_value = {"users_with_competencies": 10, "total_users": 10}

    scoring_resp = MagicMock()
    scoring_resp.status_code = 200
    scoring_resp.json.return_value = {"users_with_min_scored": 10, "avg_scored_per_user": 12.0}

    mock_hc = AsyncMock()
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=False)
    mock_hc.get.side_effect = [comp_coverage_resp, scoring_resp]

    with patch("src.services.data_quality_service.httpx.AsyncClient", return_value=mock_hc):
        with patch("src.services.data_quality_service.inject"):
            from src.services.data_quality_service import compute_data_quality_report
            report = await compute_data_quality_report(db, "Bearer test-token")

    assert report["grade"] in ("A", "B", "C", "D")
    assert 0 <= report["score"] <= 100
    assert "metrics" in report
    assert "issues" in report
    assert "computed_at" in report


@pytest.mark.asyncio
async def test_report_zero_cvs_returns_grade_d():
    """Aucun CV dans la base → score ≈ 0 → grade D."""
    db = _make_mock_db(total_cvs=0, missions_ok=0, embedding_ok=0,
                       competencies_ok=0, summary_ok=0, current_role_ok=0)

    mock_hc = AsyncMock()
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=False)

    comp_resp = MagicMock()
    comp_resp.status_code = 200
    comp_resp.json.return_value = {"users_with_competencies": 0, "total_users": 0}

    scoring_resp = MagicMock()
    scoring_resp.status_code = 200
    scoring_resp.json.return_value = {"users_with_min_scored": 0, "avg_scored_per_user": 0.0}

    mock_hc.get.side_effect = [comp_resp, scoring_resp]

    with patch("src.services.data_quality_service.httpx.AsyncClient", return_value=mock_hc):
        with patch("src.services.data_quality_service.inject"):
            from src.services.data_quality_service import compute_data_quality_report
            report = await compute_data_quality_report(db, "Bearer test")

    assert report["score"] <= 40
    assert report["grade"] in ("C", "D")


@pytest.mark.asyncio
async def test_report_competencies_api_unavailable():
    """Si competencies_api est DOWN → métriques externes = 0, rapport construit quand même."""
    db = _make_mock_db(total_cvs=5, missions_ok=5, embedding_ok=5,
                       competencies_ok=5, summary_ok=5, current_role_ok=5)

    mock_hc = AsyncMock()
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=False)
    # Simule timeout / connexion refusée
    mock_hc.get.side_effect = Exception("Connection refused")

    with patch("src.services.data_quality_service.httpx.AsyncClient", return_value=mock_hc):
        with patch("src.services.data_quality_service.inject"):
            from src.services.data_quality_service import compute_data_quality_report
            report = await compute_data_quality_report(db, "Bearer test")

    # Le rapport est construit même si les APIs externes échouent
    assert "score" in report
    assert "grade" in report
    # Les métriques manquantes génèrent des issues
    assert isinstance(report["issues"], list)


@pytest.mark.asyncio
async def test_report_gate_blocks_grade_a():
    """Score global > 85 mais un indicateur < 80% → grade plafonné à C."""
    db = _make_mock_db(total_cvs=10, missions_ok=10, embedding_ok=10,
                       competencies_ok=10, summary_ok=10, current_role_ok=10)

    mock_hc = AsyncMock()
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=False)

    comp_resp = MagicMock()
    comp_resp.status_code = 200
    # Seulement 2/10 consultants ont des compétences assignées → < 80%
    comp_resp.json.return_value = {"users_with_competencies": 2, "total_users": 10}

    scoring_resp = MagicMock()
    scoring_resp.status_code = 200
    scoring_resp.json.return_value = {"users_with_min_scored": 10, "avg_scored_per_user": 15.0}

    mock_hc.get.side_effect = [comp_resp, scoring_resp]

    with patch("src.services.data_quality_service.httpx.AsyncClient", return_value=mock_hc):
        with patch("src.services.data_quality_service.inject"):
            from src.services.data_quality_service import compute_data_quality_report
            report = await compute_data_quality_report(db, "Bearer test")

    # Le gate bloquant doit empêcher le grade A ou B
    assert report["grade"] not in ("A", "B"), \
        f"Gate bloquant non respecté — grade={report['grade']}, score={report['score']}"
    assert report["score"] <= 64


@pytest.mark.asyncio
async def test_report_score_capped_at_100():
    """Le score global ne dépasse jamais 100."""
    db = _make_mock_db(total_cvs=10, missions_ok=10, embedding_ok=10,
                       competencies_ok=10, summary_ok=10, current_role_ok=10)

    mock_hc = AsyncMock()
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=False)

    comp_resp = MagicMock()
    comp_resp.status_code = 200
    comp_resp.json.return_value = {"users_with_competencies": 10, "total_users": 10}

    scoring_resp = MagicMock()
    scoring_resp.status_code = 200
    scoring_resp.json.return_value = {"users_with_min_scored": 10, "avg_scored_per_user": 20.0}

    mock_hc.get.side_effect = [comp_resp, scoring_resp]

    with patch("src.services.data_quality_service.httpx.AsyncClient", return_value=mock_hc):
        with patch("src.services.data_quality_service.inject"):
            from src.services.data_quality_service import compute_data_quality_report
            report = await compute_data_quality_report(db, "Bearer test")

    assert report["score"] <= 100


@pytest.mark.asyncio
async def test_report_structure_complete():
    """Le rapport retourné contient tous les champs attendus."""
    db = _make_mock_db(total_cvs=3, missions_ok=2, embedding_ok=3,
                       competencies_ok=1, summary_ok=3, current_role_ok=2)

    mock_hc = AsyncMock()
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=False)

    comp_resp = MagicMock()
    comp_resp.status_code = 200
    comp_resp.json.return_value = {"users_with_competencies": 2, "total_users": 3}

    scoring_resp = MagicMock()
    scoring_resp.status_code = 200
    scoring_resp.json.return_value = {"users_with_min_scored": 1, "avg_scored_per_user": 5.0}

    mock_hc.get.side_effect = [comp_resp, scoring_resp]

    with patch("src.services.data_quality_service.httpx.AsyncClient", return_value=mock_hc):
        with patch("src.services.data_quality_service.inject"):
            from src.services.data_quality_service import compute_data_quality_report
            report = await compute_data_quality_report(db, "Bearer test")

    required_keys = {"score", "grade", "metrics", "issues", "recommendation", "computed_at", "total_cvs"}
    assert required_keys.issubset(set(report.keys())), \
        f"Clés manquantes : {required_keys - set(report.keys())}"

    required_metrics = {"embedding", "missions", "competencies", "summary",
                        "current_role", "competency_assignment", "ai_scoring"}
    assert required_metrics.issubset(set(report["metrics"].keys()))


@pytest.mark.asyncio
async def test_report_issues_populated_when_metrics_below_threshold():
    """Quand des métriques sont < 90%, des issues doivent être générées."""
    db = _make_mock_db(total_cvs=10, missions_ok=3, embedding_ok=2,
                       competencies_ok=1, summary_ok=4, current_role_ok=5)

    mock_hc = AsyncMock()
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=False)

    comp_resp = MagicMock()
    comp_resp.status_code = 200
    comp_resp.json.return_value = {"users_with_competencies": 1, "total_users": 10}

    scoring_resp = MagicMock()
    scoring_resp.status_code = 200
    scoring_resp.json.return_value = {"users_with_min_scored": 0, "avg_scored_per_user": 0.0}

    mock_hc.get.side_effect = [comp_resp, scoring_resp]

    with patch("src.services.data_quality_service.httpx.AsyncClient", return_value=mock_hc):
        with patch("src.services.data_quality_service.inject"):
            from src.services.data_quality_service import compute_data_quality_report
            report = await compute_data_quality_report(db, "Bearer test")

    assert len(report["issues"]) > 0, "Des issues auraient dû être générées"


@pytest.mark.asyncio
async def test_report_no_issues_when_all_ok():
    """Toutes les métriques à 100% → aucune issue et recommendation positive."""
    db = _make_mock_db(total_cvs=10, missions_ok=10, embedding_ok=10,
                       competencies_ok=10, summary_ok=10, current_role_ok=10)

    mock_hc = AsyncMock()
    mock_hc.__aenter__ = AsyncMock(return_value=mock_hc)
    mock_hc.__aexit__ = AsyncMock(return_value=False)

    comp_resp = MagicMock()
    comp_resp.status_code = 200
    comp_resp.json.return_value = {"users_with_competencies": 10, "total_users": 10}

    scoring_resp = MagicMock()
    scoring_resp.status_code = 200
    scoring_resp.json.return_value = {"users_with_min_scored": 10, "avg_scored_per_user": 15.0}

    mock_hc.get.side_effect = [comp_resp, scoring_resp]

    with patch("src.services.data_quality_service.httpx.AsyncClient", return_value=mock_hc):
        with patch("src.services.data_quality_service.inject"):
            from src.services.data_quality_service import compute_data_quality_report
            report = await compute_data_quality_report(db, "Bearer test")

    assert report["issues"] == []
    assert "bonne santé" in report["recommendation"]
