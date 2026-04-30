"""
scoring_utils.py — Fonctions pures de calcul pour le scoring de compétences.

Pas de dépendances réseau ni DB — testables unitairement.
Exporté depuis scoring_service.py (re-export compat).
"""
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config reprise depuis scoring_service ─────────────────────────────────────

GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
VERTEX_LOCATION: str = os.getenv("VERTEX_LOCATION", "europe-west1")
BATCH_GCS_BUCKET: str = os.getenv("BATCH_GCS_BUCKET", "")
CV_API_URL: str = os.getenv("CV_API_URL", "http://cv_api:8000")

# IMPORTANT : Vertex AI Batch n'accepte PAS les IDs preview.
# → Utiliser un ID stable via VERTEX_BATCH_MODEL.
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL")
VERTEX_BATCH_MODEL: str = os.getenv(
    "VERTEX_BATCH_MODEL",
    os.getenv("GEMINI_MODEL_STABLE")
)

# Concurrence de préchargement des missions (1 appel HTTP par user)
MISSIONS_FETCH_SEMAPHORE: int = int(os.getenv("SCORING_MISSIONS_FETCH_SEMAPHORE", "20"))
# Concurrence d'écriture DB en phase apply
SCORING_APPLY_SEMAPHORE: int = int(os.getenv("SCORING_APPLY_SEMAPHORE", "10"))

# ── Paramètres de pondération scoring v2 (dupliqués depuis router.py) ─────────
COMPETENCY_DECAY_LAMBDA: float = float(os.getenv("COMPETENCY_DECAY_LAMBDA", "0.1"))
MISSION_TYPE_BONUS: dict = {
    "audit": 0.5, "conseil": 0.5, "accompagnement": 0.3,
    "formation": 0.4, "expertise": 0.3, "build": 0.0,
}
MISSION_TYPE_LABELS: dict = {
    "audit": "Audit / Diagnostic (valeur ajoutée élevée)",
    "conseil": "Conseil / Advisory (valeur ajoutée élevée)",
    "accompagnement": "Accompagnement / Coaching (valeur ajoutée)",
    "formation": "Formation / Workshop (valeur ajoutée)",
    "expertise": "Expert / Architecte (valeur ajoutée)",
    "build": "Build / Développement (standard)",
}


# ── Utilitaires de pondération (copiés depuis router.py pour autonomie) ───────

def _compute_recency_weight(end_date_str: Optional[str]) -> float:
    """Decay exponentiel sur l'ancienneté de la mission."""
    if not end_date_str:
        return 1.0
    if str(end_date_str).lower() in ("present", "en cours", "current"):
        return 1.0
    try:
        year = int(str(end_date_str)[:4])
        current_year = datetime.now(timezone.utc).year
        age_years = max(0, current_year - year)
        return round(math.exp(-COMPETENCY_DECAY_LAMBDA * age_years), 2)
    except (ValueError, TypeError):
        return 1.0


def _parse_duration_months(duration_str: Optional[str]) -> Optional[int]:
    if not duration_str:
        return None
    m = re.search(r"(\d+)\s*mois", str(duration_str), re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s*an", str(duration_str), re.IGNORECASE)
    if m:
        return int(m.group(1)) * 12
    return None


def _duration_multiplier(months: Optional[int]) -> float:
    if not months:
        return 1.0
    if months >= 18:
        return 1.5
    if months >= 9:
        return 1.2
    if months >= 3:
        return 1.0
    return 0.5


def _get_mission_bonus(mission_type: Optional[str]) -> tuple[str, float]:
    key = (mission_type or "").lower().strip()
    bonus = MISSION_TYPE_BONUS.get(key, 0.0)
    label = MISSION_TYPE_LABELS.get(key, "Autre mission")
    return label, bonus


def _estimate_duration_from_dates(start: Optional[str], end: Optional[str]) -> Optional[str]:
    if not start or not end:
        return None
    try:
        sy = int(str(start)[:4])
        sm = int(str(start)[5:7]) if len(str(start)) >= 7 else 1
        if str(end).lower() in ("present", "en cours", "current"):
            from datetime import date as _date
            ey, em = _date.today().year, _date.today().month
        else:
            ey = int(str(end)[:4])
            em = int(str(end)[5:7]) if len(str(end)) >= 7 else 12
        months = max(1, (ey - sy) * 12 + (em - sm))
        return f"{months} mois"
    except (ValueError, TypeError):
        return None


def _format_mission_v2(m: dict) -> str:
    """Formate une mission avec méta-données de pondération explicites pour le LLM."""
    title = m.get("title", "Mission sans titre")
    company = m.get("company", "?")

    recency_weight = _compute_recency_weight(m.get("end_date"))
    end_date_label = m.get("end_date") or "date inconnue"
    if recency_weight >= 0.9:
        recency_label = f"récente (poids={recency_weight})"
    elif recency_weight >= 0.6:
        recency_label = f"semi-récente (poids={recency_weight})"
    else:
        recency_label = f"ancienne, valeur diminuée (poids={recency_weight})"

    raw_duration = m.get("duration") or _estimate_duration_from_dates(
        m.get("start_date"), m.get("end_date")
    )
    duration_months = _parse_duration_months(raw_duration)
    dur_mult = _duration_multiplier(duration_months)
    dur_label = (
        f"{duration_months} mois (multiplicateur={dur_mult})"
        if duration_months
        else f"durée non précisée (multiplicateur neutre={dur_mult})"
    )

    mtype_label, mtype_bonus = _get_mission_bonus(m.get("mission_type"))
    bonus_str = f"+{mtype_bonus} bonus" if mtype_bonus > 0 else "pas de bonus"

    parts = [
        f"▶ Mission [{recency_label} | {dur_label} | {mtype_label}, {bonus_str}]",
        f"  Titre : {title} chez {company}",
        f"  Période : {m.get('start_date', '?')} → {end_date_label}",
    ]
    if m.get("description"):
        parts.append(f"  Description : {str(m['description'])[:300]}")
    comps = m.get("competencies", [])
    if comps:
        parts.append(f"  Compétences utilisées : {', '.join(comps)}")
    return "\n".join(parts)


def _build_scoring_prompt(competency_name: str, missions: list) -> str:
    """Construit le prompt v2 identique à router._compute_ai_score."""
    if not missions:
        return ""

    comp_norm = competency_name.lower()
    relevant = [
        m for m in missions
        if any(
            comp_norm in c.lower() or c.lower() in comp_norm
            for c in m.get("competencies", [])
        )
    ]
    context_missions = relevant if relevant else missions[:5]
    context_label = "directement liées à cette compétence" if relevant else "générales du consultant"
    missions_text = "\n\n".join([_format_mission_v2(m) for m in context_missions])

    return (
        f"Tu es un évaluateur expert de consultants IT et tech (scoring v2 avec pondération)."
        f" Tu dois noter la maîtrise de la compétence '{competency_name}' "
        f"pour ce consultant, de 0.0 à 5.0 (par pas de 0.5).\n\n"
        f"=== RÈGLES DE PONDÉRATION OBLIGATOIRES ===\n"
        f"Tu DOIS appliquer ces poids dans ton évaluation :\n"
        f"1. RÉCENCE : chaque mission affiche un 'poids' entre 0.0 et 1.0.\n"
        f"   - poids proche de 1.0 = mission récente → compte PLEINEMENT\n"
        f"   - poids 0.2-0.4 = mission ancienne → compte mais de façon RÉDUITE\n"
        f"2. DURÉE : chaque mission affiche un 'multiplicateur' entre 0.5 et 1.5.\n"
        f"   - multiplicateur > 1.0 = mission longue → profondeur de maîtrise accrue\n"
        f"3. TYPE DE MISSION : audit/conseil/accompagnement/formation/expertise affichent\n"
        f"   un bonus (+0.3 à +0.5).\n\n"
        f"=== NIVEAUX DE RÉFÉRENCE ===\n"
        f"  - 0.0 : Aucune trace dans le CV\n"
        f"  - 1.0 : Notions de base, mentionné dans des missions anciennes ou courtes\n"
        f"  - 2.0 : Utilisation ponctuelle\n"
        f"  - 3.0 : Maîtrise confirmée, plusieurs missions avec bons poids\n"
        f"  - 4.0 : Expert, missions longues/récentes ou audit/conseil intense\n"
        f"  - 5.0 : Référence reconnue / Lead sur plusieurs missions à forte valeur ajoutée\n\n"
        f"=== MISSIONS {context_label.upper()} AVEC MÉTA-DONNÉES DE PONDÉRATION ===\n"
        f"{missions_text}\n\n"
        f"=== CONSIGNE ===\n"
        f"Réponds UNIQUEMENT en JSON valide avec exactement deux champs :\n"
        f"- score : float entre 0.0 et 5.0, arrondi au pas de 0.5\n"
        f"- justification : string factuelle de 50 à 250 caractères en français\n\n"
        f'Exemple : {{"score": 3.5, "justification": "2 missions récentes (poids>0.9) dont 1 audit."}}'
    )


# ── Phase 1 : Préchargement des missions ─────────────────────────────────────

def _build_jsonl_lines(
    user_comp_list: list[tuple[int, int, str]],  # (user_id, comp_id, comp_name)
    missions_map: dict[int, list],
) -> tuple[list[str], dict[str, tuple[int, int, str]], int]:
    """
    Construit les lignes JSONL Vertex AI Batch.
    Retourne (lignes_jsonl, index, nb_skipped_no_missions).

    index : clé = "score-{user_id}-{comp_id}" → (user_id, comp_id, comp_name)
    """
    lines: list[str] = []
    index: dict[str, tuple[int, int, str]] = {}
    skipped_no_mission = 0

    for user_id, comp_id, comp_name in user_comp_list:
        missions = missions_map.get(user_id, [])
        if not missions:
            skipped_no_mission += 1
            continue

        prompt = _build_scoring_prompt(comp_name, missions)
        if not prompt:
            skipped_no_mission += 1
            continue

        key = f"score-{user_id}-{comp_id}"
        lines.append(json.dumps({
            "id": key,
            "request": {
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1,
                    "responseMimeType": "application/json",
                },
            },
        }))
        index[key] = (user_id, comp_id, comp_name)

    return lines, index, skipped_no_mission


# ── Phase 3 : Apply des résultats GCS → DB ───────────────────────────────────

def _parse_scoring_results_gcs(
    blobs_jsonl: list[str],
    index: dict[str, tuple[int, int, str]],
) -> tuple[list[tuple[int, int, str, float, str]], dict[int, dict]]:
    """
    Parse les lignes JSONL de sortie Vertex AI Batch.
    Retourne une liste de (user_id, comp_id, comp_name, score, justification) 
    et un dict des usages tokens par user_id.
    """
    results: list[tuple[int, int, str, float, str]] = []
    user_usage: dict[int, dict] = {}
    for line in blobs_jsonl:
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            key = record.get("id") or record.get("key", "")
            if key not in index:
                continue
            user_id, comp_id, comp_name = index[key]
            candidates = record.get("response", {}).get("candidates", [])
            usage = record.get("response", {}).get("usageMetadata", {})
            
            inp = usage.get("promptTokenCount", 0)
            out = usage.get("candidatesTokenCount", 0)
            if user_id not in user_usage:
                user_usage[user_id] = {"prompt_token_count": 0, "candidates_token_count": 0}
            user_usage[user_id]["prompt_token_count"] += inp
            user_usage[user_id]["candidates_token_count"] += out
            
            if not candidates:
                continue
            raw = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
            if not raw.startswith("{"):
                m = re.search(r"\{.*\}", raw, re.DOTALL)
                raw = m.group(0) if m else raw
            data = json.loads(raw)
            score = max(0.0, min(5.0, float(data.get("score", 0.0))))
            score = round(score * 2) / 2  # arrondi au pas de 0.5
            justification = str(data.get("justification", ""))[:500]
            results.append((user_id, comp_id, comp_name, score, justification))
        except Exception as e:
            logger.warning(f"[scoring_service] parse ligne GCS: {e}")
    return results, user_usage


# ── Point d'entrée principal ──────────────────────────────────────────────────
