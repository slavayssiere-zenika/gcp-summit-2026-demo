from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="user", nullable=False)
    seniority = Column(String, nullable=True)  # "Junior", "Mid", "Senior" — éditable manuellement
    allowed_category_ids = Column(String, default="")  # Comma-separated IDs for simplicity
    created_at = Column(DateTime, default=datetime.utcnow)
    picture_url = Column(String, nullable=True)
    google_id = Column(String, nullable=True)
    merged_into_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_anonymous = Column(Boolean, default=False, nullable=False)

    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB
    unavailability_periods = Column(JSON().with_variant(JSONB, "postgresql"), default=list)


class UserAuditLog(Base):
    __tablename__ = "user_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    admin_username = Column(String, nullable=False)
    action = Column(String, nullable=False)
    field_changed = Column(String, nullable=True)
    old_value = Column(String, nullable=True)
    new_value = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
