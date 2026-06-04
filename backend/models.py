"""
Telifisan — SQLAlchemy ORM Models
Core entities only: sources, streams, channels, validation, output, tasks.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, JSON, Enum, Index,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def new_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Enums ──────────────────────────────────────────────────────

class SourceType(str, PyEnum):
    M3U_URL = "M3U_URL"
    M3U_FILE = "M3U_FILE"
    XTREAM_CODES_API = "XTREAM_CODES_API"


class IngestStatus(str, PyEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class ValidationStatus(str, PyEnum):
    UNKNOWN = "UNKNOWN"
    ALIVE = "ALIVE"
    SOFT_DEAD = "SOFT_DEAD"
    HARD_DEAD = "HARD_DEAD"


class CheckerTool(str, PyEnum):
    FFPROBE = "FFPROBE"
    STREAMLINK = "STREAMLINK"
    HTTP_HEAD = "HTTP_HEAD"
    HLS_MANIFEST = "HLS_MANIFEST"


class OutputMode(str, PyEnum):
    DIRECT = "DIRECT"


class SortBy(str, PyEnum):
    NAME = "NAME"


class TaskStatus(str, PyEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


# ── Models ─────────────────────────────────────────────────────

class Source(Base):
    __tablename__ = "sources"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(255), nullable=False)
    type = Column(Enum(SourceType), nullable=False)
    url = Column(String(2048), nullable=True)
    file_path = Column(String(1024), nullable=True)
    auth_username = Column(String(255), nullable=True)
    auth_password = Column(String(512), nullable=True)
    auth_headers = Column(JSON, nullable=True)
    enabled = Column(Boolean, default=True)
    priority = Column(Integer, default=100)
    last_ingest = Column(DateTime, nullable=True)
    last_ingest_status = Column(Enum(IngestStatus), nullable=True)
    last_ingest_error = Column(Text, nullable=True)
    ingest_schedule = Column(String(100), nullable=True)
    stream_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at = Column(DateTime, nullable=True)

    streams = relationship("SourceStream", back_populates="source", lazy="dynamic")

    __table_args__ = (
        Index("ix_sources_enabled_priority", "enabled", "priority"),
    )


class SourceStream(Base):
    __tablename__ = "source_streams"

    id = Column(String(36), primary_key=True, default=new_uuid)
    source_id = Column(String(36), ForeignKey("sources.id"), nullable=False)
    canonical_channel_id = Column(String(36), ForeignKey("canonical_channels.id"), nullable=True)
    name = Column(String(500), nullable=False)
    url = Column(String(2048), nullable=False)
    group = Column(String(255), nullable=True)
    tvg_id = Column(String(255), nullable=True)
    tvg_name = Column(String(500), nullable=True)
    logo = Column(String(2048), nullable=True)
    duration = Column(Integer, nullable=True)
    extra_attributes = Column(JSON, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    source = relationship("Source", back_populates="streams")
    canonical_channel = relationship(
        "CanonicalChannel",
        back_populates="source_streams",
        foreign_keys=[canonical_channel_id],
    )
    validation_records = relationship("ValidationRecord", back_populates="source_stream", lazy="dynamic")

    __table_args__ = (
        Index("ix_ss_source_canonical", "source_id", "canonical_channel_id"),
        Index("ix_ss_source_deleted", "source_id", "deleted_at"),
        Index("ix_ss_canonical", "canonical_channel_id"),
    )


class CanonicalChannel(Base):
    __tablename__ = "canonical_channels"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(500), nullable=True)
    name_original = Column(String(500), nullable=True)
    group = Column(String(255), nullable=True)
    country = Column(String(2), nullable=True)
    language = Column(String(50), nullable=True)
    logo = Column(String(2048), nullable=True)
    tvg_id = Column(String(255), nullable=True)
    last_validation = Column(DateTime, nullable=True)
    validation_status = Column(Enum(ValidationStatus), default=ValidationStatus.UNKNOWN)
    uptime_percent = Column(Float, default=0.0)
    preferred_source_id = Column(String(36), ForeignKey("source_streams.id", use_alter=True), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    source_streams = relationship(
        "SourceStream",
        back_populates="canonical_channel",
        lazy="dynamic",
        foreign_keys="SourceStream.canonical_channel_id",
    )

    __table_args__ = (
        Index("ix_cc_status_group", "validation_status", "group"),
    )


class ValidationRecord(Base):
    __tablename__ = "validation_records"

    id = Column(String(36), primary_key=True, default=new_uuid)
    source_stream_id = Column(String(36), ForeignKey("source_streams.id"), nullable=False)
    checked_at = Column(DateTime, nullable=False)
    success = Column(Boolean, nullable=False)
    codec = Column(String(50), nullable=True)
    resolution = Column(String(20), nullable=True)
    bitrate = Column(Integer, nullable=True)
    audio_tracks = Column(Integer, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    error_message = Column(Text, nullable=True)
    checker_tool = Column(Enum(CheckerTool), nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    source_stream = relationship("SourceStream", back_populates="validation_records")

    __table_args__ = (
        Index("ix_vr_stream_checked", "source_stream_id", "checked_at"),
    )


class OutputProfile(Base):
    __tablename__ = "output_profiles"

    id = Column(String(36), primary_key=True, default=new_uuid)
    name = Column(String(255), nullable=False)
    enabled = Column(Boolean, default=True)
    mode = Column(Enum(OutputMode), nullable=False, default=OutputMode.DIRECT)
    included_sources = Column(JSON, nullable=True)
    include_dead_channels = Column(Boolean, default=False)
    min_uptime_percent = Column(Float, default=0.0)
    generate_schedule = Column(String(100), nullable=True)
    last_generated = Column(DateTime, nullable=True)
    channel_count = Column(Integer, default=0)
    m3u_url_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
    deleted_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_op_enabled", "enabled"),
    )


class TaskLog(Base):
    __tablename__ = "task_logs"

    id = Column(String(36), primary_key=True, default=new_uuid)
    task_name = Column(String(255), nullable=False)
    status = Column(Enum(TaskStatus), nullable=False, default=TaskStatus.PENDING)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    message = Column(String(2000), nullable=True)
    error_details = Column(Text, nullable=True)
    stats = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    __table_args__ = (
        Index("ix_tl_name_started", "task_name", "started_at"),
        Index("ix_tl_completed", "completed_at"),
    )


class SystemConfig(Base):
    __tablename__ = "system_config"

    key = Column(String(255), primary_key=True)
    value = Column(JSON, nullable=True)
