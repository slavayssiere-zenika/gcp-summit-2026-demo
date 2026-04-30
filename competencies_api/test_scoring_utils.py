"""
test_scoring_utils.py — Tests unitaires pour scoring_utils.py.

Coverage cible : 59% → 90%+
Fonctions testées :
  - _compute_recency_weight()
  - _parse_duration_months()
  - _duration_multiplier()
  - _get_mission_bonus()
  - _estimate_duration_from_dates()
  - _format_mission_v2()
  - _build_scoring_prompt()
  - _build_jsonl_lines()
  - _parse_scoring_results_gcs()
"""
import json
import os
import sys
import pytest

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./competencies_test.db")
os.environ.setdefault("SECRET_KEY", "testsecret")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.competencies.scoring_utils import (
    _compute_recency_weight,
    _parse_duration_months,
    _duration_multiplier,
    _get_mission_bonus,
    _estimate_duration_from_dates,
    _format_mission_v2,
    _build_scoring_prompt,
    _build_jsonl_lines,
    _parse_scoring_results_gcs,
)


# ── _compute_recency_weight ───────────────────────────────────────────────────

class TestRecencyWeight:
    def test_none_returns_1(self):
        assert _compute_recency_weight(None) == 1.0

    def test_empty_returns_1(self):
        assert _compute_recency_weight("") == 1.0

    def test_present_returns_1(self):
        assert _compute_recency_weight("present") == 1.0
        assert _compute_recency_weight("en cours") == 1.0
        assert _compute_recency_weight("current") == 1.0

    def test_current_year_close_to_1(self):
        import datetime
        current_year = datetime.datetime.now().year
        result = _compute_recency_weight(str(current_year))
        assert result == 1.0

    def test_old_date_decays(self):
        result = _compute_recency_weight("2010")
        assert result < 0.5

    def test_medium_date_decays_moderately(self):
        result = _compute_recency_weight("2020")
        assert 0.3 < result < 1.0

    def test_invalid_format_returns_1(self):
        assert _compute_recency_weight("invalid-date") == 1.0

    def test_result_is_float(self):
        assert isinstance(_compute_recency_weight("2019"), float)


# ── _parse_duration_months ────────────────────────────────────────────────────

class TestParseDurationMonths:
    def test_none_returns_none(self):
        assert _parse_duration_months(None) is None

    def test_mois(self):
        assert _parse_duration_months("6 mois") == 6

    def test_mois_plural(self):
        assert _parse_duration_months("12 Mois") == 12

    def test_an_singular(self):
        assert _parse_duration_months("1 an") == 12

    def test_ans_plural(self):
        assert _parse_duration_months("2 ans") == 24

    def test_no_match_returns_none(self):
        assert _parse_duration_months("long terme") is None

    def test_whitespace_variants(self):
        assert _parse_duration_months("3mois") == 3


# ── _duration_multiplier ──────────────────────────────────────────────────────

class TestDurationMultiplier:
    def test_none_returns_1(self):
        assert _duration_multiplier(None) == 1.0

    def test_short_mission(self):
        assert _duration_multiplier(2) == 0.5

    def test_medium_mission(self):
        assert _duration_multiplier(6) == 1.0

    def test_long_mission(self):
        assert _duration_multiplier(12) == 1.2

    def test_very_long_mission(self):
        assert _duration_multiplier(24) == 1.5

    def test_boundary_9_months(self):
        assert _duration_multiplier(9) == 1.2

    def test_boundary_18_months(self):
        assert _duration_multiplier(18) == 1.5


# ── _get_mission_bonus ────────────────────────────────────────────────────────

class TestMissionBonus:
    def test_audit(self):
        label, bonus = _get_mission_bonus("audit")
        assert bonus == 0.5
        assert "audit" in label.lower() or "Audit" in label

    def test_conseil(self):
        _, bonus = _get_mission_bonus("conseil")
        assert bonus == 0.5

    def test_formation(self):
        _, bonus = _get_mission_bonus("formation")
        assert bonus == 0.4

    def test_build_no_bonus(self):
        _, bonus = _get_mission_bonus("build")
        assert bonus == 0.0

    def test_unknown_type_no_bonus(self):
        label, bonus = _get_mission_bonus("unknown_type")
        assert bonus == 0.0
        assert label == "Autre mission"

    def test_none_type(self):
        label, bonus = _get_mission_bonus(None)
        assert bonus == 0.0

    def test_case_insensitive(self):
        _, bonus = _get_mission_bonus("AUDIT")
        assert bonus == 0.5


# ── _estimate_duration_from_dates ─────────────────────────────────────────────

class TestEstimateDuration:
    def test_none_start_returns_none(self):
        assert _estimate_duration_from_dates(None, "2020") is None

    def test_none_end_returns_none(self):
        assert _estimate_duration_from_dates("2019", None) is None

    def test_simple_years(self):
        result = _estimate_duration_from_dates("2019-01", "2020-01")
        assert result == "12 mois"

    def test_same_month(self):
        result = _estimate_duration_from_dates("2020-01", "2020-01")
        # max(1, 0) = 1
        assert result == "1 mois"

    def test_present_end(self):
        result = _estimate_duration_from_dates("2020-01", "present")
        # Should be > 0 months
        assert result is not None
        assert "mois" in result

    def test_invalid_dates_returns_none(self):
        assert _estimate_duration_from_dates("not-a-date", "2020") is None


# ── _build_scoring_prompt ─────────────────────────────────────────────────────

class TestBuildScoringPrompt:
    def test_empty_missions_returns_empty(self):
        result = _build_scoring_prompt("Python", [])
        assert result == ""

    def test_prompt_contains_competency_name(self):
        missions = [{"title": "Dev", "company": "ACME",
                     "competencies": ["Python"], "end_date": "2023"}]
        result = _build_scoring_prompt("Python", missions)
        assert "Python" in result

    def test_prompt_contains_json_instruction(self):
        missions = [{"title": "Dev", "company": "X",
                     "competencies": ["Java"], "end_date": "2022"}]
        result = _build_scoring_prompt("Java", missions)
        assert "JSON" in result or "json" in result
        assert "score" in result
        assert "justification" in result

    def test_prompt_filters_relevant_missions(self):
        missions = [
            {"title": "Python Dev", "company": "A",
             "competencies": ["Python", "Django"], "end_date": "2023"},
            {"title": "Java Dev", "company": "B",
             "competencies": ["Java", "Spring"], "end_date": "2022"},
        ]
        result = _build_scoring_prompt("Python", missions)
        # Missions Python doivent apparaître
        assert "Python Dev" in result or "Django" in result

    def test_prompt_falls_back_to_all_missions(self):
        """Quand aucune mission n'est pertinente, on prend les 5 premières."""
        missions = [{"title": "Ruby Dev", "company": "X",
                     "competencies": ["Ruby"], "end_date": "2021"}]
        result = _build_scoring_prompt("Python", missions)
        # Doit quand même générer un prompt
        assert len(result) > 0


# ── _build_jsonl_lines ────────────────────────────────────────────────────────

class TestBuildJsonlLines:
    def _sample_user_comp_list(self):
        return [(1, 10, "Python"), (1, 11, "Django"), (2, 10, "Python")]

    def _sample_missions_map(self):
        mission = {"title": "Dev", "company": "X",
                   "competencies": ["Python"], "end_date": "2023"}
        return {1: [mission], 2: [mission]}

    def test_returns_lines_index_skipped(self):
        lines, index, skipped = _build_jsonl_lines(
            self._sample_user_comp_list(), self._sample_missions_map()
        )
        assert isinstance(lines, list)
        assert isinstance(index, dict)
        assert isinstance(skipped, int)

    def test_no_missions_skips_pair(self):
        """User sans missions → paire ignorée."""
        user_comp = [(99, 10, "Python")]
        lines, index, skipped = _build_jsonl_lines(user_comp, {})
        assert len(lines) == 0
        assert skipped == 1

    def test_lines_are_valid_json(self):
        lines, _, _ = _build_jsonl_lines(
            self._sample_user_comp_list(), self._sample_missions_map()
        )
        for line in lines:
            data = json.loads(line)
            assert "id" in data
            assert "request" in data
            assert "contents" in data["request"]

    def test_index_keys_match_line_ids(self):
        lines, index, _ = _build_jsonl_lines(
            self._sample_user_comp_list(), self._sample_missions_map()
        )
        for line in lines:
            data = json.loads(line)
            assert data["id"] in index

    def test_index_values_are_tuples(self):
        _, index, _ = _build_jsonl_lines(
            self._sample_user_comp_list(), self._sample_missions_map()
        )
        for key, value in index.items():
            assert len(value) == 3  # (user_id, comp_id, comp_name)

    def test_empty_user_comp_list(self):
        lines, index, skipped = _build_jsonl_lines([], {})
        assert lines == []
        assert index == {}
        assert skipped == 0


# ── _parse_scoring_results_gcs ────────────────────────────────────────────────

class TestParseScoringResultsGCS:
    def _make_index(self):
        return {"score-1-10": (1, 10, "Python"), "score-2-11": (2, 11, "Django")}

    def _make_valid_line(self, key, score=3.5, justification="Good"):
        record = {
            "id": key,
            "response": {
                "candidates": [{"content": {"parts": [{"text": json.dumps({
                    "score": score, "justification": justification
                })}]}}],
                "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50}
            }
        }
        return json.dumps(record)

    def test_returns_results_and_usage(self):
        index = self._make_index()
        line = self._make_valid_line("score-1-10", score=4.0)
        results, usage = _parse_scoring_results_gcs([line], index)
        assert len(results) == 1
        assert results[0][0] == 1   # user_id
        assert results[0][1] == 10  # comp_id
        assert results[0][3] == 4.0 # score

    def test_empty_input(self):
        results, usage = _parse_scoring_results_gcs([], {})
        assert results == []
        assert usage == {}

    def test_malformed_json_skipped(self):
        results, usage = _parse_scoring_results_gcs(["not json"], self._make_index())
        assert results == []

    def test_empty_lines_skipped(self):
        results, usage = _parse_scoring_results_gcs(["", "   "], self._make_index())
        assert results == []

    def test_unknown_key_skipped(self):
        line = self._make_valid_line("score-99-99", score=3.0)
        results, _ = _parse_scoring_results_gcs([line], self._make_index())
        assert results == []

    def test_score_clamped_to_5(self):
        """Score > 5 doit être ramené à 5."""
        index = {"score-1-10": (1, 10, "Python")}
        line = self._make_valid_line("score-1-10", score=7.0)
        results, _ = _parse_scoring_results_gcs([line], index)
        assert results[0][3] <= 5.0

    def test_score_clamped_to_0(self):
        """Score < 0 doit être ramené à 0."""
        index = {"score-1-10": (1, 10, "Python")}
        line = self._make_valid_line("score-1-10", score=-1.0)
        results, _ = _parse_scoring_results_gcs([line], index)
        assert results[0][3] >= 0.0

    def test_score_rounded_to_half_step(self):
        """Score doit être arrondi au pas de 0.5."""
        index = {"score-1-10": (1, 10, "Python")}
        line = self._make_valid_line("score-1-10", score=3.3)
        results, _ = _parse_scoring_results_gcs([line], index)
        score = results[0][3]
        assert score % 0.5 == 0.0

    def test_token_usage_aggregated_per_user(self):
        """Tokens de plusieurs lignes pour le même user sont agrégés."""
        index = {
            "score-1-10": (1, 10, "Python"),
            "score-1-11": (1, 11, "Django"),
        }
        line1 = self._make_valid_line("score-1-10", score=3.0)
        line2 = self._make_valid_line("score-1-11", score=4.0)
        _, usage = _parse_scoring_results_gcs([line1, line2], index)
        assert usage[1]["prompt_token_count"] == 200  # 100 + 100
        assert usage[1]["candidates_token_count"] == 100  # 50 + 50

    def test_multiple_users_separate_usage(self):
        index = self._make_index()
        line1 = self._make_valid_line("score-1-10", score=3.0)
        line2 = self._make_valid_line("score-2-11", score=4.5)
        _, usage = _parse_scoring_results_gcs([line1, line2], index)
        assert 1 in usage
        assert 2 in usage

    def test_raw_json_with_prefix_text(self):
        """Réponse LLM avec texte avant le JSON → doit être parsée."""
        index = {"score-1-10": (1, 10, "Python")}
        inner_json = json.dumps({"score": 3.5, "justification": "Bonne maîtrise"})
        prefixed = f"Voici ma réponse : {inner_json}"
        record = {
            "id": "score-1-10",
            "response": {
                "candidates": [{"content": {"parts": [{"text": prefixed}]}}],
                "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20}
            }
        }
        results, _ = _parse_scoring_results_gcs([json.dumps(record)], index)
        assert len(results) == 1
        assert results[0][3] == 3.5
