"""add event experience customization

Revision ID: 0005_event_experience
Revises: 0004_archive_jobs
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_event_experience"
down_revision = "0004_archive_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("events", sa.Column("welcome_message", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("thank_you_message", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("theme", sa.String(length=32), nullable=False, server_default="classic"))
    op.add_column("events", sa.Column("accent_color", sa.String(length=7), nullable=False, server_default="#7c5cff"))
    op.add_column("events", sa.Column("guest_gallery_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("events", "guest_gallery_enabled")
    op.drop_column("events", "accent_color")
    op.drop_column("events", "theme")
    op.drop_column("events", "thank_you_message")
    op.drop_column("events", "welcome_message")
