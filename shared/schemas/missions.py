"""Consumer DTO for mission resources (cv_api / missions_api responses)."""
from typing import List, Optional

from pydantic import BaseModel

from shared.schemas.pagination import PaginationResponse


class MissionItem(BaseModel):
    """Minimal mission representation needed by consumers.

    Only contains the fields actually used by competencies_api and missions_api.
    Producer-side fields (embeddings, raw_text, etc.) are intentionally omitted.

    Note: id is Optional because cv_api/get_user_missions returns LLM-extracted
    missions (ExtractedMission) which have no DB id — only title, company, etc.
    """

    id: Optional[int] = None
    title: str
    description: Optional[str] = None
    company: Optional[str] = None
    user_id: Optional[int] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration: Optional[str] = None
    competencies: List[str] = []
    is_sensitive: Optional[bool] = False
    mission_type: Optional[str] = None


MissionsResponse = PaginationResponse[MissionItem]
