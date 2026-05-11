from datetime import datetime
from typing import Generic, List, Literal, Optional, TypeVar, Annotated

from pydantic import BaseModel, EmailStr, Field

T = TypeVar("T")


class PaginationResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    skip: int
    limit: int


VALID_ROLES = Literal["user", "rh", "commercial", "admin", "service_account"]


class UserBase(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    role: VALID_ROLES = "user"
    seniority: Optional[str] = None  # "Junior", "Mid", "Senior"
    allowed_category_ids: List[Annotated[int, Field(gt=0, le=2_147_483_647)]] = []
    picture_url: Optional[str] = None
    is_anonymous: bool = False
    unavailability_periods: List[dict] = []


class UserCreate(UserBase):
    password: str = Field(min_length=8, pattern=r"^[^\x00]*$")


class LoginRequest(BaseModel):
    email: str
    password: str = Field(pattern=r"^[^\x00]*$")


class ServiceAccountLoginRequest(BaseModel):
    id_token: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    username: str
    role: VALID_ROLES = "user"


class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_anonymous: Optional[bool] = None
    role: Optional[VALID_ROLES] = None
    seniority: Optional[str] = None  # "Junior", "Mid", "Senior"
    allowed_category_ids: Optional[List[Annotated[int, Field(gt=0, le=2_147_483_647)]]] = None
    unavailability_periods: Optional[List[dict]] = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    is_anonymous: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserStatsResponse(BaseModel):
    total: int
    active: int
    inactive: int
    by_username_prefix: dict[str, int]


class MergeRequest(BaseModel):
    source_id: int = Field(gt=0, le=2_147_483_647, description="ID de l'utilisateur source (INT4)")
    target_id: int = Field(gt=0, le=2_147_483_647, description="ID de l'utilisateur cible (INT4)")


class DuplicateCandidate(BaseModel):
    users: List[UserResponse]
