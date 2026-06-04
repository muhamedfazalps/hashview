"""add slack notification settings

Revision ID: 8b4d2f1c9a06
Revises: 5c2e1f4a9d37
Create Date: 2026-06-04 00:00:00.000000

Adds Slack bot notification support:
- ``settings.slack_enabled`` / ``settings.slack_bot_token``  (global: admin enables
  Slack and stores the bot ``xoxb-`` token),
- ``users.slack_id``  (per-user Slack Member ID the bot DMs).

``slack_enabled`` is NOT NULL with a ``server_default`` of 0 so the existing single
Settings row backfills to "disabled"; fresh rows rely on the model ``default=False``.
``batch_alter_table`` keeps this SQLite-safe for the migration-smoke test.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8b4d2f1c9a06'
down_revision = '5c2e1f4a9d37'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('settings') as batch_op:
        batch_op.add_column(sa.Column('slack_enabled', sa.Boolean(), nullable=False, server_default=sa.text('0')))
        batch_op.add_column(sa.Column('slack_bot_token', sa.String(length=255), nullable=True))

    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('slack_id', sa.String(length=50), nullable=True))


def downgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('slack_id')

    with op.batch_alter_table('settings') as batch_op:
        batch_op.drop_column('slack_bot_token')
        batch_op.drop_column('slack_enabled')
