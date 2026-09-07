"""add event cover image

Revision ID: 0006_event_cover
Revises: 0005_event_experience
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_event_cover"
down_revision = "0005_event_experience"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("cover_object_key", sa.String(length=1024), nullable=True))
    op.add_column("events", sa.Column("cover_content_type", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("events", "cover_content_type")
    op.drop_column("events", "cover_object_key")
