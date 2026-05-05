"""Shared Pydantic schemas — consumer DTOs for inter-service API contracts."""
from shared.schemas.pagination import PaginationResponse
from shared.schemas.missions import MissionItem, MissionsResponse
from shared.schemas.users import UserItem, UsersResponse
from shared.schemas.cv_profiles import CvProfileItem, CvProfilesResponse
from shared.schemas.mcp import McpToolResult

__all__ = [
    "PaginationResponse",
    "MissionItem",
    "MissionsResponse",
    "UserItem",
    "UsersResponse",
    "CvProfileItem",
    "CvProfilesResponse",
    "McpToolResult",
]
