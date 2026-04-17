"""initial

Revision ID: 0001
Revises:
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "sites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sites_tenant_id", "sites", ["tenant_id"])

    op.create_table(
        "devices",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("vendor", sa.String(32), nullable=False),
        sa.Column("vendor_device_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "vendor", "vendor_device_id",
            name="uq_devices_tenant_vendor_vendor_device_id",
        ),
    )
    op.create_index("ix_devices_tenant_id", "devices", ["tenant_id"])
    op.create_index("ix_devices_site_id", "devices", ["site_id"])

    op.create_table(
        "events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("device_id", sa.String(36), sa.ForeignKey("devices.id"), nullable=True),
        sa.Column("vendor", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("vendor_event_id", sa.String(128), nullable=False),
        sa.Column("raw_payload", sa.JSON, nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "vendor", "vendor_event_id",
            name="uq_events_tenant_vendor_vendor_event_id",
        ),
    )
    op.create_index("ix_events_tenant_occurred_at", "events", ["tenant_id", "occurred_at"])
    op.create_index("ix_events_device_occurred_at", "events", ["device_id", "occurred_at"])
    op.create_index("ix_events_site_occurred_at", "events", ["site_id", "occurred_at"])


def downgrade():
    op.drop_table("events")
    op.drop_table("devices")
    op.drop_table("sites")
    op.drop_table("tenants")
