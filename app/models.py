import uuid
from datetime import date, datetime, timezone

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

def utcnow() -> datetime: return datetime.now(timezone.utc)

class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True, nullable=False)
    plan_code: Mapped[str] = mapped_column(String(64), default="free", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    events: Mapped[list["Event"]] = relationship(back_populates="owner", cascade="all, delete-orphan")
    sessions: Mapped[list["UserSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")

class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    user: Mapped[User] = relationship(back_populates="sessions")

class Event(Base):
    __tablename__ = "events"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True, nullable=False)
    package_code: Mapped[str] = mapped_column(String(64), default="starter", index=True, nullable=False)
    package_assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    gallery_visibility: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    welcome_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    thank_you_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    theme: Mapped[str] = mapped_column(String(32), default="classic", nullable=False)
    accent_color: Mapped[str] = mapped_column(String(7), default="#7c5cff", nullable=False)
    guest_font: Mapped[str] = mapped_column(String(64), default="default", nullable=False)
    guest_gallery_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    cover_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    cover_content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    owner: Mapped[User] = relationship(back_populates="events")
    media: Mapped[list["Media"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    archive_jobs: Mapped[list["ArchiveJob"]] = relationship(back_populates="event", cascade="all, delete-orphan")
    package_orders: Mapped[list["PackageOrder"]] = relationship(back_populates="event", cascade="all, delete-orphan")

class Media(Base):
    __tablename__ = "media"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploader_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    processing_status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    preview_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    poster_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    processed_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    processed_content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    event: Mapped[Event] = relationship(back_populates="media")

class ArchiveJob(Base):
    __tablename__ = "archive_jobs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    requested_media_ids: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True, nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event: Mapped[Event] = relationship(back_populates="archive_jobs")

class PackageConfig(Base):
    __tablename__ = "package_configs"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    max_media_per_event: Mapped[int | None] = mapped_column(nullable=True)
    max_storage_bytes_per_event: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_video_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    guest_gallery: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    archive_downloads: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    custom_event_design: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="ZAR", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class BrandingSettings(Base):
    __tablename__ = "branding_settings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    platform_name: Mapped[str] = mapped_column(String(160), default="Memories' Events", nullable=False)
    support_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    footer_text: Mapped[str | None] = mapped_column(String(320), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(7), default="#a47f76", nullable=False)
    secondary_color: Mapped[str] = mapped_column(String(7), default="#302b2a", nullable=False)
    background_color: Mapped[str] = mapped_column(String(7), default="#f7f4f2", nullable=False)
    font_family: Mapped[str] = mapped_column(String(64), default="inter", nullable=False)
    logo_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    favicon_object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class AdminActivity(Base):
    __tablename__ = "admin_activity"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    admin_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(320), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    admin_user: Mapped[User | None] = relationship()


class PackageOrder(Base):
    __tablename__ = "package_orders"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("events.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    package_code: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="host", nullable=False)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="ZAR", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
    event: Mapped[Event] = relationship(back_populates="package_orders")
    user: Mapped[User] = relationship()


class PaymentProviderConfig(Base):
    __tablename__ = "payment_provider_configs"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_sandbox: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    merchant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merchant_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    passphrase: Mapped[str | None] = mapped_column(String(255), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
