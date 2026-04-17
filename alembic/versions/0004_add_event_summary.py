"""add event summary

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "events",
        sa.Column("summary", sa.String(512), nullable=True),
    )


def downgrade():
    with op.batch_alter_table("events") as batch_op:
        batch_op.drop_column("summary")
