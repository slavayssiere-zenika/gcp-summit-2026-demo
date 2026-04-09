from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class CVImportRequest(BaseModel):
    url: str # A Google Docs export URL or public CV link
    google_access_token: Optional[str] = None
    source_tag: Optional[str] = None

# Output expected from LLM
class ExtractedCompetency(BaseModel):
    name: str # The specific node (e.g. Python)
    parent: Optional[str] = None # Its parent category (e.g. Langages Backend)

class ExtractedMission(BaseModel):
    title: str
    company: Optional[str] = None
    description: Optional[str] = None
    competencies: List[str]

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

class CVResponse(BaseModel):
    message: str
    user_id: int
    competencies_assigned: int

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

class UserMergeRequest(BaseModel):
    source_id: int
    target_id: int
