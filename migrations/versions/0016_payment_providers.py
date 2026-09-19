"""add payment provider settings

Revision ID: 0016_payment_providers
Revises: 0015_package_pricing
"""
from alembic import op
import sqlalchemy as sa
revision="0016_payment_providers";down_revision="0015_package_pricing";branch_labels=None;depends_on=None

def upgrade():
    op.create_table("payment_provider_configs",sa.Column("code",sa.String(64),primary_key=True),sa.Column("display_name",sa.String(120),nullable=False),sa.Column("is_enabled",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("is_sandbox",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("merchant_id",sa.String(255)),sa.Column("merchant_key",sa.String(255)),sa.Column("passphrase",sa.String(255)),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    op.execute("INSERT INTO payment_provider_configs (code,display_name,is_enabled,is_sandbox,updated_at) VALUES ('payfast','Payfast',false,true,NOW())")

def downgrade(): op.drop_table("payment_provider_configs")
