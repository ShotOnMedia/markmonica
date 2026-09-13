"""add platform admin role

Revision ID: 0010_user_admin_role
Revises: 0009_event_packages
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_user_admin_role"
down_revision = "0009_event_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_users_is_admin", "users", ["is_admin"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_users_is_admin", table_name="users")
    op.drop_column("users", "is_admin")
