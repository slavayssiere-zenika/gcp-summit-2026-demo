from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from src.models import DriveSyncStatus


class FolderCreate(BaseModel):
    google_folder_id: str
    tag: str
    folder_name: Optional[str] = None  # Peut être fourni manuellement, sinon récupéré via Drive API
    excluded_folders: Optional[List[str]] = []

class FolderUpdate(BaseModel):
    tag: Optional[str] = None
    excluded_folders: Optional[List[str]] = None


class FolderStats(BaseModel):
    total_files: int = 0
    pending: int = 0
    queued: int = 0
    processing: int = 0
    imported: int = 0
    ignored: int = 0
    errors: int = 0


class FolderResponse(FolderCreate):
    id: int
    folder_name: Optional[str] = None
    excluded_folders: Optional[List[str]] = []
    created_at: datetime
    stats: Optional[FolderStats] = None

    model_config = {"from_attributes": True}


class StatusResponse(BaseModel):
    total_files_scanned: int
    pending: int
    queued: int = 0
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
    revision_id: str
    modified_time: datetime
    parent_folder_name: Optional[str]
    last_processed_at: Optional[datetime]
    imported_at: Optional[datetime]
    error_message: Optional[str]
    user_id: Optional[int]
    processing_duration_ms: Optional[int]
    file_type: Optional[str] = "google_doc"

    model_config = {"from_attributes": True}



class PaginatedFilesResponse(BaseModel):
    files: List[FileStateResponse]
    total: int
    skip: int
    limit: int

class FileUpdate(BaseModel):
    user_id: Optional[int] = None
    status: Optional[DriveSyncStatus] = None
    error_message: Optional[str] = None
    processing_duration_ms: Optional[int] = None  # Renseigné par cv_api au callback IMPORTED_CV


# ── KPI Schemas — Ingestion Data Quality ──────────────────────────────────────

class KPIMetric(BaseModel):
    """Une métrique de data quality avec son statut visuel."""
    value: float            # Valeur brute (pourcentage 0-100 ou durée en secondes)
    pct: Optional[float] = None   # Pourcentage normalisé (0-100) pour affichage barre
    ok: int = 0             # Numérateur (nombre de fichiers OK)
    total: int = 0          # Dénominateur (nombre de fichiers éligibles)
    status: str = "ok"      # "ok" | "warning" | "critical"
    unit: str = "%"         # Unité d'affichage


class IngestionStatsResponse(BaseModel):
    """KPIs globaux de data quality pour le pipeline d'ingestion Drive → CV."""
    # Volume
    total_files: int
    imported: int
    errors: int
    pending: int
    queued: int
    processing: int
    ignored: int
    # Timing
    freshness_hours: Optional[float] = None   # Heures depuis la dernière ingestion réussie
    # KPIs de couverture (0-100)
    metrics: dict[str, KPIMetric]
    # Grade global A/B/C/D/F
    score: float
    grade: str
    computed_at: datetime
    issues: List[str]
    recommendation: str


class FolderKPIResponse(BaseModel):
    """KPIs d'ingestion pour un folder/agence spécifique."""
    folder_id: int
    folder_name: Optional[str]
    tag: str
    total: int
    imported: int
    errors: int
    pending: int
    queued: int
    processing: int
    ignored: int
    import_rate_pct: float       # imported / total * 100
    error_rate_pct: float        # errors / total * 100
    user_link_rate_pct: float    # user_id not null / imported * 100
    avg_processing_ms: Optional[float]    # Durée moyenne de traitement
    last_import_at: Optional[datetime]   # Dernière ingestion réussie
    status: str                  # "ok" | "warning" | "critical"


class QualityGateBatchResponse(BaseModel):
    """Résultat du déclenchement du Quality Gate Batch."""
    status: str
    files_queued_for_retry: int
    reason_breakdown: dict[str, int]   # {raison: nombre_de_fichiers}
    message: str
