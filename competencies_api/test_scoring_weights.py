"""Tests unitaires pour les fonctions de pondération du scoring IA v2.

Couvre :
- _compute_recency_weight : decay exponentiel selon l'ancienneté de la mission
- _parse_duration_months : parseur de durée texte FR/EN
- _duration_multiplier : multiplicateur normalisé 0.5-1.5
- _get_mission_bonus : bonus par type de mission (audit, conseil, accompagnement...)
"""
import math
import sys
import os

# Injection du path pour importer le module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src", "competencies"))
sys.path.insert(0, os.path.dirname(__file__))

import pytest
from datetime import date

# Import direct des fonctions pures (pas besoin de FastAPI/BDD)
from src.competencies.helpers import (
    _compute_recency_weight,
    _parse_duration_months,
    _duration_multiplier,
    _get_mission_bonus,
    COMPETENCY_DECAY_LAMBDA,
    MISSION_TYPE_BONUS,
)


class TestComputeRecencyWeight:
    """Tests pour la fonction de decay temporel."""

    def test_present_mission_returns_max_weight(self):
        """Une mission en cours doit avoir un poids de 1.0."""
        assert _compute_recency_weight("present") == 1.0
        assert _compute_recency_weight("en cours") == 1.0
        assert _compute_recency_weight("current") == 1.0
        assert _compute_recency_weight(None) == 1.0
        assert _compute_recency_weight("") == 1.0

    def test_current_year_returns_near_max(self):
        """Une mission terminée cette année doit avoir un poids proche de 1.0."""
        current_year = str(date.today().year)
        weight = _compute_recency_weight(current_year)
        assert weight == 1.0  # 0 ans d'écart → e^0 = 1.0

    def test_one_year_ago(self):
        """Vérification du poids à 1 an d'ancienneté avec λ=0.1."""
        year_ago = str(date.today().year - 1)
        weight = _compute_recency_weight(year_ago)
        expected = round(math.exp(-COMPETENCY_DECAY_LAMBDA * 1), 2)
        assert weight == pytest.approx(expected, abs=0.01)

    def test_five_years_ago(self):
        """Vérification du poids à 5 ans (devrait être ~0.61)."""
        year = str(date.today().year - 5)
        weight = _compute_recency_weight(year)
        expected = round(math.exp(-COMPETENCY_DECAY_LAMBDA * 5), 2)
        assert weight == pytest.approx(expected, abs=0.01)
        assert weight > 0.0, "Le poids ne doit jamais être 0 (missions anciennes ont toujours de la valeur)"

    def test_ten_years_ago(self):
        """Vérification du poids à 10 ans (devrait être ~0.37)."""
        year = str(date.today().year - 10)
        weight = _compute_recency_weight(year)
        assert weight == pytest.approx(0.37, abs=0.02)
        assert weight > 0.0, "Le poids ne doit jamais être 0"

    def test_fifteen_years_ago_still_positive(self):
        """Une mission de 2010 doit toujours avoir un poids > 0."""
        weight = _compute_recency_weight("2010")
        assert weight > 0.0
        assert weight < 0.5, "Une mission très ancienne doit avoir un poids significativement réduit"

    def test_yyyy_mm_format(self):
        """Format YYYY-MM doit être parsé correctement (seule l'année compte)."""
        year_ago_mm = f"{date.today().year - 2}-06"
        weight = _compute_recency_weight(year_ago_mm)
        expected = round(math.exp(-COMPETENCY_DECAY_LAMBDA * 2), 2)
        assert weight == pytest.approx(expected, abs=0.01)

    def test_unparseable_date_returns_neutral(self):
        """Une date non parseable retourne le poids neutre 0.7."""
        assert _compute_recency_weight("invalide") == 0.7
        assert _compute_recency_weight("N/A") == 0.7


class TestParseDurationMonths:
    """Tests pour le parseur de durée texte."""

    def test_years_only_french(self):
        assert _parse_duration_months("2 ans") == 24
        assert _parse_duration_months("1 an") == 12
        assert _parse_duration_months("3 ans") == 36

    def test_months_only_french(self):
        assert _parse_duration_months("6 mois") == 6
        assert _parse_duration_months("18 mois") == 18

    def test_years_and_months_french(self):
        assert _parse_duration_months("1 an 6 mois") == 18
        assert _parse_duration_months("2 ans 3 mois") == 27

    def test_years_english(self):
        assert _parse_duration_months("2 years") == 24
        assert _parse_duration_months("1 year") == 12

    def test_months_english(self):
        assert _parse_duration_months("6 months") == 6
        assert _parse_duration_months("18 months") == 18

    def test_combined_english(self):
        assert _parse_duration_months("1 year 3 months") == 15

    def test_none_returns_none(self):
        assert _parse_duration_months(None) is None
        assert _parse_duration_months("") is None

    def test_unparseable_returns_none(self):
        assert _parse_duration_months("N/A") is None
        assert _parse_duration_months("longue mission") is None


class TestDurationMultiplier:
    """Tests pour le multiplicateur de durée."""

    def test_none_returns_neutral(self):
        """Durée inconnue → multiplicateur neutre 1.0."""
        assert _duration_multiplier(None) == 1.0

    def test_twelve_months_is_baseline(self):
        """12 mois = 1 an → multiplicateur de référence 1.0."""
        assert _duration_multiplier(12) == pytest.approx(1.0, abs=0.01)

    def test_six_months_lower(self):
        """6 mois → multiplicateur réduit ~0.75."""
        assert _duration_multiplier(6) == pytest.approx(0.75, abs=0.01)

    def test_twenty_four_months_capped(self):
        """24 mois → multiplicateur cap à 1.5."""
        assert _duration_multiplier(24) == 1.5

    def test_thirty_six_months_still_capped(self):
        """36 mois → toujours cappé à 1.5."""
        assert _duration_multiplier(36) == 1.5

    def test_one_month_minimum(self):
        """1 mois → multiplicateur minimum ~0.54 (pas en dessous de 0.5)."""
        mult = _duration_multiplier(1)
        assert mult >= 0.5
        assert mult < 0.7

    def test_boundaries(self):
        """Le multiplicateur ne sort jamais de [0.5, 1.5]."""
        for months in [0, 1, 3, 6, 12, 18, 24, 36, 48, 60]:
            mult = _duration_multiplier(months)
            assert 0.5 <= mult <= 1.5, f"Multiplicateur hors bornes pour {months} mois: {mult}"


class TestGetMissionBonus:
    """Tests pour la détection de type et bonus de valeur ajoutée."""

    def test_audit_bonus(self):
        label, bonus = _get_mission_bonus("audit")
        assert bonus == MISSION_TYPE_BONUS["audit"]
        assert bonus == 0.5
        assert "audit" in label.lower() or "diagnostic" in label.lower()

    def test_conseil_bonus(self):
        _, bonus = _get_mission_bonus("conseil")
        assert bonus == 0.5

    def test_accompagnement_bonus(self):
        _, bonus = _get_mission_bonus("accompagnement")
        assert bonus == 0.3

    def test_formation_bonus(self):
        _, bonus = _get_mission_bonus("formation")
        assert bonus == 0.4

    def test_expertise_bonus(self):
        _, bonus = _get_mission_bonus("expertise")
        assert bonus == 0.3

    def test_build_no_bonus(self):
        _, bonus = _get_mission_bonus("build")
        assert bonus == 0.0

    def test_none_defaults_to_build(self):
        _, bonus = _get_mission_bonus(None)
        assert bonus == 0.0

    def test_unknown_type_no_bonus(self):
        """Un type inconnu → pas de bonus (défaut sûr)."""
        _, bonus = _get_mission_bonus("unknown_type")
        assert bonus == 0.0

    def test_case_insensitive(self):
        """Le type doit être insensible à la casse."""
        _, bonus_upper = _get_mission_bonus("AUDIT")
        assert bonus_upper == 0.5
        _, bonus_mixed = _get_mission_bonus("Conseil")
        assert bonus_mixed == 0.5


class TestScoringCoherence:
    """Tests de cohérence du scoring global."""

    def test_recent_mission_outweighs_old(self):
        """Une mission récente doit avoir un poids strictement supérieur à une mission ancienne."""
        recent_weight = _compute_recency_weight(str(date.today().year))
        old_weight = _compute_recency_weight("2010")
        assert recent_weight > old_weight

    def test_long_mission_outweighs_short(self):
        """Une mission longue doit avoir un multiplicateur supérieur à une mission courte."""
        assert _duration_multiplier(24) > _duration_multiplier(3)

    def test_value_add_missions_have_bonus(self):
        """Toutes les missions à valeur ajoutée doivent avoir un bonus > 0."""
        for mtype in ["audit", "conseil", "accompagnement", "formation", "expertise"]:
            _, bonus = _get_mission_bonus(mtype)
            assert bonus > 0.0, f"Type '{mtype}' devrait avoir un bonus positif"

    def test_build_missions_have_no_bonus(self):
        """Les missions build standard n'ont pas de bonus."""
        _, bonus = _get_mission_bonus("build")
        assert bonus == 0.0
