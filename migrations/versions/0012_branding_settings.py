"""add platform branding settings

Revision ID: 0012_branding_settings
Revises: 0011_package_configs
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_branding_settings"
down_revision = "0011_package_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "branding_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("platform_name", sa.String(length=160), nullable=False, server_default="Memories' Events"),
        sa.Column("support_email", sa.String(length=320), nullable=True),
        sa.Column("footer_text", sa.String(length=320), nullable=True),
        sa.Column("primary_color", sa.String(length=7), nullable=False, server_default="#a47f76"),
        sa.Column("secondary_color", sa.String(length=7), nullable=False, server_default="#302b2a"),
        sa.Column("background_color", sa.String(length=7), nullable=False, server_default="#f7f4f2"),
        sa.Column("font_family", sa.String(length=64), nullable=False, server_default="inter"),
        sa.Column("logo_object_key", sa.String(length=1024), nullable=True),
        sa.Column("favicon_object_key", sa.String(length=1024), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("INSERT INTO branding_settings (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("branding_settings")
