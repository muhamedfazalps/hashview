"""Regression tests for the login post-auth redirect (open-redirect guard).

See issue #192: login honored an attacker-controlled ?next= without
validation, allowing an open redirect. login_post now routes through
_safe_next(), which only accepts a relative, same-site path.
"""

import pytest

from hashview.models import Users, db
from hashview.users.routes import bcrypt

PASSWORD = "correct horse battery staple"


@pytest.fixture()
def login_user_row(app):
    user = Users(
        first_name="Test",
        last_name="User",
        email_address="login@example.com",
        password=bcrypt.generate_password_hash(PASSWORD).decode("latin-1"),
        admin=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, next_value):
    return client.post(
        f"/login?next={next_value}",
        data={"email": "login@example.com", "password": PASSWORD},
        follow_redirects=False,
    )


def test_login_rejects_offsite_next(app, client, login_user_row):
    resp = _login(client, "https://evil.example")
    assert resp.status_code in (301, 302)
    assert "evil.example" not in resp.headers["Location"]


def test_login_rejects_protocol_relative_next(app, client, login_user_row):
    resp = _login(client, "//evil.example")
    assert resp.status_code in (301, 302)
    assert "evil.example" not in resp.headers["Location"]


def test_login_preserves_same_site_next(app, client, login_user_row):
    resp = _login(client, "/jobs")
    assert resp.status_code in (301, 302)
    assert resp.headers["Location"].endswith("/jobs")
