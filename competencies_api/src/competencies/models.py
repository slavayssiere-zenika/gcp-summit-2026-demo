from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base

# Association table for Many-to-Many relationship between User and Competency
# Note: user_id is a logical reference to the users_api
user_competency = Table(
    "user_competency",
    Base.metadata,
    Column("user_id", Integer, primary_key=True, index=True),
    Column("competency_id", Integer, ForeignKey("competencies.id"), primary_key=True),
    Column("created_at", DateTime, default=datetime.utcnow)
)


class Competency(Base):
    __tablename__ = "competencies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False, index=True)
    description = Column(String, nullable=True)
    parent_id = Column(Integer, ForeignKey("competencies.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Hierarchical tree representation
    parent = relationship("Competency", remote_side=[id], back_populates="sub_competencies")
    sub_competencies = relationship(
        "Competency",
        back_populates="parent",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    # Note: We can't have a direct SQLAlchemy relationship to User 
    # because it's in a different service/Base. 
    # We will handle user lookups in the router.
