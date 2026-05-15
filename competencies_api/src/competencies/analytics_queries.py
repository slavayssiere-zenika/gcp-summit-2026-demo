"""
analytics_queries.py — Logique de calcul pure pour les analytics compétences.

Extrait de analytics_router.py (God module) — 2026-05-14.

Fonctions exportées :
  - compute_taxonomy_quality(all_comps) — Évalue la qualité de la taxonomie
"""

import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def compute_taxonomy_quality(all_comps: list) -> dict:
    """Évalue la qualité globale de la taxonomie (concentration, orphelines, archives).

    Calcule un score sur 100 en pénalisant :
    - La concentration excessive d'un pilier (> 35% des noeuds actifs)
    - Le ratio de compétences archivées (> 10% du total)

    Args:
        all_comps: Liste des objets Competency (avec id, name, parent_id).

    Returns:
        Dict avec score, grade (A-D), metrics, issues, details.
    """
    total_nodes = len(all_comps)
    if total_nodes == 0:
        return {
            "score": 0,
            "grade": "D",
            "metrics": {
                "balance": {"pct": 0, "ok": 0, "total": 0},
                "archives": {"pct": 0, "ok": 0, "total": 0},
            },
            "issues": ["Taxonomie vide."],
        }

    nodes_by_parent = defaultdict(list)
    roots = []
    archive_id = None

    for c in all_comps:
        if c.parent_id is None:
            roots.append(c)
            if c.name == "Compétences Archives / Non classées":
                archive_id = c.id
        else:
            nodes_by_parent[c.parent_id].append(c)

    def count_subtree(node_id):
        count = 1
        for child in nodes_by_parent[node_id]:
            count += count_subtree(child.id)
        return count

    pillar_counts = {}
    for r in roots:
        if archive_id and r.id == archive_id:
            continue
        pillar_counts[r.name] = count_subtree(r.id)

    max_pillar = {"name": "N/A", "pct": 0, "count": 0}
    archive_count = count_subtree(archive_id) if archive_id else 0
    active_nodes = total_nodes - archive_count

    if pillar_counts and active_nodes > 0:
        max_name, max_count = max(pillar_counts.items(), key=lambda x: x[1])
        max_pillar = {
            "name": max_name,
            "count": max_count,
            "pct": round((max_count / active_nodes) * 100, 1),
        }

    grade = "A"
    issues = []
    score = 100

    if max_pillar["pct"] > 35:
        issues.append(
            f"Le pilier '{max_pillar['name']}' concentre {max_pillar['pct']}% des compétences actives (> 35%)."
        )
        score -= int(max_pillar["pct"] - 35)

    archive_pct = 0
    if archive_count > 0:
        archive_pct = round((archive_count / max(total_nodes, 1)) * 100, 1)
        if archive_pct > 10:
            issues.append(
                f"{archive_pct}% des compétences sont dans les Archives (> 10%)."
            )
            score -= int(archive_pct)

    score = max(0, min(100, score))
    if score < 50:
        grade = "D"
    elif score < 70:
        grade = "C"
    elif score < 90:
        grade = "B"

    return {
        "score": score,
        "grade": grade,
        "metrics": {
            "balance": {
                "pct": max(0, 100 - int(max_pillar["pct"])),
                "ok": active_nodes - max_pillar["count"],
                "total": active_nodes,
            },
            "archives": {
                "pct": max(0, 100 - int(archive_pct)),
                "ok": total_nodes - archive_count,
                "total": total_nodes,
            },
        },
        "issues": issues,
        "details": {
            "total_nodes": total_nodes,
            "active_nodes": active_nodes,
            "pillars_count": len(pillar_counts),
        },
    }
