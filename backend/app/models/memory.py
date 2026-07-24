"""Memory-related models: medium-term, user profile, facts, frequent questions."""
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, TIMESTAMP, BigInteger,
    Identity, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base


class SessionMediumMemory(Base):
    __tablename__ = "session_medium_memory"

    id = Column(BigInteger, Identity(), primary_key=True)
    company_id = Column(String(64), default="1", nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False)
    summary = Column(Text, nullable=False)
    key_entities = Column(JSONB)
    compressed_rounds = Column(Integer)
    unresolved_questions = Column(JSONB)
    version = Column(Integer, default=1)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint("company_id", "session_id", name="uq_chat_sessions_company_session"),
    )

    id = Column(BigInteger, Identity(), primary_key=True)
    company_id = Column(String(64), default="1", nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    user_role = Column(String(32), default="school")
    school_id = Column(String(64))
    title = Column(String(128), default="新会话")
    preview = Column(Text)
    message_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, index=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(BigInteger, Identity(), primary_key=True)
    company_id = Column(String(64), default="1", nullable=False, index=True)
    session_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    user_role = Column(String(32), default="school")
    role = Column(String(16), nullable=False)
    content = Column(Text, nullable=False)
    trace_id = Column(String(64), index=True)
    answer_id = Column(String(64), index=True)
    message_metadata = Column(JSONB)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, index=True)


class RoleModuleAccess(Base):
    __tablename__ = "role_module_access"
    __table_args__ = (
        UniqueConstraint("company_id", "role", name="uq_role_module_access_company_role"),
    )

    id = Column(BigInteger, Identity(), primary_key=True)
    company_id = Column(String(64), default="1", nullable=False, index=True)
    role = Column(String(32), nullable=False, index=True)
    modules = Column(JSONB, default=list, nullable=False)
    updated_by = Column(String(64), default="admin")
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id = Column(String(64), primary_key=True)
    company_id = Column(String(64), default="1", nullable=False, index=True)
    role = Column(String(32), nullable=False)
    school_id = Column(String(64))
    school_name = Column(String(128))
    preferred_categories = Column(JSONB)
    preferred_response_style = Column(String(32), default="normal")
    total_sessions = Column(Integer, default=0)
    total_questions = Column(Integer, default=0)
    avg_satisfaction = Column(Float)
    ticket_creation_rate = Column(Float)
    memory_embedding_id = Column(String(64))
    needs_human_priority = Column(Boolean, default=False)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserFact(Base):
    __tablename__ = "user_facts"

    id = Column(BigInteger, Identity(), primary_key=True)
    company_id = Column(String(64), default="1", nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    fact_type = Column(String(32), nullable=False)
    fact_content = Column(Text, nullable=False)
    source_session_id = Column(String(64))
    confidence = Column(Float, default=0.5)
    occurrence_count = Column(Integer, default=1)
    last_mentioned_at = Column(TIMESTAMP)
    is_active = Column(Boolean, default=True)
    created_at = Column(TIMESTAMP, default=datetime.utcnow)


class UserFrequentQuestion(Base):
    __tablename__ = "user_frequent_questions"

    id = Column(BigInteger, Identity(), primary_key=True)
    company_id = Column(String(64), default="1", nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    question_hash = Column(String(64), nullable=False)
    question_text = Column(Text, nullable=False)
    answer_text = Column(Text)
    frequency = Column(Integer, default=1)
    last_asked_at = Column(TIMESTAMP)
