"""
test_analytics_queries.py — Couverture complète de analytics_queries.py.

compute_taxonomy_quality() est une fonction pure (pas de DB, pas de réseau),
entièrement testable en unitaire sans mock.

Branches couvertes :
  - Taxonomie vide → score 0, grade D
  - Taxonomie équilibrée → score 100, grade A
  - Pilier concentré > 35% → pénalité + grade dégradé
  - Archives > 10% → pénalité + grade dégradé
  - Pénalités cumulées → score plancher 0
  - Grades B (70-89) et C (50-69)
  - Comptage récursif de sous-arbres
  - Pilier archives exclu du calcul de concentration
"""
import pytest

from src.competencies.analytics_queries import compute_taxonomy_quality


# ── Helpers ───────────────────────────────────────────────────────────────────

def _node(id_, name, parent_id=None):
    """Crée un objet compétence minimal compatible avec compute_taxonomy_quality."""

    class FakeComp:
        pass

    c = FakeComp()
    c.id = id_
    c.name = name
    c.parent_id = parent_id
    return c


def _archive_node(id_):
    return _node(id_, "Compétences Archives / Non classées", parent_id=None)


# ── Cas vide ──────────────────────────────────────────────────────────────────

def test_empty_taxonomy():
    result = compute_taxonomy_quality([])
    assert result["score"] == 0
    assert result["grade"] == "D"
    assert result["metrics"]["balance"]["pct"] == 0
    assert result["metrics"]["archives"]["pct"] == 0
    assert "Taxonomie vide." in result["issues"]


# ── Taxonomie minimale (1 nœud) ───────────────────────────────────────────────

def test_single_node_no_archive():
    """Un seul nœud racine : 100% dans un pilier → pénalité complète.

    count_subtree(1)=1, active_nodes=1 → max_pillar pct=100% > 35%
    score = 100 - int(100-35) = 35 → grade D.
    """
    comps = [_node(1, "Python")]
    result = compute_taxonomy_quality(comps)
    assert result["score"] == 35
    assert result["grade"] == "D"
    assert any("concentre" in i for i in result["issues"])
    assert result["details"]["total_nodes"] == 1
    assert result["details"]["active_nodes"] == 1
    assert result["details"]["pillars_count"] == 1



# ── Taxonomie équilibrée (grade A) ────────────────────────────────────────────

def test_balanced_taxonomy_grade_a():
    """4 piliers équilibrés → aucun > 35% → score 100, grade A."""
    comps = [
        _node(1, "Cloud"),
        _node(2, "Data"),
        _node(3, "DevOps"),
        _node(4, "Front"),
        _node(10, "AWS", parent_id=1),
        _node(11, "GCP", parent_id=1),
        _node(20, "Spark", parent_id=2),
        _node(21, "BigQuery", parent_id=2),
        _node(30, "Kubernetes", parent_id=3),
        _node(31, "Terraform", parent_id=3),
        _node(40, "React", parent_id=4),
        _node(41, "Vue", parent_id=4),
    ]
    result = compute_taxonomy_quality(comps)
    assert result["grade"] == "A"
    assert result["score"] == 100
    assert result["issues"] == []
    assert result["details"]["pillars_count"] == 4


# ── Pilier concentré > 35% ────────────────────────────────────────────────────

def test_concentrated_pillar_penalty():
    """Un seul pilier avec 80% des nœuds actifs → pénalité, grade dégradé."""
    comps = [
        _node(1, "MegaPillar"),
        _node(2, "Small"),
        _node(10, "A", parent_id=1),
        _node(11, "B", parent_id=1),
        _node(12, "C", parent_id=1),
        _node(13, "D", parent_id=1),
        _node(14, "E", parent_id=1),
        _node(15, "F", parent_id=1),
        _node(16, "G", parent_id=1),
        # Small n'a qu'un seul enfant
        _node(20, "X", parent_id=2),
    ]
    # MegaPillar : 1 + 7 = 8 nœuds / 10 actifs = 80%
    result = compute_taxonomy_quality(comps)
    assert result["score"] < 100
    assert len(result["issues"]) >= 1
    assert any("concentre" in issue for issue in result["issues"])


def test_concentrated_pillar_grade_b():
    """Concentration modérée → pénalité faible → grade B."""
    comps = [
        _node(1, "Big"),
        _node(2, "Medium"),
        _node(3, "Small"),
    ]
    # Big seul = 1/3 = 33% < 35% → pas de pénalité mais petit score
    # Ici on crée une concentration de 40% exactement
    comps2 = [
        _node(1, "Big"),
        _node(2, "B"),
        _node(3, "C"),
        _node(4, "D"),
        _node(5, "E"),
        _node(10, "x1", parent_id=1),
        _node(11, "x2", parent_id=1),
        _node(12, "x3", parent_id=1),
    ]
    # Big : 1+3 = 4 / 8 = 50% → score = 100 - (50-35) = 85 → grade B
    result = compute_taxonomy_quality(comps2)
    assert result["score"] == 85
    assert result["grade"] == "B"


def test_concentrated_pillar_grade_c():
    """Concentration forte → score entre 50 et 69 → grade C."""
    comps = [_node(1, "Giant")]
    for i in range(2, 12):
        comps.append(_node(100 + i, f"child_{i}", parent_id=1))
    comps.append(_node(2, "Tiny"))
    # Giant : 1 + 10 = 11 / 12 = 91.7% → pénalité = 91-50 = 41 → score = 59 → grade C
    result = compute_taxonomy_quality(comps)
    assert result["grade"] == "C"
    assert 50 <= result["score"] <= 69


# ── Archives > 10% ────────────────────────────────────────────────────────────

def test_archive_ratio_penalty():
    """Archives > 10% → pénalité + issue."""
    # 4 actifs + 2 archives → 2/6 = 33% > 10%
    comps = [
        _node(1, "Cloud"),
        _node(2, "Data"),
        _node(10, "AWS", parent_id=1),
        _node(11, "GCP", parent_id=1),
        _archive_node(99),
        _node(100, "Old1", parent_id=99),
        _node(101, "Old2", parent_id=99),
    ]
    result = compute_taxonomy_quality(comps)
    assert result["score"] < 100
    assert any("Archives" in issue for issue in result["issues"])
    assert result["metrics"]["archives"]["pct"] < 100  # pénalisé


def test_archive_ratio_under_threshold_no_penalty():
    """Archives < 10% → pas de pénalité."""
    # 1 archive sur 20 total = 5% < 10%
    comps = [_node(i, f"comp_{i}") for i in range(1, 20)]
    comps.append(_archive_node(99))
    result = compute_taxonomy_quality(comps)
    # Seule une concentration possible, pas d'archive penalty
    assert not any("Archives" in issue for issue in result["issues"])


# ── Pénalités cumulées ────────────────────────────────────────────────────────

def test_combined_penalties_score_floor_zero():
    """Concentration > 35% + Archives > 10% → score peut descendre à 0 (plancher)."""
    comps = [
        _node(1, "Giant"),
        _archive_node(99),
    ]
    for i in range(10):
        comps.append(_node(100 + i, f"gc_{i}", parent_id=1))
    for i in range(5):
        comps.append(_node(200 + i, f"arc_{i}", parent_id=99))
    # Giant : 1+10=11 / 12 actifs = ~91% → pénalité massive
    # Archives : 1+5=6 / 17 total = ~35%
    result = compute_taxonomy_quality(comps)
    assert result["score"] >= 0  # plancher respecté
    assert len(result["issues"]) == 2


# ── Comptage récursif de sous-arbres ─────────────────────────────────────────

def test_recursive_subtree_counting():
    """count_subtree doit compter récursivement les nœuds enfants à tous les niveaux."""
    comps = [
        _node(1, "Root"),
        _node(2, "Level1", parent_id=1),
        _node(3, "Level2a", parent_id=2),
        _node(4, "Level2b", parent_id=2),
        _node(5, "Level3", parent_id=3),
    ]
    result = compute_taxonomy_quality(comps)
    assert result["details"]["total_nodes"] == 5
    # Root est le seul pilier → 5/5 = 100% → pénalité
    assert result["details"]["pillars_count"] == 1
    assert any("concentre" in issue for issue in result["issues"])


# ── Pilier archive exclu du calcul de concentration ──────────────────────────

def test_archive_pillar_excluded_from_concentration():
    """Le pilier archives ne compte pas dans la concentration des piliers actifs.

    Pour qu'il n'y ait pas de pénalité de concentration, il faut que chaque
    pilier actif représente < 35% des nœuds actifs, donc ≥ 3 piliers équilibrés.
    """
    comps = [
        _node(1, "Cloud"),
        _node(2, "Data"),
        _node(3, "DevOps"),
        _archive_node(99),
        _node(100, "old", parent_id=99),
        _node(10, "AWS", parent_id=1),
        _node(20, "Spark", parent_id=2),
        _node(30, "K8s", parent_id=3),
    ]
    result = compute_taxonomy_quality(comps)
    # 3 piliers actifs de 2 nœuds chacun = 33% < 35% → pas de pénalité concentration
    assert not any("concentre" in issue for issue in result["issues"])
    assert result["details"]["pillars_count"] == 3


# ── Retour complet de la structure ───────────────────────────────────────────

def test_return_structure_complete():
    """Vérifier que toutes les clés attendues sont présentes dans la réponse."""
    result = compute_taxonomy_quality([_node(1, "Root")])
    assert "score" in result
    assert "grade" in result
    assert "metrics" in result
    assert "balance" in result["metrics"]
    assert "archives" in result["metrics"]
    assert "issues" in result
    assert "details" in result
    assert "total_nodes" in result["details"]
    assert "active_nodes" in result["details"]
    assert "pillars_count" in result["details"]


# ── No archive node present ───────────────────────────────────────────────────

def test_no_archive_node_archive_count_zero():
    """Sans nœud 'Archives / Non classées', archive_count doit être 0."""
    comps = [
        _node(1, "Cloud"),
        _node(2, "Data"),
        _node(10, "AWS", parent_id=1),
    ]
    result = compute_taxonomy_quality(comps)
    # active_nodes == total_nodes
    assert result["details"]["active_nodes"] == result["details"]["total_nodes"]
    # Aucune issue d'archive
    assert not any("Archives" in i for i in result["issues"])
