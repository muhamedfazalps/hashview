"""Hashfile delete cascade tests.

CHANGELOG v0.8.2 claims hashfile deletion "properly cascades through all
related records" and explicitly calls out that the prior implementation
"removed hashes that belonged to other hashfiles". These tests pin that:

1. Deleting hashfile A removes its own HashfileHashes rows.
2. A hash that was *only* referenced by A and is uncracked gets pruned.
3. A hash that was *shared* with hashfile B must SURVIVE (the bug fixed).
4. A *cracked* hash referenced only by A must SURVIVE (cracked hashes are
   user-valuable and not cascaded).
"""

import pytest
from flask_login import login_user

from hashview.models import (
    Customers,
    HashfileHashes,
    Hashes,
    Hashfiles,
    Users,
    db,
)


def _make_admin():
    admin = Users(
        first_name="A",
        last_name="D",
        email_address="admin@example.com",
        password="x" * 60,
        admin=True,
    )
    db.session.add(admin)
    db.session.commit()
    return admin


def _make_customer():
    c = Customers(name="X")
    db.session.add(c)
    db.session.commit()
    return c


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


@pytest.mark.security
def test_hashfile_delete_keeps_shared_hash_and_cracked_hash(app, client):
    admin = _make_admin()
    cust = _make_customer()

    # Two hashfiles
    hf_a = Hashfiles(name="A", customer_id=cust.id, owner_id=admin.id)
    hf_b = Hashfiles(name="B", customer_id=cust.id, owner_id=admin.id)
    db.session.add_all([hf_a, hf_b])
    db.session.commit()

    # Three hashes:
    #   only_in_a_uncracked    — should be pruned when A is deleted
    #   shared_a_and_b         — must survive (was the bug)
    #   only_in_a_cracked      — must survive (cracked hashes are user data)
    only_a = Hashes(sub_ciphertext="0" * 32, ciphertext="aaaa",
                    hash_type=0, cracked=False)
    shared = Hashes(sub_ciphertext="1" * 32, ciphertext="bbbb",
                    hash_type=0, cracked=False)
    cracked = Hashes(sub_ciphertext="2" * 32, ciphertext="cccc",
                     hash_type=0, cracked=True, plaintext="70617373")  # 'pass'
    db.session.add_all([only_a, shared, cracked])
    db.session.commit()

    db.session.add_all([
        HashfileHashes(hashfile_id=hf_a.id, hash_id=only_a.id),
        HashfileHashes(hashfile_id=hf_a.id, hash_id=shared.id),
        HashfileHashes(hashfile_id=hf_b.id, hash_id=shared.id),
        HashfileHashes(hashfile_id=hf_a.id, hash_id=cracked.id),
    ])
    db.session.commit()

    only_a_id = only_a.id
    shared_id = shared.id
    cracked_id = cracked.id
    hf_a_id = hf_a.id
    hf_b_id = hf_b.id

    _login(client, admin.id)
    resp = client.post(f"/hashfiles/delete/{hf_a_id}", follow_redirects=False)
    assert resp.status_code in (200, 302)

    # Hashfile A is gone; hashfile B remains.
    assert Hashfiles.query.get(hf_a_id) is None
    assert Hashfiles.query.get(hf_b_id) is not None

    # The shared hash MUST survive (the original bug).
    assert Hashes.query.get(shared_id) is not None, (
        "Shared hash was deleted with hashfile A — cascade bug regression."
    )
    # B's HashfileHashes link to it must also survive.
    assert HashfileHashes.query.filter_by(
        hashfile_id=hf_b_id, hash_id=shared_id
    ).first() is not None

    # The cracked-only-in-A hash must also survive.
    assert Hashes.query.get(cracked_id) is not None, (
        "Cracked hash should never be cascade-deleted by a hashfile delete."
    )

    # The orphan uncracked hash that A solely owned should be pruned.
    assert Hashes.query.get(only_a_id) is None
