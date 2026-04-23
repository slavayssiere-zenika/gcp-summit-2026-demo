from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class CVImportRequest(BaseModel):
    url: str  # A Google Docs export URL or public CV link
    google_access_token: Optional[str] = None
    source_tag: Optional[str] = None
    # Nomenclature Zenika : nom du dossier parent direct ("Prénom Nom"), transmis par drive_api
    folder_name: Optional[str] = None

# Output expected from LLM
class ExtractedCompetency(BaseModel):
    name: str # The specific node (e.g. Python)
    parent: Optional[str] = None # Its parent category (e.g. Langages Backend)

class ExtractedMission(BaseModel):
    title: str
    company: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None   # Format: "YYYY-MM" or "YYYY"
    end_date: Optional[str] = None     # Format: "YYYY-MM", "YYYY", or "present"
    duration: Optional[str] = None     # Explicit duration string from CV (e.g. "2 ans", "18 mois")
    mission_type: Optional[str] = "build"  # audit | conseil | accompagnement | formation | expertise | build
    competencies: List[str]
    is_sensitive: Optional[bool] = False

class ExtractedProfile(BaseModel):
    is_cv: bool
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    summary: Optional[str] = None
    current_role: Optional[str] = None
    years_of_experience: Optional[int] = None
    competencies: List[ExtractedCompetency]
    missions: List[ExtractedMission]

class CVImportStep(BaseModel):
    """Représente une étape du pipeline d'ingestion CV avec son statut et sa durée."""
    step: str           # Identifiant technique (ex: 'download', 'llm_parse')
    label: str          # Libellé lisible (ex: 'Téléchargement du document')
    status: str         # 'success' | 'warning' | 'error' | 'skipped'
    duration_ms: Optional[int] = None
    detail: Optional[str] = None  # Info complémentaire (nb items, taille, etc.)

class CVResponse(BaseModel):
    message: str
    user_id: int
    competencies_assigned: int
    extracted_info: Optional[dict] = None
    steps: List[CVImportStep] = []
    warnings: List[str] = []

class SearchCandidateRequest(BaseModel):
    query: str
    limit: int = 5
    skills: Optional[List[str]] = None

class SearchCandidateResponse(BaseModel):
    user_id: int
    similarity_score: float
    full_name: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    is_active: Optional[bool] = None

class CVProfileResponse(BaseModel):
    user_id: int
    source_url: str
    source_tag: Optional[str] = None
    imported_by_id: Optional[int] = None
    is_anonymous: bool = False

class CVFullProfileResponse(BaseModel):
    user_id: int
    summary: Optional[str] = None
    current_role: Optional[str] = None
    seniority: Optional[str] = None
    years_of_experience: Optional[int] = None
    competencies_keywords: List[str] = []
    missions: List[ExtractedMission] = []
    is_anonymous: bool = False

class UserMergeRequest(BaseModel):
    source_id: int
    target_id: int

class RankedExperienceResponse(BaseModel):
    user_id: int
    years_of_experience: int
    full_name: Optional[str] = None
    email: Optional[str] = None
    current_role: Optional[str] = None
    is_anonymous: bool = False
