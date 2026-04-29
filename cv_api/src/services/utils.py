"""
utils.py — Helpers purs du pipeline cv_api (sans état, sans I/O).

Ce module contient les fonctions utilitaires partagées entre tous les services :
- build_taxonomy_context()  — formate l'arbre taxonomie pour le LLM
- _coerce_to_str()          — normalise les champs LLM vers str
- _build_distilled_content() — construit le texte sémantique pour l'embedding
- _clean_llm_json()         — nettoie la réponse LLM avant parsing JSON
- _CV_RESPONSE_SCHEMA       — schéma JSON Vertex AI partagé entre import ET batch

Ces fonctions sont PURES : pas d'appels réseau, pas d'accès BDD, pas d'état global.
Toute modification ici s'applique automatiquement aux deux pipelines (unitaire + batch).
"""

import json
import re
from typing import Optional


def build_taxonomy_context(items: list[dict]) -> tuple[str, int, int]:
    """Formate l'arbre de compétences en texte structuré pour le LLM.

    Retourne (texte_formaté, nb_piliers, nb_feuilles).
    Inclut les alias des compétences feuilles pour que le LLM reconnaisse
    les formes alternatives (ex: 'Kubernetes (aka: K8s, kube)').
    """
    parents = [item for item in items if not item.get("parent_id")]
    lines = []
    nb_leaves = 0
    for p in parents:
        lines.append(f"- {p['name']}")
        leaves = [item for item in items if item.get("parent_id") == p.get("id")]
        nb_leaves += len(leaves)
        if leaves:
            leaf_parts = []
            for leaf in leaves:
                entry = leaf["name"]
                # Inclure les alias pour que le LLM reconnaisse les formes alternatives
                # Ex: "Kubernetes (aka: K8s, kube)" → le LLM sait que K8s = Kubernetes
                if leaf.get("aliases"):
                    entry += f" (aka: {leaf['aliases']})"
                leaf_parts.append(entry)
            lines.append(f"  └─ {', '.join(leaf_parts)}")
    return "\n".join(lines), len(parents), nb_leaves


def _coerce_to_str(val) -> Optional[str]:
    """Normalise un champ attendu comme VARCHAR vers une str.

    Gemini retourne parfois summary comme dict ou list — cette fonction
    le convertit proprement pour éviter les erreurs asyncpg DataError.
    """
    if val is None:
        return None
    if isinstance(val, str):
        return val
    if isinstance(val, dict):
        # Extraire le premier champ textuel pertinent, sinon sérialiser
        for key in ("profile", "introduction", "quote", "title", "summary", "text"):
            if key in val and isinstance(val[key], str):
                return val[key]
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, list):
        return "\n".join(str(x) for x in val if x)
    return str(val)


def _build_distilled_content(structured_cv: dict) -> str:
    """Construit le texte sémantique distillé à vectoriser pour un profil CV.

    Remplace le raw_text[:6000] (bruit pour l'embedding) par une représentation
    structurée des missions récentes, compétences et formations.
    Utilisé à la fois par le pipeline d'import ET par le job de re-indexation.
    """
    comp_keywords = [
        c.get("name") for c in structured_cv.get("competencies", []) if c.get("name")
    ]
    educations_list = [
        f"{e.get('degree', '')} @ {e.get('school', '')}".strip(" @")
        for e in structured_cv.get("educations", [])
        if e.get("degree") or e.get("school")
    ]
    missions_chunks = [
        (
            f"Mission ({m.get('start_date', '?')}-{m.get('end_date', 'present')}): "
            f"{m.get('title', '')} @ {m.get('company', '')} | "
            f"{', '.join(m.get('skills', [])[:10])} | "
            f"{str(m.get('description', ''))[:300]}"
        )
        for m in structured_cv.get("missions", [])[:6]
    ]
    return (
        f"ROLE: {structured_cv.get('current_role', 'Unknown')}\n"
        f"EXPERIENCE: {structured_cv.get('years_of_experience', 0)} years\n"
        f"SUMMARY: {structured_cv.get('summary', '')}\n"
        f"COMPETENCIES: {', '.join(comp_keywords)}\n"
        f"EDUCATIONS: {', '.join(educations_list)}\n"
        f"RECENT_MISSIONS:\n" + "\n".join(missions_chunks)
    )


def _clean_llm_json(text: str) -> str:
    """Nettoie et répare une réponse LLM avant parsing JSON.

    Opérations appliquées dans l'ordre :
    1. Retire les balises markdown (```json ... ```).
    2. Retire les trailing commas avant ``}`` ou ``]``
       (erreur la plus fréquente : ``},`` ou ``"val",}`` produit par le LLM).

    Note : la suppression des commentaires ``// ...`` a été volontairement écartée car
    elle casse les URLs (``https://...``) présentes dans les valeurs JSON et supprime
    entièrement les réponses où le LLM n'exprime que du texte libre (pas de JSON).

    Retourne toujours une chaîne stripée prête pour ``json.loads``.
    """
    cleaned = text.strip()
    # 1. Balises markdown
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    # 2. Trailing commas
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    return cleaned.strip()


def _chunk_text(text: str, chunk_size: int = 150, overlap: int = 20) -> list[str]:
    """Découpe un texte en passages de `chunk_size` mots avec `overlap` mots de chevauchement.

    Utilisé par le endpoint /reindex pour segmenter le contenu distillé
    avant embedding et calcul de similarité sémantique.

    Args:
        text: Texte à segmenter.
        chunk_size: Nombre de mots par passage.
        overlap: Nombre de mots de chevauchement entre deux passages consécutifs.

    Returns:
        Liste de passages (str). Retourne [text] si le texte est plus court que chunk_size.
    """
    if not text or not text.strip():
        return []
    words = text.split()
    if len(words) <= chunk_size:
        return [text]
    step = max(1, chunk_size - overlap)
    chunks = []
    start = 0
    while start < len(words):
        chunk_words = words[start:start + chunk_size]
        chunks.append(" ".join(chunk_words))
        start += step
    return chunks



# ── Schéma JSON partagé entre route unitaire ET batch Vertex ──────────────────
# Toute modification ici s'applique automatiquement aux deux pipelines.
_CV_RESPONSE_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "is_cv": {"type": "boolean"},
        "first_name": {"type": "string"},
        "last_name": {"type": "string"},
        "email": {"type": "string"},
        "summary": {"type": "string"},
        "current_role": {"type": "string"},
        "years_of_experience": {"type": "integer"},
        "competencies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "parent": {"type": "string"},
                    "aliases": {"type": "array", "items": {"type": "string"}},
                    "practiced": {
                        "type": "boolean",
                        "description": (
                            "True if the consultant has actively used this skill "
                            "in at least one mission."
                        ),
                    },
                },
                "required": ["name", "practiced"],
            },
        },
        "missions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "company": {"type": "string"},
                    "description": {"type": "string"},
                    "start_date": {
                        "type": "string",
                        "description": "YYYY-MM or YYYY, null if unknown",
                    },
                    "end_date": {
                        "type": "string",
                        "description": "YYYY-MM, YYYY, 'present', or null",
                    },
                    "duration": {
                        "type": "string",
                        "description": "Explicit duration from CV text, null if not stated",
                    },
                    "mission_type": {
                        "type": "string",
                        "description": (
                            "One of: audit, conseil, accompagnement, formation, "
                            "expertise, build"
                        ),
                    },
                    "is_sensitive": {"type": "boolean"},
                    "competencies": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["title", "competencies", "is_sensitive", "mission_type"],
            },
        },
        "educations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "degree": {"type": "string"},
                    "school": {"type": "string"},
                },
            },
        },
        "is_anonymous": {"type": "boolean"},
        "trigram": {"type": "string"},
    },
    "required": [
        "is_cv", "first_name", "last_name", "email", "summary",
        "current_role", "years_of_experience", "competencies",
        "missions", "educations", "is_anonymous",
    ],
}
