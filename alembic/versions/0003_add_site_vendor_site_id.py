"""add site vendor_site_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("sites") as batch_op:
        batch_op.add_column(sa.Column("vendor_site_id", sa.String(128), nullable=True))
        batch_op.create_index(
            "ix_sites_tenant_vendor_site_id",
            ["tenant_id", "vendor_site_id"],
        )
        batch_op.create_unique_constraint(
            "uq_sites_tenant_vendor_site_id",
            ["tenant_id", "vendor_site_id"],
        )


def downgrade():
    with op.batch_alter_table("sites") as batch_op:
        batch_op.drop_constraint("uq_sites_tenant_vendor_site_id", type_="unique")
        batch_op.drop_index("ix_sites_tenant_vendor_site_id")
        batch_op.drop_column("vendor_site_id")
