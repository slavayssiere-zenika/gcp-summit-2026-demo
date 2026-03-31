from pydantic import BaseModel, HttpUrl
from typing import List, Optional

class CVImportRequest(BaseModel):
    url: str # A Google Docs export URL or public CV link

# Output expected from LLM
class ExtractedCompetency(BaseModel):
    name: str # The specific node (e.g. Python)
    parent: Optional[str] = None # Its parent category (e.g. Langages Backend)

class ExtractedProfile(BaseModel):
    first_name: str
    last_name: str
    email: str
    competencies: List[ExtractedCompetency]

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
