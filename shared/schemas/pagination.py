"""Generic paginated response — mirrors the PaginationResponse envelope used by all APIs."""
from typing import Generic, List, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationResponse(BaseModel, Generic[T]):
    """Standard paginated response envelope.

    All list endpoints in the platform return this structure.
    Using model_validate() on raw API responses will raise ValidationError
    if the contract is broken (e.g. 'items' key renamed or missing).
    """

    items: List[T]
    total: int
    skip: int = 0
    limit: int = 50
