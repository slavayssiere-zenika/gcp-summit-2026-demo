from sqlalchemy import Column, Integer, String, Text, DateTime
from pgvector.sqlalchemy import Vector
from datetime import datetime
from database import Base

class CVProfile(Base):
    __tablename__ = "cv_profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True, nullable=False) # Refers to Users API physical ID
    source_url = Column(String, nullable=True)
    raw_content = Column(Text, nullable=False)
    # Using 3072 dimensions to match gemini-embedding-001 output topology natively
    semantic_embedding = Column(Vector(3072), nullable=True) 
    created_at = Column(DateTime, default=datetime.utcnow)
