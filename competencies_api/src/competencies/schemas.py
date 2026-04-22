from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime


class CompetencyBase(BaseModel):
    name: str
    description: Optional[str] = None
    aliases: Optional[str] = None
    parent_id: Optional[int] = None


class CompetencyCreate(CompetencyBase):
    pass


class CompetencyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    aliases: Optional[str] = None
    parent_id: Optional[int] = None


class CompetencyResponse(CompetencyBase):
    id: int
    created_at: datetime
    sub_competencies: List['CompetencyResponse'] = []

    model_config = ConfigDict(from_attributes=True)


class UserCompetencyBase(BaseModel):
    user_id: int
    competency_id: int


class UserCompetencyResponse(UserCompetencyBase):
    created_at: datetime
    competency: CompetencyResponse


class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool


class PaginationResponse(BaseModel):
    items: List[CompetencyResponse]
    total: int
    skip: int
    limit: int

class TreeImportRequest(BaseModel):
    tree: Union[Dict[str, Any], List[Any]]

class StatsRequest(BaseModel):
    user_ids: Optional[List[int]] = None
    limit: int = 10
    sort_order: str = "desc" # "asc" or "desc"

class CompetencyCount(BaseModel):
    id: int
    name: str
    count: int

class CompetencyStatsResponse(BaseModel):
    items: List[CompetencyCount]


# ── Evaluation Schemas ────────────────────────────────────────────────────────

class CompetencyEvaluationResponse(BaseModel):
    """Réponse complète d'une évaluation : note IA + note utilisateur."""
    id: int
    user_id: int
    competency_id: int
    competency_name: str
    ai_score: Optional[float] = None
    ai_justification: Optional[str] = None
    ai_scored_at: Optional[datetime] = None
    user_score: Optional[float] = None
    user_comment: Optional[str] = None
    user_scored_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class UserScoreRequest(BaseModel):
    """Saisie manuelle de la note auto-évaluée par le consultant."""
    score: float = Field(..., ge=0.0, le=5.0, description="Note de 0 à 5 (multiples de 0.5 recommandés)")
    comment: Optional[str] = Field(None, max_length=500)


class AiScoreAllResponse(BaseModel):
    """Résultat du déclenchement du scoring IA batch."""
    user_id: int
    triggered: int
    message: str


# ── Analytics Schemas ─────────────────────────────────────────────────────────

class AgencyCompetencyItem(BaseModel):
    """Un (agence, compétence, count) dans la heatmap."""
    agency: str
    competency: str
    count: int
    avg_ai_score: Optional[float] = None


class AgencyCompetencyCoverage(BaseModel):
    """Réponse de /analytics/agency-coverage."""
    items: List[AgencyCompetencyItem]
    total_consultants: int
    total_agencies: int


class SkillGapItem(BaseModel):
    """Une compétence manquante dans le pool ciblé."""
    competency_id: int
    competency_name: str
    consultants_with_skill: int
    consultants_in_pool: int
    coverage_pct: float


class SkillGapResult(BaseModel):
    """Réponse de /analytics/skill-gaps."""
    gaps: List[SkillGapItem]
    pool_size: int


class SimilarConsultant(BaseModel):
    """Un consultant similaire avec son score de similarité Jaccard."""
    user_id: int
    common_competencies: int
    jaccard_score: float
    shared_competency_names: List[str]


class SimilarConsultantsResult(BaseModel):
    """Réponse de /analytics/similar-consultants/{user_id}."""
    reference_user_id: int
    reference_competency_count: int
    similar_consultants: List[SimilarConsultant]
