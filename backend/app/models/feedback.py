"""User feedback model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, Boolean, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.models.base import Base


class AnswerFeedback(Base):
    __tablename__ = "answer_feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answer_id = Column(String(64), nullable=False, index=True)
    company_id = Column(String(64), default="1", nullable=False, index=True)
    trace_id = Column(String(64), nullable=False)
    session_id = Column(String(64))
    user_id = Column(String(64), nullable=False, index=True)
    user_role = Column(String(32))
    feedback = Column(String(16), nullable=False)  # like | dislike
    reason = Column(Text)
    reason_category = Column(String(32))
    question = Column(Text, nullable=False)
    llm_answer = Column(Text, nullable=False)
    retrieved_sources = Column(JSONB)
    review_status = Column(String(32), default="pending_review")
    reviewed_by = Column(String(64))
    reviewed_at = Column(TIMESTAMP)
    review_comment = Column(Text)
    is_badcase_candidate = Column(Boolean, default=False)
    badcase_id = Column(String(64))
    created_at = Column(TIMESTAMP, default=datetime.utcnow)
