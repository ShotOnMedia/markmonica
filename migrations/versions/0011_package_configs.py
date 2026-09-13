"""add editable package configurations

Revision ID: 0011_package_configs
Revises: 0010_user_admin_role
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_package_configs"
down_revision = "0010_user_admin_role"
branch_labels = None
depends_on = None

GIB = 1024**3
MIB = 1024**2


def upgrade() -> None:
    table = op.create_table(
        "package_configs",
        sa.Column("code", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("max_media_per_event", sa.Integer(), nullable=True),
        sa.Column("max_storage_bytes_per_event", sa.BigInteger(), nullable=True),
        sa.Column("max_video_bytes", sa.BigInteger(), nullable=True),
        sa.Column("guest_gallery", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("archive_downloads", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("custom_event_design", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.bulk_insert(table, [
        {"code": "starter", "name": "Starter", "max_media_per_event": 100, "max_storage_bytes_per_event": 1 * GIB, "max_video_bytes": 500 * MIB, "guest_gallery": False, "archive_downloads": True, "custom_event_design": True, "is_active": True},
        {"code": "celebration", "name": "Celebration", "max_media_per_event": 500, "max_storage_bytes_per_event": 5 * GIB, "max_video_bytes": 500 * MIB, "guest_gallery": True, "archive_downloads": True, "custom_event_design": True, "is_active": True},
        {"code": "premium", "name": "Premium", "max_media_per_event": None, "max_storage_bytes_per_event": None, "max_video_bytes": 500 * MIB, "guest_gallery": True, "archive_downloads": True, "custom_event_design": True, "is_active": True},
    ])


def downgrade() -> None:
    op.drop_table("package_configs")
