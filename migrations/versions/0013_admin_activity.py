"""add administrator activity audit log

Revision ID: 0013_admin_activity
Revises: 0012_branding_settings
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_admin_activity"
down_revision = "0012_branding_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_activity",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("admin_user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(length=120), nullable=False),
        sa.Column("target_type", sa.String(length=80), nullable=True),
        sa.Column("target_id", sa.String(length=160), nullable=True),
        sa.Column("target_label", sa.String(length=320), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admin_activity_admin_user_id", "admin_activity", ["admin_user_id"])
    op.create_index("ix_admin_activity_action", "admin_activity", ["action"])
    op.create_index("ix_admin_activity_created_at", "admin_activity", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_admin_activity_created_at", table_name="admin_activity")
    op.drop_index("ix_admin_activity_action", table_name="admin_activity")
    op.drop_index("ix_admin_activity_admin_user_id", table_name="admin_activity")
    op.drop_table("admin_activity")
