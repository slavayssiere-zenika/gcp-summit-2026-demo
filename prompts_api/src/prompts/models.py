import logging
from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.sql import func
from database import Base

class Prompt(Base):
    __tablename__ = "prompts"

    key = Column(String, primary_key=True, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())
