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

class FileStateResponse(BaseModel):
    google_file_id: str
    file_name: Optional[str]
    folder_id: Optional[int]
    status: DriveSyncStatus
    modified_time: Optional[datetime]
    last_processed_at: Optional[datetime]
    
    model_config = {"from_attributes": True}
