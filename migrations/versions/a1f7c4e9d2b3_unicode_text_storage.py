"""unicode text storage for usernames/plaintext

Revision ID: a1f7c4e9d2b3
Revises: 9c5e3a07b218
Create Date: 2026-06-05 00:00:00.000000

Usernames + recovered plaintext are now stored as plain UTF-8 text (with a
hashcat-style ``$HEX[...]`` marker for non-UTF-8 bytes) instead of latin-1 hex.

- Adds ``settings.passwords_decoded`` (the one-time hex->text backfill flag). It
  is NOT NULL with server_default 0 so EXISTING rows are flagged for the
  launch-time backfill (``decode_legacy_hex_if_needed``); fresh installs rely on
  the model default True (new Settings row is created already-decoded).
- On MySQL, widens the two text columns to utf8mb4 so 4-byte characters (emojis)
  fit. Guarded to MySQL only — SQLite stores UTF-8 natively, so it's a no-op
  there (keeps the migration-smoke / isolated tests backend-agnostic).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1f7c4e9d2b3'
down_revision = '9c5e3a07b218'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('settings') as batch_op:
        batch_op.add_column(sa.Column('passwords_decoded', sa.Boolean(), nullable=False, server_default=sa.text('0')))

    if op.get_bind().dialect.name == 'mysql':
        op.execute("ALTER TABLE hashfile_hashes MODIFY username VARCHAR(256) CHARACTER SET utf8mb4")
        op.execute("ALTER TABLE hashes MODIFY plaintext VARCHAR(256) CHARACTER SET utf8mb4")


def downgrade():
    with op.batch_alter_table('settings') as batch_op:
        batch_op.drop_column('passwords_decoded')
    # The utf8mb4 widening is intentionally not reverted (reverting to a narrower
    # charset could truncate/garble stored text); it is a safe superset.
