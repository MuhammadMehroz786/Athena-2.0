from datetime import datetime, UTC
import uuid
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from athena.db.base import Base


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "vendor", "vendor_device_id", name="uq_devices_tenant_vendor_vendor_device_id"),
        Index("ix_devices_tenant_id", "tenant_id"),
        Index("ix_devices_site_id", "site_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id"), nullable=False)
    site_id: Mapped[str] = mapped_column(String(36), ForeignKey("sites.id"), nullable=False)
    vendor: Mapped[str] = mapped_column(String(32), nullable=False)
    vendor_device_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
