import pytest
from pydantic import ValidationError
from src.cvs.schemas import (
    ExtractedCompetency,
    ExtractedMission,
    ExtractedProfile,
    CVImportRequest
)

def test_extracted_competency():
    # Valid
    comp = ExtractedCompetency(name="Python", parent="Backend")
    assert comp.name == "Python"
    assert comp.parent == "Backend"

    # Valid without parent
    comp = ExtractedCompetency(name="Python")
    assert comp.parent is None

    # Invalid missing name
    with pytest.raises(ValidationError):
        ExtractedCompetency()

def test_extracted_mission():
    # Valid minimum
    mission = ExtractedMission(title="Developer")
    assert mission.title == "Developer"
    assert mission.mission_type == "build"
    assert mission.competencies == []
    assert mission.is_sensitive is False

    # Valid full
    mission = ExtractedMission(
        title="Tech Lead",
        company="Zenika",
        description="Leaded a team",
        start_date="2020-01",
        end_date="present",
        duration="3 ans",
        mission_type="conseil",
        competencies=["Python", "GCP"],
        is_sensitive=True
    )
    assert mission.company == "Zenika"
    assert mission.mission_type == "conseil"

    # Invalid missing title
    with pytest.raises(ValidationError):
        ExtractedMission(company="Zenika")

def test_cv_import_request():
    req = CVImportRequest(url="http://test.com")
    assert req.url == "http://test.com"

    with pytest.raises(ValidationError):
        CVImportRequest()

def test_extracted_profile():
    prof = ExtractedProfile(
        is_cv=True,
        first_name="Jean",
        last_name="Dupont",
        competencies=[ExtractedCompetency(name="Python")],
        missions=[ExtractedMission(title="Dev")]
    )
    assert prof.is_cv is True
    assert prof.first_name == "Jean"
    assert len(prof.competencies) == 1
    assert len(prof.missions) == 1
    assert prof.educations == []

    # Invalid without competencies or missions or is_cv
    with pytest.raises(ValidationError):
        ExtractedProfile(first_name="Jean")
