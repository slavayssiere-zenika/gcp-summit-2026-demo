from pydantic import BaseModel
from typing import List, Optional

class MissionCreateRequest(BaseModel):
    title: str
    description: str

class ExtractedCompetency(BaseModel):
    name: str

class TeamMember(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    role: str # "Directeur de Projet", "Tech Lead", "Consultant"
    justification: str
    estimated_days: int

class MissionAnalyzeResponse(BaseModel):
    id: int
    title: str
    description: str
    extracted_competencies: List[str]
    prefiltered_candidates: Optional[list] = []
    proposed_team: List[TeamMember]
    fallback_full_scan: Optional[bool] = False

class TaskResponse(BaseModel):
    task_id: str
    status: str
