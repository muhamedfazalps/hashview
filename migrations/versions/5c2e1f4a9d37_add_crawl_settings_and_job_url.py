"""add crawl settings + jobs.crawl_url

Revision ID: 5c2e1f4a9d37
Revises: 3f9c1d2a7b04
Create Date: 2026-06-03 00:00:00.000000

Adds the website-keywords crawler settings to the ``settings`` table and a
``crawl_url`` column to ``jobs`` (the per-job URL captured during job creation
for the "(DYNAMIC) Website Keywords" wordlist).

The five settings columns are added NOT NULL with a ``server_default`` so that
existing single Settings rows are backfilled with sensible defaults; fresh
rows created by the setup flow rely on the SQLAlchemy model ``default=``.
``batch_alter_table`` keeps this SQLite-safe for the migration-smoke test.
"""
from alembic import op
import sqlalchemy as sa

from hashview.models import DEFAULT_CRAWL_USER_AGENT


# revision identifiers, used by Alembic.
revision = '5c2e1f4a9d37'
down_revision = '3f9c1d2a7b04'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('settings') as batch_op:
        batch_op.add_column(sa.Column('crawl_min_word_length', sa.Integer(), nullable=False, server_default='8'))
        batch_op.add_column(sa.Column('crawl_user_agent', sa.String(length=255), nullable=False, server_default=DEFAULT_CRAWL_USER_AGENT))
        batch_op.add_column(sa.Column('crawl_force_lowercase', sa.Boolean(), nullable=False, server_default=sa.text('1')))
        batch_op.add_column(sa.Column('crawl_depth', sa.Integer(), nullable=False, server_default='2'))
        batch_op.add_column(sa.Column('crawl_threads', sa.Integer(), nullable=False, server_default='5'))

    with op.batch_alter_table('jobs') as batch_op:
        batch_op.add_column(sa.Column('crawl_url', sa.String(length=2048), nullable=True))


def downgrade():
    with op.batch_alter_table('jobs') as batch_op:
        batch_op.drop_column('crawl_url')

    with op.batch_alter_table('settings') as batch_op:
        batch_op.drop_column('crawl_threads')
        batch_op.drop_column('crawl_depth')
        batch_op.drop_column('crawl_force_lowercase')
        batch_op.drop_column('crawl_user_agent')
        batch_op.drop_column('crawl_min_word_length')
