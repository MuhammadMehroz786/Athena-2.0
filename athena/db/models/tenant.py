from datetime import datetime, UTC
import uuid
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from athena.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    # display name; intentionally non-unique — two clients can share a name (e.g., "Smith Residence"). id is the identifier.
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
