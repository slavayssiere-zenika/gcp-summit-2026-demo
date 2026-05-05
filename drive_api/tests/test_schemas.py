import pytest
from pydantic import ValidationError
from datetime import datetime, timezone
from src.schemas import (
    FolderCreate,
    FolderUpdate,
    FolderStats,
    FolderResponse,
    StatusResponse,
    FileStateResponse,
    PaginatedFilesResponse,
    PaginatedFoldersResponse,
    FileUpdate,
    KPIMetric,
    IngestionStatsResponse,
    FolderKPIResponse,
    QualityGateBatchResponse
)
from src.models import DriveSyncStatus

def test_folder_create():
    f = FolderCreate(google_folder_id="123", tag="test")
    assert f.google_folder_id == "123"
    assert f.excluded_folders == []

    with pytest.raises(ValidationError):
        FolderCreate(google_folder_id="123")  # Missing tag

def test_folder_update():
    f = FolderUpdate(tag="new_tag")
    assert f.tag == "new_tag"
    assert f.excluded_folders is None

def test_folder_stats():
    s = FolderStats(total_files=10)
    assert s.total_files == 10
    assert s.pending == 0

def test_folder_response():
    f = FolderResponse(
        id=1,
        google_folder_id="123",
        tag="test",
        created_at=datetime.now(timezone.utc),
        stats=FolderStats()
    )
    assert f.id == 1
    assert f.stats.total_files == 0

def test_status_response():
    s = StatusResponse(total_files_scanned=10, pending=5, imported=2, ignored=3, errors=0, last_processed_time=None)
    assert s.total_files_scanned == 10
    assert s.queued == 0

def test_file_state_response():
    f = FileStateResponse(
        google_file_id="abc",
        file_name="CV.pdf",
        folder_id=1,
        status=DriveSyncStatus.IMPORTED_CV,
        revision_id="r1",
        modified_time=datetime.now(timezone.utc),
        parent_folder_name="folder",
        last_processed_at=None,
        imported_at=None,
        error_message=None,
        user_id=42,
        processing_duration_ms=100,
        file_type="google_doc"
    )
    assert f.google_file_id == "abc"
    assert f.status == DriveSyncStatus.IMPORTED_CV

def test_paginated_files_response():
    resp = PaginatedFilesResponse(files=[], total=0, skip=0, limit=10)
    assert resp.total == 0
    assert resp.limit == 10

def test_paginated_folders_response():
    resp = PaginatedFoldersResponse(items=[], total=0, skip=0, limit=10)
    assert resp.total == 0

def test_file_update():
    u = FileUpdate(status=DriveSyncStatus.ERROR, error_message="Crash")
    assert u.status == DriveSyncStatus.ERROR
    assert u.error_message == "Crash"

def test_kpi_metric():
    k = KPIMetric(value=95.5, ok=95, total=100, status="ok")
    assert k.value == 95.5

def test_ingestion_stats_response():
    s = IngestionStatsResponse(
        total_files=100, imported=90, errors=5, pending=5, queued=0, processing=0, ignored=0,
        metrics={"coverage": KPIMetric(value=90.0)},
        score=90.0, grade="A", computed_at=datetime.now(timezone.utc), issues=[], recommendation="All good"
    )
    assert s.total_files == 100
    assert s.grade == "A"

def test_folder_kpi_response():
    k = FolderKPIResponse(
        folder_id=1, folder_name="f", tag="t", total=10, imported=8, errors=1, pending=1,
        queued=0, processing=0, ignored=0, import_rate_pct=80.0, error_rate_pct=10.0,
        user_link_rate_pct=100.0, avg_processing_ms=150.0, last_import_at=None, status="ok"
    )
    assert k.total == 10

def test_quality_gate_batch_response():
    r = QualityGateBatchResponse(status="success", files_queued_for_retry=0, reason_breakdown={}, message="OK")
    assert r.status == "success"
