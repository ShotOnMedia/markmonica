"""add commercial package pricing

Revision ID: 0015_package_pricing
Revises: 0014_package_orders
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_package_pricing"
down_revision = "0014_package_orders"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("package_configs", sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("package_configs", sa.Column("currency", sa.String(length=3), nullable=False, server_default="ZAR"))
    op.add_column("package_orders", sa.Column("amount_cents", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("package_orders", sa.Column("currency", sa.String(length=3), nullable=False, server_default="ZAR"))


def downgrade():
    op.drop_column("package_orders", "currency")
    op.drop_column("package_orders", "amount_cents")
    op.drop_column("package_configs", "currency")
    op.drop_column("package_configs", "price_cents")
