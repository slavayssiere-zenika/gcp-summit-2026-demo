from typing import Generic, List, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginationResponse(BaseModel, Generic[T]):
    """Standard paginated response envelope.

    All list endpoints in the platform return this structure.
    Using model_validate() on raw API responses will raise ValidationError
    if the contract is broken (e.g. 'items' key renamed or missing).
    """

    items: List[T]
    total: int = Field(..., ge=0)
    skip: int = Field(0, ge=0)
    limit: int = Field(50, ge=1, le=500)
