"""add email/pushover notification enable flags

Revision ID: 9c5e3a07b218
Revises: 8b4d2f1c9a06
Create Date: 2026-06-04 00:00:00.000000

Adds the per-channel master switches for the Settings -> Notifications tab:
``settings.email_enabled`` and ``settings.pushover_enabled`` (``slack_enabled``
already exists). Both are NOT NULL with a ``server_default`` of 1 so existing
installs keep email + pushover ON after upgrade (no surprise loss of alerts);
fresh rows rely on the model ``default=True``. ``batch_alter_table`` keeps this
SQLite-safe for the migration-smoke test.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9c5e3a07b218'
down_revision = '8b4d2f1c9a06'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('settings') as batch_op:
        batch_op.add_column(sa.Column('email_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')))
        batch_op.add_column(sa.Column('pushover_enabled', sa.Boolean(), nullable=False, server_default=sa.text('1')))


def downgrade():
    with op.batch_alter_table('settings') as batch_op:
        batch_op.drop_column('pushover_enabled')
        batch_op.drop_column('email_enabled')
