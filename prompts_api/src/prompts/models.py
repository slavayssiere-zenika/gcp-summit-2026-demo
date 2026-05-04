from database import Base
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func


class Prompt(Base):
    __tablename__ = "prompts"

    key = Column(String, primary_key=True, index=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), default=func.now())
