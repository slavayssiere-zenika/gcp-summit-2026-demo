from pydantic import BaseModel, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime


class CompetencyBase(BaseModel):
    name: str
    description: Optional[str] = None
    parent_id: Optional[int] = None


class CompetencyCreate(CompetencyBase):
    pass


class CompetencyUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


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
    tree: Dict[str, Any]
