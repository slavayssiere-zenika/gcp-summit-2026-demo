from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class MissionCreateRequest(BaseModel):
    title: str
    description: str


class ExtractedCompetency(BaseModel):
    name: str


class TeamMember(BaseModel):
    user_id: int
    full_name: Optional[str] = None
    role: str  # "Directeur de Projet", "Tech Lead", "Consultant"
    justification: str
    estimated_days: int


class MissionAnalyzeResponse(BaseModel):
    id: int
    title: str
    description: str
    status: str
    extracted_competencies: List[str]
    prefiltered_candidates: Optional[list] = []
    proposed_team: List[TeamMember]
    fallback_full_scan: Optional[bool] = False


class MissionStatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = None


class StatusHistoryEntry(BaseModel):
    id: int
    mission_id: int
    old_status: Optional[str] = None
    new_status: str
    reason: Optional[str] = None
    changed_by: str
    changed_at: datetime


class TaskResponse(BaseModel):
    task_id: str
    status: str
