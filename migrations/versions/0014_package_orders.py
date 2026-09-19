"""add package orders

Revision ID: 0014_package_orders
Revises: 0013_admin_activity
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_package_orders"
down_revision = "0013_admin_activity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "package_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("package_code", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="host"),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_package_orders_event_id", "package_orders", ["event_id"])
    op.create_index("ix_package_orders_user_id", "package_orders", ["user_id"])
    op.create_index("ix_package_orders_package_code", "package_orders", ["package_code"])
    op.create_index("ix_package_orders_status", "package_orders", ["status"])
    op.create_index("ix_package_orders_created_at", "package_orders", ["created_at"])


def downgrade():
    op.drop_table("package_orders")
