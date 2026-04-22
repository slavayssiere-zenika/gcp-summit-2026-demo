from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table, Float, Text
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
    aliases = Column(String, nullable=True)
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
    evaluations = relationship("CompetencyEvaluation", back_populates="competency", cascade="all, delete-orphan")

    # Note: We can't have a direct SQLAlchemy relationship to User
    # because it's in a different service/Base.
    # We will handle user lookups in the router.


class CompetencyEvaluation(Base):
    """Evaluation d'une competence feuille pour un utilisateur.

    Stocke deux types de note independantes :
    - ai_score : calcule par Gemini depuis les missions reelles du CV (0.0-5.0)
    - user_score : auto-evaluation saisie par le consultant (0.0-5.0)
    """
    __tablename__ = "competency_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    competency_id = Column(Integer, ForeignKey("competencies.id"), nullable=False, index=True)

    # Scoring IA (calcule par Gemini depuis les missions)
    ai_score = Column(Float, nullable=True)
    ai_justification = Column(Text, nullable=True)
    ai_scored_at = Column(DateTime, nullable=True)

    # Auto-evaluation utilisateur
    user_score = Column(Float, nullable=True)
    user_comment = Column(String(500), nullable=True)
    user_scored_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    competency = relationship("Competency", back_populates="evaluations")


class CompetencySuggestion(Base):
    """Suggestion de compétence issue d'une analyse de mission ou CV.

    Ces suggestions sont créées automatiquement lorsque le LLM extrait une
    compétence absente de la taxonomie officielle. Un admin peut les valider
    (status='ACCEPTED' → crée la compétence) ou rejeter (status='REJECTED').
    """
    __tablename__ = "competency_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    source = Column(String(50), nullable=False)  # 'mission' | 'cv'
    context = Column(String(500), nullable=True)  # titre mission ou nom CV
    status = Column(String(20), nullable=False, default="PENDING_REVIEW", index=True)
    occurrence_count = Column(Integer, nullable=False, default=1)  # fréquence = signal marché
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
