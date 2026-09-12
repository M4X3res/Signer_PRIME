"""
app/models.py
SQLAlchemy ORM модели для лицензий и устройств.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase


class Base(DeclarativeBase):
    """Базовый класс для всех моделей."""
    pass


class License(Base):
    """Модель лицензии."""
    __tablename__ = "licenses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    license_key: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        index=True,
        nullable=False
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True
    )
    stripe_subscription_id: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        index=True
    )
    plan: Mapped[str] = mapped_column(
        String(16),
        nullable=False
    )  # monthly|quarterly|yearly
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="active"
    )  # active|past_due|canceled|expired
    current_period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )
    max_devices: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=2
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    devices: Mapped[list["Device"]] = relationship(
        back_populates="license",
        cascade="all, delete-orphan"
    )


class Device(Base):
    """Модель устройства."""
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4
    )
    license_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("licenses.id", ondelete="CASCADE"),
        nullable=False
    )
    fingerprint_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False
    )
    device_label: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True
    )
    first_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    license: Mapped["License"] = relationship(back_populates="devices")

    __table_args__ = (
        # Partial unique index будет создан в миграции Alembic через raw SQL
        Index("ix_devices_license_id", "license_id"),
    )
