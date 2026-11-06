"""SQLAlchemy models for Agent Bazaar database.

These models define the schema used by Alembic for database migrations.
They mirror the existing SQLite tables used by the application.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class TrustState(Base):
    """Trust registry state for each provider."""
    __tablename__ = "trust_state"

    provider_id: str = Column(String, primary_key=True)
    successes: float = Column(Float, default=0.0, nullable=False)
    failures: float = Column(Float, default=0.0, nullable=False)
    probes: int = Column(Integer, default=0, nullable=False)
    calls: int = Column(Integer, default=0, nullable=False)
    schema_pass: int = Column(Integer, default=0, nullable=False)
    ratings_sum: float = Column(Float, default=0.0, nullable=False)
    ratings_count: int = Column(Integer, default=0, nullable=False)
    contradictions: int = Column(Integer, default=0, nullable=False)
    score: float = Column(Float, default=0.5, nullable=False)
    demoted: int = Column(Integer, default=0, nullable=False)
    updated_at: Optional[str] = Column(Text, nullable=True)


class TrustHistory(Base):
    """Trust history ledger for each provider."""
    __tablename__ = "trust_history"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    provider_id: str = Column(String, nullable=False)
    signal: str = Column(String, nullable=False)
    success: int = Column(Integer, nullable=False)
    weight: float = Column(Float, nullable=False)
    successes: float = Column(Float, nullable=False)
    failures: float = Column(Float, nullable=False)
    score: float = Column(Float, nullable=False)
    reason: Optional[str] = Column(Text, nullable=True)
    source: Optional[str] = Column(String, nullable=True)
    created_at: Optional[str] = Column(Text, nullable=True)


class TraceEvent(Base):
    """Trace events for task execution."""
    __tablename__ = "trace_events"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    task_id: str = Column(String, nullable=False)
    seq: int = Column(Integer, nullable=False)
    timestamp: str = Column(Text, nullable=False)
    event_type: str = Column(Text, nullable=False)
    actor: str = Column(Text, nullable=False)
    summary: str = Column(Text, nullable=False)
    data_json: str = Column(Text, nullable=False)


class TaskResult(Base):
    """Task results."""
    __tablename__ = "task_results"

    task_id: str = Column(String, primary_key=True)
    task: str = Column(Text, nullable=False)
    status: str = Column(Text, nullable=False)
    result_json: str = Column(Text, nullable=False)
    created_at: str = Column(Text, nullable=False)


class Message(Base):
    """Agent messages."""
    __tablename__ = "messages"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    task_id: Optional[str] = Column(String, nullable=True)
    kind: str = Column(Text, nullable=False)
    sender: str = Column(Text, nullable=False)
    recipient: Optional[str] = Column(String, nullable=True)
    timestamp: str = Column(Text, nullable=False)
    payload_json: str = Column(Text, nullable=False)


class Document(Base):
    """Document records."""
    __tablename__ = "documents"

    document_id: str = Column(String, primary_key=True)
    name: str = Column(Text, nullable=False)
    path: str = Column(Text, nullable=False)
    size_bytes: int = Column(Integer, nullable=False)
    text: str = Column(Text, nullable=False)
    created_at: str = Column(Text, nullable=False)


class WebhookSubscription(Base):
    """Webhook subscriptions."""
    __tablename__ = "webhook_subscriptions"

    id: str = Column(String, primary_key=True)
    url: str = Column(Text, nullable=False)
    events: str = Column(Text, nullable=False)  # JSON array
    secret: Optional[str] = Column(String, nullable=True)
    created_at: str = Column(Text, nullable=False)
    deliveries: int = Column(Integer, default=0, nullable=False)
    failures: int = Column(Integer, default=0, nullable=False)


class ScheduledJob(Base):
    """Scheduled jobs."""
    __tablename__ = "scheduled_jobs"

    id: str = Column(String, primary_key=True)
    task: str = Column(Text, nullable=False)
    interval_seconds: int = Column(Integer, nullable=False)
    enabled: int = Column(Integer, default=1, nullable=False)
    next_run: str = Column(Text, nullable=False)
    last_run: Optional[str] = Column(Text, nullable=True)
    last_status: Optional[str] = Column(String, nullable=True)
    created_at: str = Column(Text, nullable=False)


class ScheduledRunResult(Base):
    """Scheduled run results."""
    __tablename__ = "scheduled_run_results"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    job_id: str = Column(String, nullable=False)
    status: str = Column(Text, nullable=False)
    started_at: str = Column(Text, nullable=False)
    finished_at: Optional[str] = Column(Text, nullable=True)
    result_json: Optional[str] = Column(Text, nullable=True)
    error: Optional[str] = Column(Text, nullable=True)


class Notification(Base):
    """Notification records."""
    __tablename__ = "notifications"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: str = Column(String, nullable=False)
    title: str = Column(Text, nullable=False)
    body: str = Column(Text, nullable=False)
    read: int = Column(Integer, default=0, nullable=False)
    created_at: str = Column(Text, nullable=False)


class Tenant(Base):
    """Multi-tenant workspace."""
    __tablename__ = "tenants"

    id: str = Column(String, primary_key=True)
    name: str = Column(Text, nullable=False)
    plan: str = Column(String, default="free", nullable=False)
    created_at: str = Column(Text, nullable=False)
    settings_json: str = Column(Text, default="{}", nullable=False)