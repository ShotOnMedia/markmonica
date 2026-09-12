"""introduce named event packages

Revision ID: 0009_event_packages
Revises: 0008_event_guest_font
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_event_packages"
down_revision = "0008_event_guest_font"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing events were created before packages were customer-facing. Keep
    # them unrestricted by migrating the legacy `free` value to Premium.
    op.execute("UPDATE events SET package_code = 'premium' WHERE package_code = 'free'")
    op.alter_column(
        "events",
        "package_code",
        existing_type=sa.String(length=64),
        server_default="starter",
        existing_nullable=False,
    )


def downgrade() -> None:
    op.execute("UPDATE events SET package_code = 'free' WHERE package_code IN ('starter', 'celebration', 'premium')")
    op.alter_column(
        "events",
        "package_code",
        existing_type=sa.String(length=64),
        server_default="free",
        existing_nullable=False,
    )
