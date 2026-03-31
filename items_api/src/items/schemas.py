from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Generic, TypeVar, List

T = TypeVar("T")


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
    allowed_category_ids: List[int] = []


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


class ItemCreate(ItemBase):
    user_id: int
    category_ids: List[int]


class ItemResponse(ItemBase):
    id: int
    user_id: int
    created_at: datetime
    user: Optional[UserInfo] = None
    categories: List[CategoryResponse] = []

    model_config = {"from_attributes": True}


class ItemStatsResponse(BaseModel):
    total: int
    by_user: dict[int, int]
