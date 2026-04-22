"""
taxonomy_utils — Utilitaires partagés pour la manipulation de l'arbre de taxonomie
des compétences (competencies_api).

Ce module est conçu pour être importé par tout service qui interagit avec l'arbre
de compétences afin d'éviter la duplication de code et les dérives silencieuses.

Fonctions publiques :
  - extract_mid_parents  : nœuds intermédiaires (groupes de compétences)
  - extract_leaf_names   : noms des compétences feuilles
  - build_taxonomy_context : construit le bloc de contexte complet à injecter dans un prompt LLM
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "extract_mid_parents",
    "extract_leaf_names",
    "build_taxonomy_context",
    "find_domains_for_skills",
]

_MAX_LEAVES_DEFAULT = 300


def extract_mid_parents(nodes: list[dict[str, Any]]) -> list[str]:
    """Extrait les nœuds intermédiaires de l'arbre de taxonomie.

    Un nœud intermédiaire est :
    - porteur d'au moins un enfant feuille (nœud sans sous-compétences)
    - non-racine (parent_id non null)

    Utilisé pour guider le LLM sur le champ 'parent' des compétences extraites
    depuis un CV ou une description de mission.

    Args:
        nodes: Liste de nœuds tels que retournés par GET /competencies_api/?limit=...

    Returns:
        Liste ordonnée de noms de catégories intermédiaires (sans doublons d'ordre).
    """
    parents: list[str] = []
    for n in nodes:
        subs: list = n.get("sub_competencies") or []
        if subs:
            has_leaf_child = any(not s.get("sub_competencies") for s in subs)
            if has_leaf_child and n.get("parent_id") is not None and n.get("name"):
                parents.append(n["name"])
            parents.extend(extract_mid_parents(subs))
    return parents


def extract_leaf_names(
    nodes: list[dict[str, Any]],
    max_leaves: int = _MAX_LEAVES_DEFAULT,
) -> list[str]:
    """Extrait les noms des compétences feuilles (nœuds terminaux sans sous-compétences).

    Utilisé pour normaliser les compétences extraites par le LLM vers les noms
    canoniques existants dans la taxonomie (ex: 'K8s' → 'Kubernetes').

    Args:
        nodes: Liste de nœuds tels que retournés par GET /competencies_api/?limit=...
        max_leaves: Nombre maximum de feuilles à retourner (par défaut 300,
                    conservatif pour tenir dans la fenêtre de contexte LLM).

    Returns:
        Liste des noms de feuilles, plafonnée à max_leaves.
    """
    acc: list[str] = []
    _collect_leaves(nodes, acc)
    return acc[:max_leaves]


def _collect_leaves(nodes: list[dict[str, Any]], acc: list[str]) -> None:
    """Traversal récursif interne pour extract_leaf_names."""
    for n in nodes:
        subs: list = n.get("sub_competencies") or []
        if not subs:
            name: str | None = n.get("name")
            if name:
                acc.append(name)
        else:
            _collect_leaves(subs, acc)


def build_taxonomy_context(
    nodes: list[dict[str, Any]],
    max_leaves: int = _MAX_LEAVES_DEFAULT,
) -> tuple[str, int, int]:
    """Construit le bloc de contexte taxonomique complet à injecter dans un prompt LLM.

    Le contexte est structuré en deux sections :
    1. PARENT DOMAINS   — catégories intermédiaires pour le champ 'parent'
    2. EXISTING LEAVES  — noms canoniques des feuilles pour la normalisation

    Args:
        nodes: Nœuds de l'arbre de compétences.
        max_leaves: Plafond du nombre de feuilles injectées.

    Returns:
        Tuple (context_str, nb_parents, nb_leaves) où :
        - context_str est le bloc de texte à concaténer au prompt
        - nb_parents et nb_leaves sont les compteurs pour les logs
    """
    import json

    parent_categories = extract_mid_parents(nodes)
    leaf_names = extract_leaf_names(nodes, max_leaves=max_leaves)

    context = (
        "\n\nHere is the official taxonomy for this company's competencies."
        f"\n\n1. PARENT DOMAINS — use these as the 'parent' field for each extracted competency:\n{json.dumps(parent_categories)}"
        f"\n\n2. EXISTING LEAF COMPETENCIES — if a skill matches one of these exactly (or is an alias/abbreviation), "
        f"use this EXACT name instead of creating a variant "
        f"(e.g. map 'K8s' → 'Kubernetes', 'GCP' → 'Google Cloud Platform'):\n{json.dumps(leaf_names)}"
    )
    return context, len(parent_categories), len(leaf_names)


def find_domains_for_skills(skills: list[str], nodes: list[dict[str, Any]]) -> list[str]:
    """Retrouve les domaines parents pour un ensemble de noms de compétences.

    Un 'domaine' correspond au noeud racine supérieur ('Frontend', 'Cloud', etc.) 
    sous lequel se trouve la compétence feuille.

    Args:
        skills: Liste de noms de compétences (ex: ['React', 'Kubernetes']).
        nodes: Arbre complet de la taxonomie (GET /competencies_api/).

    Returns:
        Liste dédupliquée et triée des noms de domaines parents pour ces compétences.
    """
    if not skills or not nodes:
        return []

    domains = set()
    skills_lower = {s.lower() for s in skills}

    def _search(current_nodes: list[dict[str, Any]], current_domain: str | None = None) -> None:
        for node in current_nodes:
            # Si c'est un noeud top-level (au premier niveau typiquement, sans parent_id 
            # ou tout juste en dessous de la racine virtuelle), on le prend comme domaine courant
            node_name = node.get("name", "")
            node_domain = current_domain
            # Heuristique simple: un domaine est un noeud avec des enfants
            has_children = bool(node.get("sub_competencies"))
            if has_children and not current_domain:
                node_domain = node_name

            # Si le noeud courant correspond à un des skills
            if node_name.lower() in skills_lower:
                if node_domain:
                    domains.add(node_domain)
            
            # Match dans les alias ?
            aliases = node.get("aliases")
            if aliases:
                for alias in aliases.split(","):
                    if alias.strip().lower() in skills_lower:
                        if node_domain:
                            domains.add(node_domain)
                        break

            # On descend
            if has_children:
                _search(node.get("sub_competencies", []), node_domain)

    _search(nodes)
    return sorted(list(domains))

