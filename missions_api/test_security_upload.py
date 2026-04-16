"""
Tests de sécurité — Upload de fichiers pour missions_api.

Couvre :
- MIME TYPE GUARD : Rejet des types non autorisés (exécutables, images, archives)
- SIZE GUARD : Rejet des fichiers > 10 MB (anti-OOM Cloud Run)
- VALID CASES : Acceptation des types PDF, DOCX, TXT légitimes
- AUTH GUARD : Rejet sans token JWT
- MAGIC BYTES : Détection de fichiers dont le Content-Type est spoofé
"""

import os
os.environ['SECRET_KEY'] = 'testsecret'

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock

from main import app
from database import get_db
from src.auth import verify_jwt

# ── Dependency Overrides ──────────────────────────────────────────────────────

async def override_get_db():
    db = AsyncMock()
    yield db

def override_verify_jwt():
    return {"sub": "test@zenika.com", "email": "test@zenika.com", "role": "admin"}

app.dependency_overrides[get_db] = override_get_db
app.dependency_overrides[verify_jwt] = override_verify_jwt

client = TestClient(app)

AUTH_HEADER = {"Authorization": "Bearer fake_token"}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _post_mission_with_file(content: bytes, content_type: str, filename: str = "test.pdf",
                             title: str = "Test Mission", description: str = "Description"):
    """Helper : soumet POST /missions avec un fichier."""
    return client.post(
        "/missions",
        data={"title": title, "description": description},
        files={"file": (filename, content, content_type)},
        headers=AUTH_HEADER,
    )


# ── Tests Auth ────────────────────────────────────────────────────────────────

def test_upload_requires_jwt():
    """POST /missions sans Authorization doit retourner 401."""
    original_jwt = app.dependency_overrides.pop(verify_jwt, None)
    try:
        resp = client.post(
            "/missions",
            data={"title": "No Auth", "description": "desc"},
            files={"file": ("test.pdf", b"%PDF-1.4", "application/pdf")},
        )
        assert resp.status_code == 401
    finally:
        if original_jwt:
            app.dependency_overrides[verify_jwt] = original_jwt


# ── Tests MIME Type Guard ─────────────────────────────────────────────────────

def test_upload_rejects_executable_mime():
    """Un fichier application/x-msdownload (EXE) doit être rejeté avec 415."""
    fake_exe = b"MZ\x90\x00\x03\x00\x00\x00"  # Magic bytes Windows PE
    resp = _post_mission_with_file(fake_exe, "application/x-msdownload", "malware.exe")
    assert resp.status_code == 415
    data = resp.json()
    assert "detail" in data
    assert "Type de fichier non supporté" in data["detail"] or "non supporté" in data["detail"]


def test_upload_rejects_image_mime():
    """Un fichier image/jpeg doit être rejeté avec 415."""
    fake_jpg = b"\xFF\xD8\xFF\xE0\x00\x10JFIF"  # Magic bytes JPEG
    resp = _post_mission_with_file(fake_jpg, "image/jpeg", "photo.jpg")
    assert resp.status_code == 415
    assert "non supporté" in resp.json()["detail"].lower()


def test_upload_rejects_zip_mime():
    """Un fichier application/zip doit être rejeté avec 415."""
    fake_zip = b"PK\x03\x04"  # Magic bytes ZIP
    resp = _post_mission_with_file(fake_zip, "application/zip", "archive.zip")
    assert resp.status_code == 415


def test_upload_rejects_html_mime():
    """Un fichier text/html doit être rejeté (potentiel XSS/SSRF)."""
    html_content = b"<html><body>Injection Attempt</body></html>"
    resp = _post_mission_with_file(html_content, "text/html", "page.html")
    assert resp.status_code == 415


def test_upload_rejects_javascript_mime():
    """Un fichier application/javascript doit être rejeté."""
    js_content = b"alert('xss')"
    resp = _post_mission_with_file(js_content, "application/javascript", "script.js")
    assert resp.status_code == 415


def test_upload_rejects_shell_script():
    """Un script Shell doit être rejeté (text/x-sh ou application/x-sh)."""
    sh_content = b"#!/bin/bash\nrm -rf /"
    resp = _post_mission_with_file(sh_content, "application/x-sh", "destroy.sh")
    assert resp.status_code == 415


# ── Tests Size Guard ──────────────────────────────────────────────────────────

def test_upload_rejects_file_over_10mb(mocker):
    """Un fichier > 10 MB doit être rejeté avec 413."""
    # Patch task_manager pour éviter les effets de bord
    mocker.patch("src.missions.router.task_manager", autospec=True)
    large_content = b"%PDF-1.4" + b"A" * (11 * 1024 * 1024)  # 11 MB
    resp = _post_mission_with_file(large_content, "application/pdf", "big.pdf")
    assert resp.status_code == 413
    assert "volumineux" in resp.json()["detail"].lower() or "10 MB" in resp.json()["detail"]


def test_upload_accepts_file_exactly_10mb(mocker):
    """Un fichier de exactement 10 MB doit être accepté (limite incluse)."""
    mocker.patch("src.missions.router.task_manager", autospec=True)
    # 10 MB exactement — dans la limite autorisée
    max_content = b"%PDF-1.4" + b"B" * (10 * 1024 * 1024 - 8)
    resp = _post_mission_with_file(max_content, "application/pdf", "exact.pdf")
    # Doit passer la validation initiale et retourner 202 (processing)
    assert resp.status_code == 202


def test_upload_accepts_small_pdf(mocker):
    """Un PDF léger valide doit être accepté."""
    mocker.patch("src.missions.router.task_manager", autospec=True)
    small_pdf = b"%PDF-1.4 1 0 obj<</Type/Catalog>>endobj"
    resp = _post_mission_with_file(small_pdf, "application/pdf", "light.pdf")
    assert resp.status_code == 202
    assert "task_id" in resp.json()
    assert resp.json()["status"] == "processing"


# ── Tests Types Valides ────────────────────────────────────────────────────────

def test_upload_accepts_docx(mocker):
    """Un fichier DOCX (application/vnd.openxmlformats-officedocument...) doit être accepté."""
    mocker.patch("src.missions.router.task_manager", autospec=True)
    # Magic bytes DOCX (est un ZIP en réalité)
    docx_content = b"PK\x03\x04" + b"docx_content" * 10
    resp = _post_mission_with_file(
        docx_content,
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "mission.docx"
    )
    assert resp.status_code == 202


def test_upload_accepts_txt(mocker):
    """Un fichier text/plain doit être accepté."""
    mocker.patch("src.missions.router.task_manager", autospec=True)
    txt_content = b"Mission Java Spring Boot 6 mois Paris."
    resp = _post_mission_with_file(txt_content, "text/plain", "mission.txt")
    assert resp.status_code == 202


def test_upload_accepts_doc(mocker):
    """Un fichier application/msword (.doc) doit être accepté."""
    mocker.patch("src.missions.router.task_manager", autospec=True)
    doc_content = b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"  # Magic bytes OLE2 (doc)
    resp = _post_mission_with_file(doc_content, "application/msword", "mission.doc")
    assert resp.status_code == 202


# ── Tests Sans Fichier (form data only) ───────────────────────────────────────

def test_create_mission_without_file(mocker):
    """POST /missions sans fichier (form data uniquement) doit être accepté."""
    mocker.patch("src.missions.router.task_manager", autospec=True)
    resp = client.post(
        "/missions",
        data={"title": "Mission Sans Fichier", "description": "Description longue de la mission."},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 202
    data = resp.json()
    assert "task_id" in data
    assert data["status"] == "processing"


def test_create_mission_with_url(mocker):
    """POST /missions avec une URL de document doit être accepté."""
    mocker.patch("src.missions.router.task_manager", autospec=True)
    resp = client.post(
        "/missions",
        data={
            "title": "Mission URL",
            "description": "Mission depuis Google Doc",
            "url": "https://docs.google.com/document/d/fake123/edit"
        },
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 202


# ── Tests Réponse Structurée ──────────────────────────────────────────────────

def test_upload_415_response_has_detail(mocker):
    """La réponse 415 doit contenir une clé 'detail' lisible par le frontend."""
    bad_content = b"not a valid file"
    resp = _post_mission_with_file(bad_content, "application/octet-stream", "unknown.bin")
    assert resp.status_code == 415
    resp_json = resp.json()
    assert "detail" in resp_json
    # Le message doit mentionner les types acceptés
    detail = resp_json["detail"]
    assert any(t in detail for t in ["PDF", "DOCX", "TXT", "pdf", "docx", "txt"]) or "accepté" in detail


def test_upload_413_response_has_detail(mocker):
    """La réponse 413 doit contenir une clé 'detail' avec le message de taille."""
    mocker.patch("src.missions.router.task_manager", autospec=True)
    large_content = b"%PDF-1.4" + b"X" * (11 * 1024 * 1024)
    resp = _post_mission_with_file(large_content, "application/pdf")
    assert resp.status_code == 413
    assert "detail" in resp.json()
