from datetime import datetime

from database import Base
from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB


class CVProfile(Base):
    __tablename__ = "cv_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False)  # Refers to Users API physical ID
    source_url = Column(String, nullable=True)
    source_tag = Column(String, index=True, nullable=True)
    extracted_competencies = Column(JSONB, nullable=True)

    # New distilled representation attributes
    current_role = Column(String, nullable=True)
    years_of_experience = Column(Integer, nullable=True)
    summary = Column(Text, nullable=True)

    from sqlalchemy.dialects.postgresql import ARRAY
    competencies_keywords = Column(ARRAY(String), nullable=True)
    missions = Column(JSONB, nullable=True)
    educations = Column(JSONB, nullable=True)

    raw_content = Column(Text, nullable=False)
    # Using 3072 dimensions to match gemini-embedding-001 output topology natively
    semantic_embedding = Column(Vector(3072), nullable=True)
    # R1 — versionning du modèle d'embedding : invalide les recherches cross-modèle
    embedding_model = Column(String(100), nullable=True, index=True)
    extraction_reliability_score = Column(Integer, nullable=True)
    imported_by_id = Column(Integer, index=True, nullable=True)
    is_archived = Column(Boolean, default=False, nullable=False)
    # Erreurs fonctionnelles de post-traitement (assignation compétences, missions)
    # [] = pas d'erreur, ["Echec d'assignation de 'Angular'"] = compétence manquante
    # Critique : une compétence non assignée rend le consultant invisible à la recherche
    processing_errors = Column(JSONB, nullable=True, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class CVMissionEmbedding(Base):
    """R7 — Chunk-level embeddings pour le RAG multi-vecteur.

    Chaque CVProfile possède N lignes dans cette table :
    - 1 chunk de type 'profile_summary' (ROLE + SUMMARY + COMPETENCIES, sans missions)
    - N chunks de type 'mission' (1 par mission, toutes missions sans limite)

    Avantage vs le vecteur global cv_profiles.semantic_embedding :
    Un consultant Java/GCP aura des chunks mission spécifiques à chaque domaine,
    permettant une précision de matching bien supérieure sur les queries ciblées.
    """
    __tablename__ = "cv_mission_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    cv_profile_id = Column(Integer, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    # 0 = profile_summary, 1..N = index de la mission dans profile.missions[]
    mission_index = Column(Integer, nullable=False)
    # 'profile_summary' | 'mission'
    chunk_type = Column(String(50), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_embedding = Column(Vector(3072), nullable=True)
    embedding_model = Column(String(100), nullable=True, index=True)
    source_tag = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
