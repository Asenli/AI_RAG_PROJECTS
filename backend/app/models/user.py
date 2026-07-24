"""User role model for RBAC."""
from datetime import datetime
from sqlalchemy import Column, String, Boolean, TIMESTAMP, Integer, Identity
from app.models.base import Base


class UserRole(Base):
    __tablename__ = "user_roles"

    id = Column(Integer, Identity(), primary_key=True)
    user_id = Column(String(64), unique=True, nullable=False)
    role = Column(String(32), nullable=False)
    school_id = Column(String(64))
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
