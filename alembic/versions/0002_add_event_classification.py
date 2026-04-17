"""add event classification

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "events",
        sa.Column("classification", sa.String(32), nullable=True),
    )


def downgrade():
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_column("classification")
