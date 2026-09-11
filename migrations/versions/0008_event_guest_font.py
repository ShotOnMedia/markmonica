"""add guest display font

Revision ID: 0008_event_guest_font
Revises: 0007_product_foundations
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_event_guest_font"
down_revision = "0007_product_foundations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("guest_font", sa.String(length=64), nullable=False, server_default="default"))


def downgrade() -> None:
    op.drop_column("events", "guest_font")
