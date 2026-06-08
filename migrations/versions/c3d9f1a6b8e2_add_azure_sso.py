"""add azure/entra OIDC SSO settings + user fields

Revision ID: c3d9f1a6b8e2
Revises: a1f7c4e9d2b3
Create Date: 2026-06-08 00:00:00.000000

Adds optional Microsoft Entra ID (Azure AD) OIDC SSO alongside local auth.

- settings.auth_method ('local' default, NOT NULL via server_default so the
  existing row backfills to local) + the azure_* App-Registration config columns
  (nullable; azure_client_secret is write-only in the UI and never serialized).
- users.auth_source ('local' default, NOT NULL via server_default) and
  users.azure_oid (nullable; the stable Entra object id, backfilled on first
  SSO login). The setup admin (id=1) stays 'local'.
- Widens users.first_name/last_name (->64) and email_address (->255) so
  JIT-provisioned Entra display names / UPN-style emails fit. MySQL-only raw
  ALTERs (guarded by dialect); SQLite has no VARCHAR length limit so existing
  data already fits and the smoke/isolated tests stay backend-agnostic.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d9f1a6b8e2'
down_revision = 'a1f7c4e9d2b3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('settings') as batch_op:
        batch_op.add_column(sa.Column('auth_method', sa.String(length=10), nullable=False, server_default='local'))
        batch_op.add_column(sa.Column('azure_tenant_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('azure_client_id', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('azure_client_secret', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('azure_redirect_uri', sa.String(length=512), nullable=True))
        batch_op.add_column(sa.Column('azure_allowed_groups', sa.String(length=1024), nullable=True))

    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('auth_source', sa.String(length=10), nullable=False, server_default='local'))
        batch_op.add_column(sa.Column('azure_oid', sa.String(length=64), nullable=True))

    # Widen the user text columns for JIT-provisioned Entra identities. MySQL only;
    # SQLite ignores VARCHAR length, so existing data already fits.
    if op.get_bind().dialect.name == 'mysql':
        op.execute("ALTER TABLE users MODIFY first_name VARCHAR(64) CHARACTER SET utf8mb4 NOT NULL")
        op.execute("ALTER TABLE users MODIFY last_name VARCHAR(64) CHARACTER SET utf8mb4 NOT NULL")
        op.execute("ALTER TABLE users MODIFY email_address VARCHAR(255) CHARACTER SET utf8mb4 NOT NULL")


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('azure_oid')
        batch_op.drop_column('auth_source')

    with op.batch_alter_table('settings') as batch_op:
        batch_op.drop_column('azure_allowed_groups')
        batch_op.drop_column('azure_redirect_uri')
        batch_op.drop_column('azure_client_secret')
        batch_op.drop_column('azure_client_id')
        batch_op.drop_column('azure_tenant_id')
        batch_op.drop_column('auth_method')
    # The users column widening is intentionally not reverted (narrowing could
    # truncate stored names/emails); the wider VARCHAR is a safe superset.
