from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional, Generic, TypeVar, List

T = TypeVar("T")


class PaginationResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    skip: int
    limit: int


class UserBase(BaseModel):
    username: str
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    role: str = "user"
    allowed_category_ids: List[int] = []
    picture_url: Optional[str] = None


class UserCreate(UserBase):
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class ServiceAccountLoginRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: str = "user"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    role: Optional[str] = None
    allowed_category_ids: Optional[List[int]] = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    by_username_prefix: dict[str, int]

class MergeRequest(BaseModel):
    source_id: int
    target_id: int

class DuplicateCandidate(BaseModel):
    users: List[UserResponse]
