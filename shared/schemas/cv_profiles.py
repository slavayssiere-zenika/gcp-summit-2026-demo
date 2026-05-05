"""Consumer DTO for CV profile resources (cv_api responses)."""
from typing import Optional

from pydantic import BaseModel

from shared.schemas.pagination import PaginationResponse


class CvProfileItem(BaseModel):
    """Minimal CV profile representation needed by consumers (search_service, etc.)."""

    id: int
    user_id: Optional[int] = None
    source_url: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


CvProfilesResponse = PaginationResponse[CvProfileItem]
