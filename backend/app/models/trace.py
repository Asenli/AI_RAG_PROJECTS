"""Trace log model for full-chain observability."""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, TIMESTAMP, BigInteger, Identity
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base


class TraceLog(Base):
    __tablename__ = "trace_log"

    id = Column(BigInteger, Identity(), primary_key=True)
    trace_id = Column(String(64), nullable=False, index=True)
    company_id = Column(String(64), default="1", nullable=False, index=True)
    session_id = Column(String(64))
    user_id = Column(String(64), index=True)
    user_role = Column(String(32))
    node_name = Column(String(64), nullable=False)
    node_order = Column(Integer, nullable=False, default=0)
    input_data = Column(JSONB)
    output_data = Column(JSONB)
    duration_ms = Column(Integer)
    status = Column(String(16), default="ok")
    error_message = Column(Text)
    trace_meta = Column("metadata", JSONB)
    created_at = Column(TIMESTAMP, default=datetime.utcnow, index=True)
