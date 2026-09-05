"""Add media processing metadata.

Revision ID: 0003_media_processing
Revises: 0002_user_sessions
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_media_processing"
down_revision = "0002_user_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media", sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="pending"))
    op.add_column("media", sa.Column("preview_object_key", sa.String(length=1024), nullable=True))
    op.add_column("media", sa.Column("poster_object_key", sa.String(length=1024), nullable=True))
    op.add_column("media", sa.Column("processed_object_key", sa.String(length=1024), nullable=True))
    op.add_column("media", sa.Column("processed_content_type", sa.String(length=255), nullable=True))
    op.add_column("media", sa.Column("processing_error", sa.Text(), nullable=True))
    op.create_index("ix_media_processing_status", "media", ["processing_status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_media_processing_status", table_name="media")
    op.drop_column("media", "processing_error")
    op.drop_column("media", "processed_content_type")
    op.drop_column("media", "processed_object_key")
    op.drop_column("media", "poster_object_key")
    op.drop_column("media", "preview_object_key")
    op.drop_column("media", "processing_status")
