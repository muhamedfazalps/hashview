"""Unit tests for the admin Logs viewer (hashview.logs.routes).

Reuses the audit logging test conventions: the ``audit_app`` fixture points the
audit/error loggers at a tmp dir via the HASHVIEW_LOGS_DIR override, and
``log_event`` seeds audit lines. All tests are ``@pytest.mark.security`` so the
parent Playwright autouse fixtures are skipped (see conftest).
"""

import json
import os

import pytest

from hashview.models import Users
from hashview.models import db as _db
from hashview.utils.audit import (
    ERROR_FILE,
    configure_audit_logging,
    log_event,
    logs_dir,
    read_log_entries,
)


@pytest.fixture()
def audit_app(app, tmp_path):
    app.config["HASHVIEW_LOGS_DIR"] = str(tmp_path / "logs")
    configure_audit_logging(app)
    return app


def _user(admin=True, email="logs-admin@example.com"):
    user = Users(first_name="Log", last_name="Viewer", email_address=email,
                 password="x" * 60, admin=admin, api_key=None)
    _db.session.add(user)
    _db.session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def _seed_error(app, **over):
    """Write one server.error line directly into error.log."""
    rec = {
        "ts": "2026-06-08T03:30:00.000-05:00", "event": "server.error",
        "actor": "j.mercer", "actor_id": 2, "ip": "10.0.0.5",
        "target": "POST /jobs/new", "outcome": "failure",
        "detail": "IntegrityError('UNIQUE constraint failed: jobs.name')",
        "traceback": "Traceback (most recent call last):\n  ...\nIntegrityError",
    }
    rec.update(over)
    os.makedirs(logs_dir(app), exist_ok=True)
    with open(os.path.join(logs_dir(app), ERROR_FILE), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


# ---------------------------------------------------------------------------
# read_log_entries
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_read_log_entries_newest_first_and_capped(audit_app):
    with audit_app.app_context():
        for i in range(5):
            log_event("job.create", target=f"job:{i} 'j{i}'")
    entries = read_log_entries(audit_app, "audit", limit=3)
    assert len(entries) == 3
    # newest first → the last-written (j4) comes first
    assert entries[0]["target"] == "job:4 'j4'"


@pytest.mark.security
def test_read_log_entries_missing_file_is_empty(audit_app):
    assert read_log_entries(audit_app, "error") == []


# ---------------------------------------------------------------------------
# /logs page
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_logs_view_audit_renders_seeded_event(client, audit_app):
    admin = _user()
    with audit_app.app_context():
        log_event("job.create", actor=("j.mercer", 2), target="job:17 'Q2 External Pentest'")
    _login(client, admin)

    resp = client.get("/logs")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Q2 External Pentest" in html        # entity name
    assert 'badge green">CREATE' in html        # action badge
    assert "j.mercer" in html                   # actor
    assert "All actions" in html                # audit dropdown present
    assert "/logs/download/audit" in html       # export link
    # pills + filter + dropdown + export all live in the single toolbar row
    assert html.count('class="card-head"') == 1


@pytest.mark.security
def test_logs_view_error_renders_seeded_error(client, audit_app):
    admin = _user()
    _seed_error(audit_app)
    _login(client, admin)

    resp = client.get("/logs?view=error")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'badge red">500' in html
    assert "/jobs/new" in html                  # route path
    assert "IntegrityError" in html             # exception class
    assert "All actions" not in html            # no action dropdown on errors
    assert "/logs/download/error" in html


@pytest.mark.security
def test_audit_modal_fields_and_ip_color(client, audit_app):
    """The audit detail modal renders entity/actor/IP, embeds raw JSON, colors
    the IP teal (--cyan), and omits the request-id / user-agent fields."""
    admin = _user()
    with audit_app.app_context():
        log_event("job.create", actor=("j.mercer", 2), target="job:14 'Q2 External Pentest'")
    _login(client, admin)

    html = client.get("/logs").get_data(as_text=True)
    assert 'id="audit-modal-1"' in html          # per-row detail modal
    assert "var(--cyan)" in html                  # IP rendered teal/blue
    assert "View raw .json" in html and "Download .json" in html
    assert "USER AGENT" not in html.upper()       # omitted (not captured)
    assert ">Request<" not in html                # omitted (not captured)
    assert "&#34;event&#34;" in html or "&quot;event&quot;" in html  # raw JSON embedded (escaped)


@pytest.mark.security
def test_error_modal_shows_traceback_and_location(client, audit_app):
    """The error detail modal renders the traceback + parsed location and omits
    the request-id field."""
    admin = _user()
    _seed_error(audit_app, traceback=(
        'Traceback (most recent call last):\n'
        '  File "/srv/hashview/jobs/routes.py", line 214, in create_job\n'
        '    db.session.commit()\nIntegrityError'))
    _login(client, admin)

    html = client.get("/logs?view=error").get_data(as_text=True)
    assert 'id="error-modal-1"' in html
    assert "Traceback (most recent call last)" in html
    assert "hashview/jobs/routes.py:214" in html  # location parsed from traceback
    assert ">Request<" not in html                # omitted (not captured)


@pytest.mark.security
def test_logs_view_rejects_non_admin(client, audit_app):
    user = _user(admin=False, email="reg@example.com")
    _login(client, user)
    assert client.get("/logs").status_code == 403


@pytest.mark.security
def test_logs_view_requires_login(client, audit_app):
    resp = client.get("/logs")
    assert 300 <= resp.status_code < 400
    assert "/login" in resp.headers.get("Location", "")


# ---------------------------------------------------------------------------
# /logs/download/<which>
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_logs_download_returns_attachment(client, audit_app):
    admin = _user()
    with audit_app.app_context():
        log_event("job.create", target="job:1 'x'")
    _login(client, admin)

    resp = client.get("/logs/download/audit")
    assert resp.status_code == 200
    assert "attachment" in resp.headers.get("Content-Disposition", "")
    assert "audit.log" in resp.headers.get("Content-Disposition", "")


@pytest.mark.security
def test_logs_download_invalid_which_404(client, audit_app):
    admin = _user()
    _login(client, admin)
    assert client.get("/logs/download/bogus").status_code == 404


@pytest.mark.security
def test_logs_download_rejects_non_admin(client, audit_app):
    user = _user(admin=False, email="reg2@example.com")
    _login(client, user)
    assert client.get("/logs/download/audit").status_code == 403
