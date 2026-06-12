"""Regression tests for notifications routes/helpers (function-coverage batch)."""

from hashview.models import (
    Hashes,
    HashfileHashes,
    HashNotifications,
    Settings,
    db,
)
from tests.unit.helpers import login, make_admin


def test_hash_type_names_maps_modes(app):
    from hashview.notifications.routes import _hash_type_names
    names = _hash_type_names()
    assert isinstance(names, dict)
    assert "1000" in names


def test_notifications_list_renders_with_seeded_notification(app, client):
    admin = make_admin()
    login(client, admin)
    db.session.add(Settings(email_enabled=True, pushover_enabled=True, slack_enabled=False))
    h = Hashes(sub_ciphertext="0" * 8, ciphertext="abc", hash_type=1000, cracked=False)
    db.session.add(h)
    db.session.commit()
    db.session.add(HashfileHashes(hash_id=h.id, hashfile_id=1, username="alice"))
    db.session.add(HashNotifications(owner_id=admin.id, hash_id=h.id, method="email"))
    db.session.commit()
    resp = client.get("/notifications")
    assert resp.status_code == 200
