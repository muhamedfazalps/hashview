"""Shared seeding/login helpers for unit route tests.

The login pattern mirrors tests/unit/test_delete_idempotency.py: create a row,
then set Flask-Login's session keys directly so no password/CSRF dance is
needed. Constructors match hashview/models.py (non-nullable columns supplied).
"""

from hashview.models import Customers, Users, db


def make_admin(email="admin@example.com"):
    u = Users(first_name="Ad", last_name="Min", email_address=email,
              password="x" * 60, admin=True)
    db.session.add(u)
    db.session.commit()
    return u


def make_user(email="user@example.com"):
    u = Users(first_name="Plain", last_name="User", email_address=email,
              password="x" * 60, admin=False)
    db.session.add(u)
    db.session.commit()
    return u


def login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def make_customer(name="Test Customer"):
    c = Customers(name=name)
    db.session.add(c)
    db.session.commit()
    return c
