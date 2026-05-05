"""Consumer DTO for authentication (users_api responses)."""
from pydantic import BaseModel


class TokenResponse(BaseModel):
    """Token representation needed by consumers to avoid silent JSON parsings."""

    access_token: str
    token_type: str = "bearer"
