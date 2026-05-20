from typing import List, Optional, Generic, TypeVar

from pydantic import BaseModel, model_validator

T = TypeVar("T")


class PaginationResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    skip: int
    limit: int


class CVImportRequest(BaseModel):
    url: Optional[str] = None  # Google Docs export URL — optionnel si raw_text fourni
    google_access_token: Optional[str] = None
    source_tag: Optional[str] = None
    folder_name: Optional[str] = None
    # Champs perf-test : bypass Drive + identity resolution
    raw_text: Optional[str] = None      # Texte CV direct (bypasse le téléchargement Drive)
    direct_user_id: Optional[int] = None  # User_id existant (bypasse la résolution d'identité)

    @model_validator(mode='after')
    def check_url_or_raw_text(self):
        if not self.url and not self.raw_text:
            raise ValueError('url or raw_text must be provided')
        return self

# Output expected from LLM


class ExtractedCompetency(BaseModel):
    name: str  # The specific node (e.g. Python)
    parent: Optional[str] = None  # Its parent category (e.g. Langages Backend)


class ExtractedMission(BaseModel):
    title: str
    company: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None   # Format: "YYYY-MM" or "YYYY"
    end_date: Optional[str] = None     # Format: "YYYY-MM", "YYYY", or "present"
    duration: Optional[str] = None     # Explicit duration string from CV (e.g. "2 ans", "18 mois")
    mission_type: Optional[str] = "build"  # audit | conseil | accompagnement | formation | expertise | build
    competencies: List[str] = []
    is_sensitive: Optional[bool] = False


class ExtractedEducation(BaseModel):
    degree: Optional[str] = None
    school: Optional[str] = None


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
    educations: List[ExtractedEducation] = []


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
    structured_cv: Optional[dict] = None  # Données LLM brutes — utilisées par pubsub pour bg_process
    steps: List[CVImportStep] = []
    warnings: List[str] = []


class SearchCandidateRequest(BaseModel):
    query: str
    skip: int = 0
    limit: int = 5
    skills: Optional[List[str]] = None
    agency: Optional[str] = None


class SearchCandidateResponse(BaseModel):
    user_id: int
    similarity_score: float
    full_name: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    is_active: Optional[bool] = None
    source_url: Optional[str] = None       # R5 — URL Drive du CV source
    embedding_model: Optional[str] = None  # R1 — Modèle d'embedding utilisé


class CVProfileResponse(BaseModel):
    user_id: int
    source_url: Optional[str] = None
    source_tag: Optional[str] = None
    imported_by_id: Optional[int] = None
    is_anonymous: bool = False
    is_archived: bool = False
    full_name: Optional[str] = None
    email: Optional[str] = None
    username: Optional[str] = None
    processing_errors: List[str] = []


class CVFullProfileResponse(BaseModel):
    user_id: int
    summary: Optional[str] = None
    current_role: Optional[str] = None
    seniority: Optional[str] = None
    years_of_experience: Optional[int] = None
    competencies_keywords: List[str] = []
    missions: List[ExtractedMission] = []
    educations: List[ExtractedEducation] = []
    is_anonymous: bool = False
    is_archived: bool = False
    processing_errors: List[str] = []


class UserMergeRequest(BaseModel):
    source_id: int
    target_id: int


class RankedExperienceResponse(BaseModel):
    user_id: int
    years_of_experience: int
    full_name: Optional[str] = None
    email: Optional[str] = None
    current_role: Optional[str] = None
    agency: Optional[str] = None
    is_anonymous: bool = False
