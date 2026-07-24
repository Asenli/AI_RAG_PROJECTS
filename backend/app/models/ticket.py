"""Ticket draft model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Float, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from app.models.base import Base


class TicketDraft(Base):
    __tablename__ = "ticket_drafts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_id = Column(String(64), unique=True, nullable=False, index=True)
    status = Column(String(32), default="draft")  # draft | submitted | processing | resolved
    company_id = Column(String(64), default="1", nullable=False, index=True)
    original_question = Column(Text, nullable=False)
    rewritten_question = Column(Text)
    user_id = Column(String(64), nullable=False, index=True)
    user_role = Column(String(32))
    school_id = Column(String(64))
    trace_id = Column(String(64))
    retrieval_scores = Column(ARRAY(Float))
    top_docs_summary = Column(Text)
    llm_judgment = Column(JSONB)
    suggested_category = Column(String(64))
    category = Column(String(64))
    priority = Column(String(16), default="medium")  # low | medium | high | urgent
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
