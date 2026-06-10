"""widen hashes.ciphertext to TEXT

Revision ID: e2b9c7a14d35
Revises: d4e8b1f3a297
Create Date: 2026-06-10 00:00:00.000000

The live MySQL ``hashes.ciphertext`` column drifted to ``VARCHAR(500)`` (see
fix_schema_drift, a671bad25f89, which only set NOT NULL with
existing_type=VARCHAR(500); nothing ever widened it), which truncates/rejects
long hashes (NetNTLMv2, Kerberos, etc. -> "Data too long for column 'ciphertext'").

It is widened to ``TEXT`` rather than a large ``VARCHAR``:
- ``VARCHAR(16383)`` in utf8mb4 is 65,532 bytes, which exceeds MySQL's hard
  65,535-byte row limit once the other columns are counted.
- ``CHARACTER SET ascii``/``latin1`` is not an option: the column already
  contains non-ASCII (UTF-8) bytes, so the conversion fails / would lose data.
``TEXT`` is stored off-page (no row-size limit) and holds ~64 KB. Keeping
``CHARACTER SET utf8mb4`` (the column's existing charset) makes this a lossless
widening of existing data.

Guarded to non-SQLite backends — SQLite has no MODIFY/CHARACTER SET syntax and
treats TEXT/VARCHAR interchangeably, so it's a no-op there (keeps the
migration-smoke / isolated tests backend-agnostic).
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = 'e2b9c7a14d35'
down_revision = 'd4e8b1f3a297'
branch_labels = None
depends_on = None


def upgrade():
    if op.get_bind().dialect.name != 'sqlite':
        op.execute("ALTER TABLE hashes MODIFY ciphertext TEXT CHARACTER SET utf8mb4 NOT NULL")


def downgrade():
    # Intentionally not reverted: narrowing back to VARCHAR(500) would truncate
    # already-stored long hashes. A wider column is a safe superset.
    pass
