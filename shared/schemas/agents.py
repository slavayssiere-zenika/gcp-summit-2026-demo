from typing import Any, Optional
from pydantic import BaseModel, Field

class OpsResponse(BaseModel):
    """Schéma de réponse structurée pour l'Agent Ops."""
    summary: str = Field(..., description="Résumé textuel de l'analyse Ops/FinOps.")
    data: dict[str, Any] = Field(default_factory=dict, description="Données brutes (métriques, coûts, status).")
    recommendations: list[str] = Field(default_factory=list, description="Liste de recommandations actionnables.")
    cost_estimate: Optional[float] = Field(None, description="Estimation du coût en USD si applicable.")

class AssistantResponse(BaseModel):
    """Schéma de réponse finale pour le Router (Assistant Global)."""
    answer: str = Field(..., description="Réponse synthétisée pour l'utilisateur (Markdown supporté).")
    domain: str = Field(..., description="Domaine d'expertise détecté (hr, ops, missions, mixed).")
    confidence: float = Field(..., description="Indice de confiance du routeur (0.0 à 1.0).")
    display_type: Optional[str] = Field(None, description="Slug UI pour l'affichage (ex: 'consultant_card').")
    data: Optional[dict[str, Any]] = Field(None, description="Données structurées pour le composant UI.")
    sources: list[dict[str, Any]] = Field(default_factory=list, description="Liste des agents sous-jacents consultés.")
