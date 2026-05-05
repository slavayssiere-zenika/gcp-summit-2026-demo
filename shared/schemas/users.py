"""Consumer DTO for user resources (users_api responses)."""
from typing import Optional

from pydantic import BaseModel

from shared.schemas.pagination import PaginationResponse


class UserItem(BaseModel):
    """Minimal user representation needed by consumers (cv_import_service, etc.)."""

    id: int
    email: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    is_active: Optional[bool] = True
    role: Optional[str] = None
    is_anonymous: Optional[bool] = False
    agency_id: Optional[int] = None


UsersResponse = PaginationResponse[UserItem]
