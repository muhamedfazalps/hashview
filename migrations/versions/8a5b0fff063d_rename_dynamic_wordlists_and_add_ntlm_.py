"""rename dynamic wordlists and add NTLM dynamic wordlist

Revision ID: 8a5b0fff063d
Revises: dba208b9344c
Create Date: 2026-05-28 04:54:13.598898

This migration only renames the existing dynamic wordlists. The new
"(DYNAMIC) All NTLM Hashes" wordlist is not inserted here — instead it gets
created at app startup by
``hashview/setup/__init__.py:add_default_dynamic_wordlists``, which runs
after the admin user exists. Earlier versions of this migration tried to
``INSERT INTO wordlists (... owner_id=1 ...)`` directly, which failed with a
foreign-key violation on a fresh install because the admin user is created
after ``flask db upgrade`` finishes.

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = '8a5b0fff063d'
down_revision = 'dba208b9344c'
branch_labels = None
depends_on = None


def upgrade():
    # Rename existing dynamic wordlists to the new (DYNAMIC) prefix and the
    # "Passwords" terminology. The rename also fixes the dispatcher in
    # hashview/utils/utils.py:update_dynamic_wordlist, which matches by
    # substring ('Passwords' / 'Usernames' / 'Customers' / 'NTLM').
    op.execute("UPDATE wordlists SET name='(DYNAMIC) All Recovered Passwords' WHERE name='(Dynamic) All Recovered Hashes'")
    op.execute("UPDATE wordlists SET name='(DYNAMIC) All Usernames' WHERE name='(Dynamic) All Usernames'")
    op.execute("UPDATE wordlists SET name='(DYNAMIC) All Customers' WHERE name='(Dynamic) All Customers'")


def downgrade():
    op.execute("UPDATE wordlists SET name='(Dynamic) All Customers' WHERE name='(DYNAMIC) All Customers'")
    op.execute("UPDATE wordlists SET name='(Dynamic) All Usernames' WHERE name='(DYNAMIC) All Usernames'")
    op.execute("UPDATE wordlists SET name='(Dynamic) All Recovered Hashes' WHERE name='(DYNAMIC) All Recovered Passwords'")
