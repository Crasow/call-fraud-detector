import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    prompt_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="custom")
    custom_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    expert: Mapped[str | None] = mapped_column(String(255), nullable=True)
    main_task: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields_for_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_words: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        onupdate=lambda: datetime.now(UTC).replace(tzinfo=None),
    )

    calls: Mapped[list["Call"]] = relationship(back_populates="profile")


class Call(Base):
    __tablename__ = "calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    audio_format: Mapped[str] = mapped_column(String(10), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None), index=True)

    analysis: Mapped["AnalysisResult | None"] = relationship(back_populates="call", uselist=False, cascade="all, delete-orphan")
    profile_result: Mapped["ProfileResult | None"] = relationship(back_populates="call", uselist=False, cascade="all, delete-orphan")
    profile: Mapped["Profile | None"] = relationship(back_populates="calls")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_fraud: Mapped[bool] = mapped_column(Boolean, nullable=False)
    fraud_score: Mapped[float] = mapped_column(Float, nullable=False)
    fraud_categories: Mapped[list] = mapped_column(JSONB, default=list)
    reasons: Mapped[list] = mapped_column(JSONB, default=list)
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))

    call: Mapped[Call] = relationship(back_populates="analysis")


class ProfileResult(Base):
    __tablename__ = "profile_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    call_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC).replace(tzinfo=None))

    call: Mapped[Call] = relationship(back_populates="profile_result")
