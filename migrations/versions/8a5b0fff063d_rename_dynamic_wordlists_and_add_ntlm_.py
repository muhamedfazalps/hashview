"""rename dynamic wordlists and add NTLM dynamic wordlist

Revision ID: 8a5b0fff063d
Revises: dba208b9344c
Create Date: 2026-05-28 04:54:13.598898

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

    # Add the new All NTLM Hashes dynamic wordlist if absent.
    op.execute("""
        INSERT INTO wordlists (name, owner_id, type, path, size, checksum, last_updated)
        SELECT '(DYNAMIC) All NTLM Hashes', 1, 'dynamic',
               'hashview/control/wordlists/dynamic-ntlm.txt', 0, '', NOW()
        WHERE NOT EXISTS (SELECT 1 FROM wordlists WHERE name='(DYNAMIC) All NTLM Hashes')
    """)


def downgrade():
    op.execute("DELETE FROM wordlists WHERE name='(DYNAMIC) All NTLM Hashes'")
    op.execute("UPDATE wordlists SET name='(Dynamic) All Customers' WHERE name='(DYNAMIC) All Customers'")
    op.execute("UPDATE wordlists SET name='(Dynamic) All Usernames' WHERE name='(DYNAMIC) All Usernames'")
    op.execute("UPDATE wordlists SET name='(Dynamic) All Recovered Hashes' WHERE name='(DYNAMIC) All Recovered Passwords'")
