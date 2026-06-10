"""add task loopback flag

Revision ID: d4e8b1f3a297
Revises: c3d9f1a6b8e2
Create Date: 2026-06-08 00:00:00.000000

Adds ``tasks.loopback`` — the per-task opt-in for hashcat's ``--loopback``
(only emitted for straight mode + a rule; see ``build_hashcat_command``). NOT
NULL with a ``server_default`` of 0 so existing tasks keep loopback OFF after
upgrade; fresh rows rely on the model ``default=False``. ``batch_alter_table``
keeps this SQLite-safe for the migration-smoke test.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e8b1f3a297'
down_revision = 'c3d9f1a6b8e2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.add_column(sa.Column('loopback', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade():
    with op.batch_alter_table('tasks') as batch_op:
        batch_op.drop_column('loopback')
