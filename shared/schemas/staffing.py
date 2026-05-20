"""
shared/schemas/staffing.py — Schémas Pydantic pour les réponses structurées des agents.

Ces schémas sont utilisés comme `output_schema` dans les LlmAgent ADK (v1.28+/v2),
garantissant des réponses typées et validées entre les agents.

Contrat d'interface :
  - ConsultantMatch : profil d'un candidat avec score de compatibilité
  - StaffingResponse : réponse complète de agent_hr_api (Task API)
  - MissionAnalysis  : réponse complète de agent_ops_api / agent_missions_api
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ConsultantMatch(BaseModel):
    """Profil d'un consultant recommandé pour une mission."""

    consultant_id: int = Field(description="ID AlloyDB du consultant.")
    full_name: str = Field(description="Nom complet du consultant.")
    confidence_score: float = Field(
        ge=0.0, le=1.0,
        description="Score de compatibilité entre 0.0 et 1.0.",
    )
    matching_skills: list[str] = Field(
        default_factory=list,
        description="Compétences du consultant alignées avec la mission.",
    )
    availability_conflicts: list[str] = Field(
        default_factory=list,
        description="Missions actuelles pouvant créer un conflit de disponibilité.",
    )
    reasoning: str = Field(
        default="",
        description="Explication synthétique du choix de ce consultant.",
    )


class StaffingResponse(BaseModel):
    """Réponse structurée de agent_hr_api — compatible output_schema LlmAgent ADK."""

    top_candidates: list[ConsultantMatch] = Field(
        default_factory=list,
        description="Liste des consultants recommandés, triés par score décroissant.",
    )
    query_summary: str = Field(
        default="",
        description="Résumé de la demande de staffing analysée.",
    )
    data_sources_used: list[str] = Field(
        default_factory=list,
        description="APIs interrogées pour produire la réponse (ex: competencies_api, cv_api).",
    )
    total_candidates_scanned: int = Field(
        default=0,
        description="Nombre total de consultants évalués avant filtrage.",
    )
    confidence_level: str = Field(
        default="medium",
        description="Niveau de confiance global : 'low' | 'medium' | 'high'.",
    )
    display_type: str = Field(
        default="consultants",
        description=(
            "Hint d'affichage frontend pour le composant Vue.js à rendre. "
            "Valeurs autorisées : 'consultants' (liste de cartes candidats), "
            "'candidates' (vue simplifiée), 'profile' (profil unique), "
            "'evaluations' (résultats d'évaluation), 'empty' (texte uniquement). "
            "Utilisé comme source de vérité quand ENABLE_OUTPUT_SCHEMA=true, "
            "en remplacement de render_ui_widgets."
        ),
    )


class MissionAnalysis(BaseModel):
    """Réponse structurée de agent_ops_api / agent_missions_api — compatible output_schema."""

    mission_id: Optional[int] = Field(
        default=None,
        description="ID AlloyDB de la mission si identifiée.",
    )
    mission_title: str = Field(
        default="",
        description="Titre ou description courte de la mission.",
    )
    required_skills: list[str] = Field(
        default_factory=list,
        description="Compétences requises pour la mission.",
    )
    urgency_level: str = Field(
        default="medium",
        description="Niveau d'urgence : 'low' | 'medium' | 'high' | 'critical'.",
    )
    recommended_consultants: list[ConsultantMatch] = Field(
        default_factory=list,
        description="Consultants recommandés pour cette mission.",
    )
    requires_human_approval: bool = Field(
        default=False,
        description=(
            "Si True, déclenche le flow Human-in-the-Loop (HITL) avant "
            "toute décision de staffing. Cas typiques : urgency='critical', "
            "mission_id non trouvé, ou score < 0.5 pour tous les candidats."
        ),
    )
    approval_reason: Optional[str] = Field(
        default=None,
        description="Explication du besoin de validation humaine si requires_human_approval=True.",
    )
    estimated_start_date: Optional[str] = Field(
        default=None,
        description="Date de début estimée au format ISO 8601.",
    )
    display_type: str = Field(
        default="missions",
        description=(
            "Hint d'affichage frontend pour le composant Vue.js à rendre. "
            "Valeurs autorisées : 'missions' (liste de missions), "
            "'candidates' (liste de candidats recommandés), "
            "'empty' (texte uniquement — pour FinOps, métriques, ou erreurs). "
            "Utilisé comme source de vérité quand ENABLE_OUTPUT_SCHEMA=true, "
            "en remplacement de render_ui_widgets."
        ),
    )
