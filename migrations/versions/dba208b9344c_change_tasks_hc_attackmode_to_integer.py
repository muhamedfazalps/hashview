"""change tasks.hc_attackmode to Integer

Revision ID: dba208b9344c
Revises: a02b6f567b7b
Create Date: 2026-05-28 04:28:34.490020

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'dba208b9344c'
down_revision = 'a02b6f567b7b'
branch_labels = None
depends_on = None


def upgrade():
    # Normalize legacy textual values to their numeric equivalents BEFORE the
    # column type change so MySQL's implicit cast can't silently turn them
    # into 0. Mapping comes from hashview/tasks/forms.py choices.
    op.execute("UPDATE tasks SET hc_attackmode = '0' WHERE hc_attackmode = 'dictionary'")
    op.execute("UPDATE tasks SET hc_attackmode = '1' WHERE hc_attackmode = 'combinator'")
    op.execute("UPDATE tasks SET hc_attackmode = '3' WHERE hc_attackmode IN ('maskmode', 'bruteforce')")

    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.alter_column('hc_attackmode',
               existing_type=mysql.VARCHAR(length=25),
               type_=sa.Integer(),
               existing_nullable=False)


def downgrade():
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.alter_column('hc_attackmode',
               existing_type=sa.Integer(),
               type_=mysql.VARCHAR(length=25),
               existing_nullable=False)
