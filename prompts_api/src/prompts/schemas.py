from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PromptBase(BaseModel):
    value: str

class PromptCreate(PromptBase):
    key: str

class PromptUpdate(PromptBase):
    pass

class Prompt(PromptBase):
    key: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class PaginatedPromptsResponse(BaseModel):
    prompts: List[Prompt]
    total: int
    skip: int
    limit: int

class AnalysisResponse(BaseModel):
    original_prompt: str
    improved_prompt: str
    promptfoo_report: dict

class ErrorReport(BaseModel):
    service_name: str
    error_message: str
    context: Optional[str] = None
