from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Boolean
from database import Base
import enum
from datetime import datetime

class DriveSyncStatus(enum.Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"        # Publié dans Pub/Sub, en attente de traitement par cv_api
    PROCESSING = "PROCESSING"  # En traitement actif dans cv_api (reçu depuis Pub/Sub)
    IMPORTED_CV = "IMPORTED_CV"
    IGNORED_NOT_CV = "IGNORED_NOT_CV"
    ERROR = "ERROR"

class DriveFolder(Base):
    __tablename__ = "drive_folders"

    id = Column(Integer, primary_key=True, index=True)
    google_folder_id = Column(String, unique=True, index=True, nullable=False)
    tag = Column(String, nullable=False)
    folder_name = Column(String, nullable=True)  # Nom du dossier Drive (ex: "Marie Dupont")
    is_initial_sync_done = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class DriveSyncState(Base):
    __tablename__ = "drive_sync_state"

    google_file_id = Column(String, primary_key=True, index=True)
    folder_id = Column(Integer, ForeignKey("drive_folders.id"), nullable=True)  # Tag root
    file_name = Column(String, nullable=True)
    revision_id = Column(String, nullable=True)
    status = Column(Enum(DriveSyncStatus, native_enum=False), default=DriveSyncStatus.PENDING, index=True)
    user_id = Column(Integer, nullable=True)
    modified_time = Column(DateTime, nullable=True)
    last_processed_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Nom du dossier parent direct du fichier (nomenclature Zenika "Prénom Nom")
    parent_folder_name = Column(String, nullable=True)
    error_message = Column(String, nullable=True)

