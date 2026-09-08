"""add billing-neutral product metadata

Revision ID: 0007_product_foundations
Revises: 0006_event_cover
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_product_foundations"
down_revision = "0006_event_cover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("plan_code", sa.String(length=64), nullable=False, server_default="free"))
    op.create_index("ix_users_plan_code", "users", ["plan_code"], unique=False)
    op.add_column("events", sa.Column("package_code", sa.String(length=64), nullable=False, server_default="free"))
    op.add_column("events", sa.Column("package_assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")))
    op.create_index("ix_events_package_code", "events", ["package_code"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_events_package_code", table_name="events")
    op.drop_column("events", "package_assigned_at")
    op.drop_column("events", "package_code")
    op.drop_index("ix_users_plan_code", table_name="users")
    op.drop_column("users", "plan_code")
