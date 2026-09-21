"""add package hierarchy and demo package

Revision ID: 0017_package_hierarchy_demo
Revises: 0016_payment_providers
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_package_hierarchy_demo"
down_revision = "0016_payment_providers"
branch_labels = None
depends_on = None

MIB = 1024 * 1024


def upgrade():
    op.add_column("package_configs", sa.Column("tier_rank", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("package_configs", sa.Column("payment_required", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_index("ix_package_configs_tier_rank", "package_configs", ["tier_rank"])
    op.execute("UPDATE package_configs SET tier_rank = 10 WHERE code = 'starter'")
    op.execute("UPDATE package_configs SET tier_rank = 20 WHERE code = 'celebration'")
    op.execute("UPDATE package_configs SET tier_rank = 30 WHERE code = 'premium'")
    op.execute(sa.text("""
        INSERT INTO package_configs
          (code, name, max_media_per_event, max_storage_bytes_per_event, max_video_bytes,
           guest_gallery, archive_downloads, custom_event_design, is_active,
           price_cents, currency, tier_rank, payment_required, updated_at)
        VALUES
          ('demo', 'Demo', 20, :storage, :video, false, false, false, true,
           0, 'ZAR', 0, false, NOW())
        ON CONFLICT (code) DO NOTHING
    """).bindparams(storage=250 * MIB, video=50 * MIB))


def downgrade():
    op.execute("UPDATE events SET package_code = 'starter' WHERE package_code = 'demo'")
    op.execute("DELETE FROM package_configs WHERE code = 'demo'")
    op.drop_index("ix_package_configs_tier_rank", table_name="package_configs")
    op.drop_column("package_configs", "payment_required")
    op.drop_column("package_configs", "tier_rank")
