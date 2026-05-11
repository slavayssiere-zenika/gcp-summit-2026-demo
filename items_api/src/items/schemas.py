from datetime import datetime
from typing import Generic, List, Optional, TypeVar, Annotated

from pydantic import BaseModel, Field

T = TypeVar("T")

# Borne maximale pour les colonnes INT4 (PostgreSQL / SQLite)
_INT4_MAX = 2_147_483_647


class PaginationResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    skip: int
    limit: int


class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    allowed_category_ids: List[Annotated[int, Field(gt=0, le=_INT4_MAX)]] = []


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryResponse(CategoryBase):
    id: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ItemBase(BaseModel):
    name: str
    description: Optional[str] = None
    metadata_json: Optional[dict] = None


class ItemCreate(ItemBase):
    user_id: int = Field(gt=0, le=_INT4_MAX, description="ID de l'utilisateur propriétaire (INT4)")
    category_ids: List[Annotated[int, Field(gt=0, le=_INT4_MAX)]] = Field(
        min_length=1,
        description="IDs des catégories (INT4). Au moins une requise."
    )


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    metadata_json: Optional[dict] = None
    category_ids: Optional[List[Annotated[int, Field(gt=0, le=_INT4_MAX)]]] = None


class ItemResponse(ItemBase):
    id: int
    user_id: int
    created_at: datetime
    metadata_json: Optional[dict] = None
    user: Optional[UserInfo] = None
    categories: List[CategoryResponse] = []

    model_config = {"from_attributes": True}


class ItemStatsResponse(BaseModel):
    total: int
    by_user: dict[int, int]


class BulkItemCreate(BaseModel):
    items: List[ItemCreate]
