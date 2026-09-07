"""add archive jobs

Revision ID: 0004_archive_jobs
Revises: 0003_media_processing
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_archive_jobs"
down_revision = "0003_media_processing"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "archive_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("requested_media_ids", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=True),
        sa.Column("filename", sa.String(length=512), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_archive_jobs_event_id", "archive_jobs", ["event_id"])
    op.create_index("ix_archive_jobs_status", "archive_jobs", ["status"])

def downgrade():
    op.drop_index("ix_archive_jobs_status", table_name="archive_jobs")
    op.drop_index("ix_archive_jobs_event_id", table_name="archive_jobs")
    op.drop_table("archive_jobs")
