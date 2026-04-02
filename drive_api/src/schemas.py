from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from src.models import DriveSyncStatus

class FolderCreate(BaseModel):
    google_folder_id: str
    tag: str

class FolderResponse(FolderCreate):
    id: int
    created_at: datetime
    
    model_config = {"from_attributes": True}

class StatusResponse(BaseModel):
    total_files_scanned: int
    pending: int
    imported: int
    ignored: int
    errors: int
    last_processed_time: Optional[datetime]
