from datetime import datetime, UTC
import uuid
from sqlalchemy import DateTime, ForeignKey, JSON, String, UniqueConstraint, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from athena.db.base import Base


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "vendor", "vendor_event_id",
            name="uq_events_tenant_vendor_vendor_event_id",
        ),
        Index("ix_events_tenant_occurred_at", "tenant_id", "occurred_at"),
        Index("ix_events_device_occurred_at", "device_id", "occurred_at"),
        Index("ix_events_site_occurred_at", "site_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id"), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("devices.id"), nullable=True)
    vendor: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    vendor_event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    classification: Mapped[str | None] = mapped_column(String(32), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(512), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
    )
