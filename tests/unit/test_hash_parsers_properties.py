"""Property-based tests for hash file parsers.

Generated counterparts to tests/unit/test_hash_parsers.py: instead of pinning
single examples, these assert invariants over arbitrary usernames/hashes —
the parser must never import machine accounts (trailing $), never import
*_history entries, and never crash on weird-but-structurally-valid lines.

Hypothesis runs each test body many times inside ONE function-scoped ``app``
fixture instance, so DB state accumulates across examples. Every example
therefore creates its own user (unique email) + hashfile and scopes all
assertions to that hashfile_id — never to global table counts.
"""

import os
import tempfile
import uuid

import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from hashview.models import Hashes, HashfileHashes, Hashfiles, Users, db
from hashview.utils.utils import import_hashfilehashes


# --- strategies -------------------------------------------------------------

HEX32 = st.text(alphabet="0123456789abcdefABCDEF", min_size=32, max_size=32)
USERNAME = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), max_codepoint=0x7F),
    min_size=1,
    max_size=20,
)

# Shared settings: the unit-test ``app`` fixture is function-scoped but each
# example builds its own hashfile, so suppressing the fixture health check is
# safe here. deadline=None because the first example pays SQLite setup cost.
PROPERTY_SETTINGS = settings(
    max_examples=50,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# --- helpers ----------------------------------------------------------------

def _make_user_and_hashfile() -> int:
    """Copy of the helper in test_hash_parsers.py, with a unique email so
    repeated creation across Hypothesis examples doesn't violate the unique
    constraint on Users.email_address."""
    user = Users(
        first_name="t",
        last_name="u",
        email_address=f"{uuid.uuid4().hex}@example.com",
        password="x" * 60,
        admin=True,
    )
    db.session.add(user)
    db.session.commit()
    hashfile = Hashfiles(
        name="t.txt",
        customer_id=1,
        owner_id=user.id,
    )
    db.session.add(hashfile)
    db.session.commit()
    return hashfile.id


def _import_text(text: str, hashfile_id: int, file_type: str, hash_type: str):
    """Write ``text`` to a temp file and run the real parser on it."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        return import_hashfilehashes(
            hashfile_id=hashfile_id,
            hashfile_path=path,
            file_type=file_type,
            hash_type=hash_type,
        )
    finally:
        os.unlink(path)


def _imported_rows(hashfile_id: int):
    return HashfileHashes.query.filter_by(hashfile_id=hashfile_id).all()


def _imported_ciphertexts(hashfile_id: int):
    return [
        row.ciphertext
        for row in Hashes.query.join(
            HashfileHashes, Hashes.id == HashfileHashes.hash_id
        )
        .filter(HashfileHashes.hashfile_id == hashfile_id)
        .all()
    ]


# --- invariant 1: pwdump machine accounts -----------------------------------

@pytest.mark.security
@PROPERTY_SETTINGS
@given(username=USERNAME, nt=HEX32)
def test_pwdump_machine_accounts_never_imported(app, username, nt):
    """Any username with a trailing ``$`` is a machine account and must never
    be imported, no matter what the rest of the line looks like. A control
    line with the bare username confirms the filter isn't dropping everything."""
    hashfile_id = _make_user_and_hashfile()
    text = (
        f"{username}$:1001:aad3b435b51404eeaad3b435b51404ee:{nt}:::\n"
        f"{username}:1002:aad3b435b51404eeaad3b435b51404ee:{nt}:::\n"
    )
    _import_text(text, hashfile_id, file_type="pwdump", hash_type="1000")

    usernames = {row.username for row in _imported_rows(hashfile_id)}
    assert f"{username}$" not in usernames, f"machine account {username}$ was imported"
    assert not any(u.endswith("$") for u in usernames)
    assert usernames == {username}
