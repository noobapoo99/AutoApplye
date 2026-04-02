from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from enum import Enum
import os
from typing import Any
from uuid import uuid4

from sqlalchemy import CheckConstraint
from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Float
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import Text
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class ApplicationStatus(str, Enum):
    discovered = "discovered"
    researching = "researching"
    resume_editing = "resume_editing"
    flagged_human = "flagged_human"
    applying = "applying"
    applied = "applied"
    email_received = "email_received"
    interview = "interview"
    rejected = "rejected"
    withdrawn = "withdrawn"


class Base(DeclarativeBase):
    pass


def _normalize_database_url(database_url: str) -> str:
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return database_url


def _get_database_url() -> str:
    try:
        from core.config import get_settings

        return get_settings().database_url
    except Exception:
        database_url = os.environ.get("DATABASE_URL")
        if database_url:
            return _normalize_database_url(database_url)
        raise


engine = create_async_engine(
    _get_database_url(),
    pool_pre_ping=True,
)
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    screenshot_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    external_apply_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
    )
    raw_payload: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.discovered,
        server_default=ApplicationStatus.discovered.value,
        nullable=False,
    )

    research: Mapped[CompanyResearch | None] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )
    application: Mapped[Application | None] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )


class CompanyResearch(Base):
    __tablename__ = "company_research"
    __table_args__ = (
        CheckConstraint(
            "hallucination_score >= 0 AND hallucination_score <= 6",
            name="ck_company_research_hallucination_score",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    reddit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    glassdoor_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    culture_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_skills_extended: Mapped[dict[str, Any] | list[Any] | None] = (
        mapped_column(JSON, nullable=True)
    )
    salary_range: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interview_process: Mapped[str | None] = mapped_column(Text, nullable=True)
    red_flags: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    hallucination_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    hallucination_breakdown: Mapped[dict[str, Any] | list[Any] | None] = (
        mapped_column(JSON, nullable=True)
    )
    enriched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    job: Mapped[Job] = relationship(back_populates="research")


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    edited_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    changes_made: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    match_score_before: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_score_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    applications: Mapped[list[Application]] = relationship(
        back_populates="resume_version",
    )


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "hallucination_score >= 0 AND hallucination_score <= 6",
            name="ck_applications_hallucination_score",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ApplicationStatus] = mapped_column(
        SAEnum(ApplicationStatus, name="application_status"),
        default=ApplicationStatus.discovered,
        server_default=ApplicationStatus.discovered.value,
        nullable=False,
    )
    resume_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("resume_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    form_fill_result: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    flagged_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    hallucination_score: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    job: Mapped[Job] = relationship(back_populates="application")
    resume_version: Mapped[ResumeVersion | None] = relationship(
        back_populates="applications",
    )
    email_threads: Mapped[list[EmailThread]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
    )


class EmailThread(Base):
    __tablename__ = "email_threads"
    __table_args__ = (
        CheckConstraint(
            "classification IN "
            "('interview_invite', 'rejection', 'assessment', "
            "'follow_up_needed', 'other')",
            name="ck_email_threads_classification",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid4()),
    )
    application_id: Mapped[str] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    gmail_thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(512), nullable=False)
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    classification: Mapped[str] = mapped_column(
        String(64),
        default="other",
        server_default="other",
        nullable=False,
    )
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    draft_followup: Mapped[str | None] = mapped_column(Text, nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    dlq_attempts: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )

    application: Mapped[Application] = relationship(back_populates="email_threads")


async def get_db() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


__all__ = [
    "Application",
    "ApplicationStatus",
    "AsyncSessionLocal",
    "Base",
    "CompanyResearch",
    "EmailThread",
    "Job",
    "ResumeVersion",
    "get_db",
    "init_db",
]
