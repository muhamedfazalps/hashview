"""Unit tests for the audit / event logging feature (hashview.utils.audit).

The audit + error loggers are process-global, but ``configure_audit_logging``
is idempotent (it removes its own previously-attached handlers before
re-adding), so the ``audit_app`` fixture re-points both loggers into a
per-test ``tmp_path`` by monkeypatching ``app.root_path`` and reconfiguring.

All tests are marked ``@pytest.mark.security`` so the parent autouse fixtures
that require Playwright + a live HTTP server are skipped (see conftest).
"""

import json
import os

import pytest

from hashview.models import Settings, Users
from hashview.models import db as _db
from hashview.utils.audit import (
    AUDIT_FILE,
    ERROR_FILE,
    configure_audit_logging,
    log_event,
    logs_dir,
)


@pytest.fixture()
def audit_app(app, tmp_path):
    """Re-point the audit/error loggers into tmp_path for this test.

    Uses the HASHVIEW_LOGS_DIR config override rather than monkeypatching
    app.root_path (which would also break Flask's template loader).
    """
    app.config["HASHVIEW_LOGS_DIR"] = str(tmp_path / "logs")
    configure_audit_logging(app)   # idempotent: re-attaches handlers under tmp_path
    return app


def _admin(api_key="audit-admin-key"):
    user = Users(
        first_name="Audit",
        last_name="Admin",
        email_address="audit-admin@example.test",
        password="x" * 60,
        admin=True,
        api_key=api_key,
    )
    _db.session.add(user)
    _db.session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def _lines(app, fname=AUDIT_FILE):
    path = os.path.join(logs_dir(app), fname)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# ---------------------------------------------------------------------------
# Core helper
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_log_event_writes_json_line(audit_app):
    """log_event appends a parseable JSON object; outside a request the actor
    and ip are null."""
    with audit_app.app_context():
        log_event("job.create", target="job:1 'demo'", detail="hi")

    entries = _lines(audit_app)
    assert entries, "audit.log should have at least one line"
    last = entries[-1]
    assert last["event"] == "job.create"
    assert last["target"] == "job:1 'demo'"
    assert last["outcome"] == "success"
    assert last["detail"] == "hi"
    assert last["actor"] is None and last["actor_id"] is None
    assert last["ip"] is None
    assert "ts" in last


# ---------------------------------------------------------------------------
# Auth events
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_login_failure_is_audited(client, audit_app):
    """A bad login writes a user.login_failed line with the attempted email."""
    resp = client.post(
        "/login",
        data={"email": "ghost@example.com", "password": "nope", "submit": "Login"},
    )
    # Failed login re-renders the login page (HTTP 200) — no redirect.
    assert resp.status_code == 200

    failed = [e for e in _lines(audit_app) if e["event"] == "user.login_failed"]
    assert failed, "expected a user.login_failed audit line"
    assert failed[-1]["outcome"] == "failure"
    assert "ghost@example.com" in (failed[-1]["detail"] or "")
    assert failed[-1]["actor"] is None


@pytest.mark.security
def test_successful_login_is_audited(client, audit_app):
    """A good login writes a user.login line attributed to that user."""
    from hashview.users.routes import bcrypt
    pw = bcrypt.generate_password_hash("correct-horse-battery").decode("latin-1")
    user = Users(first_name="Log", last_name="In",
                 email_address="loginok@example.com", password=pw, admin=False)
    _db.session.add(user)
    _db.session.commit()

    resp = client.post(
        "/login",
        data={"email": "loginok@example.com",
              "password": "correct-horse-battery", "submit": "Login"},
    )
    assert resp.status_code in (301, 302)
    ok = [e for e in _lines(audit_app) if e["event"] == "user.login"]
    assert ok and ok[-1]["actor"] == "loginok@example.com"
    assert ok[-1]["actor_id"] == user.id


# ---------------------------------------------------------------------------
# Actor resolution — web session vs api_key cookie
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_web_event_resolves_session_actor(client, audit_app):
    """A logged-in web user's action is attributed to their session identity."""
    admin = _admin()
    _login(client, admin)

    resp = client.post("/customers/add", data={"name": "WebCo", "submit": "Add"})
    assert resp.status_code in (301, 302)

    created = [e for e in _lines(audit_app) if e["event"] == "customer.create"]
    assert created, "expected a customer.create audit line"
    assert created[-1]["actor"] == admin.email_address
    assert created[-1]["actor_id"] == admin.id
    assert "WebCo" in created[-1]["target"]


@pytest.mark.security
def test_api_event_resolves_api_key_actor(client, audit_app):
    """An API action authenticated by the uuid cookie resolves the api_key user."""
    admin = _admin(api_key="audit-api-key")
    client.set_cookie("uuid", "audit-api-key", domain="localhost.test")

    resp = client.post(
        "/v1/customers/add",
        data=json.dumps({"name": "ApiCo"}),
        content_type="application/json",
    )
    body = json.loads(resp.get_data(as_text=True))
    assert body["status"] == 200

    created = [e for e in _lines(audit_app) if e["event"] == "customer.create"]
    assert created and created[-1]["actor"] == admin.email_address
    assert created[-1]["actor_id"] == admin.id
    assert "ApiCo" in created[-1]["target"]


# ---------------------------------------------------------------------------
# 500-error capture
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_unhandled_exception_is_logged_to_error_log(client, audit_app):
    """Any unhandled exception (an HTTP 500) is recorded in error.log with a
    traceback, without being captured for the body-level {'status':500} API
    returns (those are plain jsonify, not raised)."""
    audit_app.add_url_rule("/__boom", "__boom", lambda: 1 / 0)
    # Return the 500 to the client instead of re-raising, so the signal fires
    # and we can assert on the response too.
    audit_app.config["PROPAGATE_EXCEPTIONS"] = False

    resp = client.get("/__boom")
    assert resp.status_code == 500

    errors = _lines(audit_app, ERROR_FILE)
    assert errors, "expected a server.error line in error.log"
    last = errors[-1]
    assert last["event"] == "server.error"
    assert last["outcome"] == "failure"
    assert last["target"] == "GET /__boom"
    assert "ZeroDivisionError" in (last.get("traceback") or "")


# ---------------------------------------------------------------------------
# Clear logs (Settings -> Data management)
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_clear_logs_admin_truncates_and_self_audits(client, audit_app):
    """Admin clear_logs truncates the live files, removes rotated backups, and
    leaves a single fresh logs.clear line."""
    _db.session.add(Settings(retention_period=30, max_runtime_jobs=0, max_runtime_tasks=0))
    admin = _admin()
    _login(client, admin)

    # Seed some prior content + a rotated backup.
    with audit_app.app_context():
        log_event("job.create", target="job:9 'old'")
    backup = os.path.join(logs_dir(audit_app), "audit.log.1")
    open(backup, "w").close()

    resp = client.post("/settings/clear_logs")
    assert resp.status_code in (301, 302)
    assert not os.path.exists(backup), "rotated backup should be removed"

    entries = _lines(audit_app)
    assert len(entries) == 1, "audit.log should be truncated to just the clear line"
    assert entries[0]["event"] == "logs.clear"
    assert entries[0]["actor"] == admin.email_address


@pytest.mark.security
def test_clear_logs_rejects_non_admin(client, audit_app):
    """A non-admin cannot clear the logs and the files are left intact."""
    _db.session.add(Settings(retention_period=30, max_runtime_jobs=0, max_runtime_tasks=0))
    user = Users(first_name="Reg", last_name="User",
                 email_address="reg@example.test", password="x" * 60, admin=False)
    _db.session.add(user)
    _db.session.commit()
    _login(client, user)

    with audit_app.app_context():
        log_event("job.create", target="job:1 'keep'")
    before = len(_lines(audit_app))

    resp = client.post("/settings/clear_logs")
    assert resp.status_code == 403
    assert len(_lines(audit_app)) == before, "non-admin must not clear the logs"
