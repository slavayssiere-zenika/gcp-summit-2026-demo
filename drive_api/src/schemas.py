from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from src.models import DriveSyncStatus

class FolderCreate(BaseModel):
    google_folder_id: str
    tag: str
    folder_name: Optional[str] = None  # Peut être fourni manuellement, sinon récupéré via Drive API

class FolderResponse(FolderCreate):
    id: int
    folder_name: Optional[str] = None
    created_at: datetime
    
    model_config = {"from_attributes": True}

class StatusResponse(BaseModel):
    total_files_scanned: int
    pending: int
    processing: int = 0
    imported: int
    ignored: int
    errors: int
    last_processed_time: Optional[datetime]

class FileStateResponse(BaseModel):
    google_file_id: str
    file_name: Optional[str]
    folder_id: Optional[int]
    status: DriveSyncStatus
    user_id: Optional[int] = None
    modified_time: Optional[datetime]
    last_processed_at: Optional[datetime]
    parent_folder_name: Optional[str] = None  # Nom Prénom Nom du dossier parent direct
    
    model_config = {"from_attributes": True}

class FileUpdate(BaseModel):
    user_id: Optional[int] = None
    status: Optional[DriveSyncStatus] = None
