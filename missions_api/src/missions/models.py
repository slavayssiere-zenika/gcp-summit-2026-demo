from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from pgvector.sqlalchemy import Vector
from datetime import datetime
from database import Base
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

class Mission(Base):
    __tablename__ = "missions"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    
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
