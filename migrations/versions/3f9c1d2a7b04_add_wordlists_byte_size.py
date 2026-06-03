"""add wordlists.byte_size

Revision ID: 3f9c1d2a7b04
Revises: 8a5b0fff063d
Create Date: 2026-06-03 00:00:00.000000

Adds a nullable ``byte_size`` column to the ``wordlists`` table. This records
the on-disk size in bytes of the file at ``wordlists.path`` (the compressed
``.gz`` for static wordlists, the plaintext ``.txt`` for dynamic ones).

The column is left nullable and is backfilled at application startup by
``hashview/setup/__init__.py:compress_existing_wordlists_if_needed`` (which
also compresses any pre-existing uncompressed static wordlists). Using
``batch_alter_table`` keeps this SQLite-safe so the migration-smoke test can
walk the chain on an in-memory database.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '3f9c1d2a7b04'
down_revision = '8a5b0fff063d'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('wordlists') as batch_op:
        batch_op.add_column(sa.Column('byte_size', sa.BigInteger(), nullable=True))


def downgrade():
    with op.batch_alter_table('wordlists') as batch_op:
        batch_op.drop_column('byte_size')
