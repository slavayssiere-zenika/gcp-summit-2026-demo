from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey
from pgvector.sqlalchemy import Vector
from datetime import datetime
from database import Base
from sqlalchemy.dialects.postgresql import JSONB, ARRAY
import enum


class MissionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ANALYSIS_IN_PROGRESS = "ANALYSIS_IN_PROGRESS"
    STAFFED = "STAFFED"
    NO_GO = "NO_GO"
    SUBMITTED_TO_CLIENT = "SUBMITTED_TO_CLIENT"
    WON = "WON"
    LOST = "LOST"
    CANCELLED = "CANCELLED"


# Transitions autorisées : (état courant) -> [états cibles possibles]
ALLOWED_TRANSITIONS: dict[str, list[str]] = {
    MissionStatus.DRAFT: [MissionStatus.ANALYSIS_IN_PROGRESS],
    MissionStatus.ANALYSIS_IN_PROGRESS: [MissionStatus.STAFFED, MissionStatus.DRAFT],
    MissionStatus.STAFFED: [MissionStatus.NO_GO, MissionStatus.SUBMITTED_TO_CLIENT, MissionStatus.CANCELLED],
    MissionStatus.SUBMITTED_TO_CLIENT: [MissionStatus.WON, MissionStatus.LOST, MissionStatus.CANCELLED],
    MissionStatus.NO_GO: [],
    MissionStatus.WON: [],
    MissionStatus.LOST: [],
    MissionStatus.CANCELLED: [],
}

# Rôles autorisés à modifier le statut manuellement
STATUS_UPDATE_ROLES = ["admin", "commercial"]


class Mission(Base):
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)

    # Mission lifecycle status
    status = Column(String(30), default=MissionStatus.DRAFT, nullable=False)

    # Needs extracted by LLM
    extracted_competencies = Column(JSONB, nullable=True)
    competencies_keywords = Column(ARRAY(String), nullable=True)

    # Team proposed
    prefiltered_candidates = Column(JSONB, nullable=True)
    proposed_team = Column(JSONB, nullable=True)
    fallback_full_scan = Column(Boolean, default=False)

    # Semantic Search
    semantic_embedding = Column(Vector(3072), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class MissionStatusHistory(Base):
    __tablename__ = "mission_status_history"

    id = Column(Integer, primary_key=True, index=True)
    mission_id = Column(Integer, ForeignKey("missions.id"), nullable=False)
    old_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=False)
    reason = Column(Text, nullable=True)
    changed_by = Column(String(255), nullable=False)
    changed_at = Column(DateTime, default=datetime.utcnow)
