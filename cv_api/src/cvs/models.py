from sqlalchemy import Column, Integer, String, Text, DateTime
from pgvector.sqlalchemy import Vector
from datetime import datetime
from database import Base

from sqlalchemy.dialects.postgresql import JSONB

class CVProfile(Base):
    __tablename__ = "cv_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False) # Refers to Users API physical ID
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
    
    raw_content = Column(Text, nullable=False)
    # Using 3072 dimensions to match gemini-embedding-001 output topology natively
    semantic_embedding = Column(Vector(3072), nullable=True) 
    imported_by_id = Column(Integer, index=True, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
