"""reconcile model drift with schema

Revision ID: a02b6f567b7b
Revises: 8027c2d2b40a
Create Date: 2026-05-27 18:16:35.389246

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'a02b6f567b7b'
down_revision = '8027c2d2b40a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('hashes', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recovered_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('task_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('recovered_by', sa.Integer(), nullable=True))

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('limit_recovered', sa.Boolean(), nullable=False))

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('wl_id_2', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('j_rule', sa.String(length=25), nullable=True))
        batch_op.add_column(sa.Column('k_rule', sa.String(length=25), nullable=True))


def downgrade():
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_column('k_rule')
        batch_op.drop_column('j_rule')
        batch_op.drop_column('wl_id_2')

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_column('limit_recovered')

    with op.batch_alter_table('hashes', schema=None) as batch_op:
        batch_op.drop_column('recovered_by')
        batch_op.drop_column('task_id')
        batch_op.drop_column('recovered_at')
