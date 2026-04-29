"""
Tests unitaires pour scoring_service.py (Competencies API).

Teste les utilitaires de pondération et les branches critiques du pipeline
sans appels réels à Vertex AI, GCS ou la DB.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone

from src.competencies.scoring_service import (
    _compute_recency_weight,
    _parse_duration_months,
    _duration_multiplier,
    _get_mission_bonus,
    _estimate_duration_from_dates,
    _build_scoring_prompt,
)


# ── Tests _compute_recency_weight ──────────────────────────────────────────────

def test_compute_recency_weight_recent():
    """Mission terminée il y a moins de 1 an → poids proche de 1.0."""
    recent = datetime.now(timezone.utc).strftime("%Y-%m")
    weight = _compute_recency_weight(recent)
    assert 0.9 <= weight <= 1.0


def test_compute_recency_weight_old():
    """Mission terminée il y a 10 ans → poids faible."""
    weight = _compute_recency_weight("2015-01")
    assert weight < 0.5


def test_compute_recency_weight_none():
    """Sans date de fin, on retourne un poids par défaut (1.0 ou non-nul)."""
    weight = _compute_recency_weight(None)
    assert isinstance(weight, float)
    assert weight >= 0.0


# ── Tests _parse_duration_months ───────────────────────────────────────────────

def test_parse_duration_months_standard():
    assert _parse_duration_months("6 mois") == 6


def test_parse_duration_months_years():
    """Supporte 'X an(s)' → conversion en mois."""
    result = _parse_duration_months("2 ans")
    assert result == 24


def test_parse_duration_months_none():
    assert _parse_duration_months(None) is None


def test_parse_duration_months_invalid():
    assert _parse_duration_months("pas une durée") is None


# ── Tests _duration_multiplier ─────────────────────────────────────────────────

def test_duration_multiplier_long_mission():
    """Mission > 12 mois → multiplicateur >= 1.0."""
    mult = _duration_multiplier(18)
    assert mult >= 1.0


def test_duration_multiplier_short_mission():
    """Mission < 3 mois → multiplicateur < 1.0."""
    mult = _duration_multiplier(1)
    assert mult < 1.0


def test_duration_multiplier_none():
    """Sans durée, retourne un multiplicateur par défaut."""
    mult = _duration_multiplier(None)
    assert isinstance(mult, float)
    assert mult > 0


# ── Tests _get_mission_bonus ───────────────────────────────────────────────────

def test_get_mission_bonus_audit():
    label, bonus = _get_mission_bonus("audit")
    assert bonus == 0.5
    assert "Audit" in label


def test_get_mission_bonus_build():
    label, bonus = _get_mission_bonus("build")
    assert bonus == 0.0
    assert "Build" in label


def test_get_mission_bonus_unknown():
    """Type inconnu → bonus 0.0 et un label générique."""
    label, bonus = _get_mission_bonus("inconnu")
    assert bonus == 0.0


def test_get_mission_bonus_none():
    label, bonus = _get_mission_bonus(None)
    assert isinstance(bonus, float)


# ── Tests _estimate_duration_from_dates ────────────────────────────────────────

def test_estimate_duration_from_dates_valid():
    result = _estimate_duration_from_dates("2023-01", "2023-07")
    assert result is not None
    assert "6" in result or "mois" in result.lower()


def test_estimate_duration_from_dates_none():
    assert _estimate_duration_from_dates(None, None) is None


def test_estimate_duration_from_dates_partial():
    result = _estimate_duration_from_dates("2023-01", None)
    assert result is None or isinstance(result, str)


# ── Tests _build_scoring_prompt ────────────────────────────────────────────────

def test_build_scoring_prompt_contains_competency():
    prompt = _build_scoring_prompt("Python", [{"title": "Backend Dev"}])
    assert "Python" in prompt


def test_build_scoring_prompt_empty_missions():
    """Sans missions, le prompt retourne une chaîne vide (comportement attendu)."""
    prompt = _build_scoring_prompt("DevOps", [])
    assert prompt == ""


def test_build_scoring_prompt_json_schema():
    """Le prompt doit demander une réponse structurée JSON (score entre 0 et 5)."""
    prompt = _build_scoring_prompt("Terraform", [{"title": "Infra Cloud"}])
    assert "score" in prompt.lower() or "json" in prompt.lower() or "5" in prompt
