"""Unit tests for hashview.api.routes.

Each test exercises a route from the ``api`` Blueprint using the in-memory
SQLite app + Flask test_client fixtures provided by ``tests/unit/conftest.py``.
All tests are marked ``@pytest.mark.security`` so the parent autouse fixtures
that require Playwright + a live HTTP server are skipped.

Auth model recap (see ``is_authorized``):
- The 'uuid' cookie value is matched against either ``Users.api_key`` (when
  the route allows users) or ``Agents.uuid`` (when the route allows agents,
  with status in Online/Working/Idle/Authorized).
- Unauthorized requests are answered with a redirect to ``/v1/not_authorized``
  (or, for two buggy routes, the typo'd ``/vi/not_authorized``).
"""

import json
import os

import pytest

from hashview.models import (
    Agents,
    Customers,
    Hashfiles,
    Jobs,
    Settings,
    Users,
    Wordlists,
)
from hashview.models import db as _db


# ---------------------------------------------------------------------------
# Local fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def admin_user(app):
    user = Users(
        first_name="Admin",
        last_name="User",
        email_address="admin@example.test",
        password="hashed-pw",
        admin=True,
        api_key="user-api-key-admin",
    )
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture()
def authorized_agent(app):
    agent = Agents(
        name="agent-1",
        src_ip="127.0.0.1",
        uuid="agent-uuid-ok",
        status="Authorized",
    )
    _db.session.add(agent)
    _db.session.commit()
    return agent


def _json_body(resp):
    """Return parsed JSON body from a Flask test response."""
    return json.loads(resp.get_data(as_text=True))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_admin_settings_authorized_returns_200_with_settings(client, admin_user):
    """GET /v1/admin/settings with a valid user api_key cookie returns 200."""
    settings_row = Settings(
        retention_period=30,
        max_runtime_tasks=0,
        max_runtime_jobs=0,
    )
    _db.session.add(settings_row)
    _db.session.commit()

    client.set_cookie("uuid", admin_user.api_key)
    resp = client.get("/v1/admin/settings")

    assert resp.status_code == 200
    body = _json_body(resp)
    assert body["status"] == 200
    assert "settings" in body


@pytest.mark.security
def test_admin_settings_no_cookie_redirects_to_not_authorized(client):
    """GET /v1/admin/settings without a cookie redirects to /v1/not_authorized."""
    resp = client.get("/v1/admin/settings")
    assert 300 <= resp.status_code < 400
    location = resp.headers.get("Location", "")
    assert "/v1/not_authorized" in location


@pytest.mark.security
def test_customers_list_authorized_returns_seeded_customer(client, admin_user):
    """GET /v1/customers returns the seeded Customer in the JSON-string body."""
    cust = Customers(name="Acme")
    _db.session.add(cust)
    _db.session.commit()

    client.set_cookie("uuid", admin_user.api_key)
    resp = client.get("/v1/customers")

    assert resp.status_code == 200
    body = _json_body(resp)
    # Route returns the customer collection serialized as a JSON string under
    # the (oddly named) "users" key.
    assert "Acme" in body["users"]


@pytest.mark.security
def test_customers_add_with_body_returns_status_and_id_key(client, admin_user):
    """POST /v1/customers/add with a name-only JSON body creates a Customer."""
    client.set_cookie("uuid", admin_user.api_key)
    resp = client.post(
        "/v1/customers/add",
        data=json.dumps({"name": "Globex"}),
        content_type="application/json",
    )
    body = _json_body(resp)
    assert body["status"] == 200
    assert body["msg"] == "Customer added"
    assert isinstance(body["customer_id"], int)
    assert Customers.query.filter_by(name="Globex").first() is not None


@pytest.mark.security
def test_customers_add_missing_body_returns_400(client, admin_user):
    """POST /v1/customers/add with no JSON body returns status 400."""
    client.set_cookie("uuid", admin_user.api_key)
    resp = client.post(
        "/v1/customers/add",
        data="",
        content_type="application/json",
    )
    body = _json_body(resp)
    assert body["status"] == 400
    assert "Missing" in body["msg"]


@pytest.mark.security
def test_wordlists_add_writes_file_and_creates_row(
    client, app, admin_user, tmp_path, monkeypatch
):
    """POST /v1/wordlists/add/<name> writes the file and creates a row."""
    # Point the route at a tmp directory and create the expected subdir.
    monkeypatch.setattr(app, "root_path", str(tmp_path))
    os.makedirs(os.path.join(str(tmp_path), "control", "wordlists"), exist_ok=True)

    body_text = "alpha\nbeta\n"
    client.set_cookie("uuid", admin_user.api_key)
    resp = client.post(
        "/v1/wordlists/add/my-list",
        data=body_text,
        content_type="text/plain",
    )

    body = _json_body(resp)
    assert body["status"] == 200
    assert body["msg"] == "Wordlist added"

    row = Wordlists.query.filter_by(name="my-list").first()
    assert row is not None
    assert row.type == "static"
    assert row.owner_id == admin_user.id
    # File on disk should contain the original raw body.
    with open(row.path, "r") as fh:
        assert fh.read() == body_text


@pytest.mark.security
def test_jobs_start_rejects_agent_cookie(client, authorized_agent):
    """POST /v1/jobs/start/<id> with an agent cookie redirects to not_authorized.

    The route uses ``is_authorized(user=True, agent=False, ...)`` so even a
    valid agent uuid must be refused.
    """
    client.set_cookie("uuid", authorized_agent.uuid)
    resp = client.post("/v1/jobs/start/1")
    assert 300 <= resp.status_code < 400
    location = resp.headers.get("Location", "")
    assert "not_authorized" in location


@pytest.mark.security
def test_jobs_start_returns_400_when_job_not_queued(client, admin_user):
    """POST /v1/jobs/start/<id> for a Ready (not Queued) job returns 400."""
    cust = Customers(name="CustForJob")
    _db.session.add(cust)
    _db.session.commit()

    hashfile = Hashfiles(
        name="hf",
        customer_id=cust.id,
        owner_id=admin_user.id,
    )
    _db.session.add(hashfile)
    _db.session.commit()

    job = Jobs(
        name="my-job",
        status="Ready",
        hashfile_id=hashfile.id,
        customer_id=cust.id,
        owner_id=admin_user.id,
    )
    _db.session.add(job)
    _db.session.commit()

    # The route requires at least one JobTask for the "not queued" branch
    # to be reachable. Seed one so we hit the status check rather than the
    # "Invalid job ID" fallback.
    from hashview.models import JobTasks
    job_task = JobTasks(
        job_id=job.id,
        task_id=1,
        status="Not Started",
    )
    _db.session.add(job_task)
    _db.session.commit()

    client.set_cookie("uuid", admin_user.api_key)
    resp = client.post(f"/v1/jobs/start/{job.id}")
    body = _json_body(resp)
    assert body["status"] == 400
    assert "queued" in body["msg"].lower()


@pytest.mark.security
def test_hashes_import_unsupported_hash_type_returns_403(client, admin_user):
    """POST /v1/hashes/import/<n> for an unsupported hash type returns 403."""
    client.set_cookie("uuid", admin_user.api_key)
    resp = client.post(
        "/v1/hashes/import/500",
        data="x",
        content_type="text/plain",
    )
    body = _json_body(resp)
    assert body["status"] == 403
    assert "Unsupported" in body["msg"]


@pytest.mark.security
def test_hashes_import_hash_type_1000_documents_str_int_bug(client, admin_user):
    """Documents a known str/int comparison bug in the route.

    The route declares ``<int:hash_type>`` (so the value arrives as int) but
    then guards on ``if hash_type == '1000':`` (a string literal). The two
    types never compare equal, so the supported branch is unreachable and
    every request, including hash_type=1000, falls through to the 403
    "Unsupported Hashtype" branch.

    When the bug is fixed (compare to int 1000 instead of '1000'), this
    test will fail loudly and should be updated to reflect the new
    behavior.
    """
    client.set_cookie("uuid", admin_user.api_key)
    resp = client.post(
        "/v1/hashes/import/1000",
        data="x",
        content_type="text/plain",
    )
    body = _json_body(resp)
    assert body["status"] == 403
    assert "Unsupported" in body["msg"]


@pytest.mark.security
def test_error_route_rejects_user_cookie(client, admin_user):
    """POST /v1/error with a user cookie redirects to (typo'd) not_authorized.

    The route uses ``is_authorized(user=False, agent=True, ...)`` so a user
    api_key cookie is refused. The route's redirect target is the typo'd
    ``/vi/not_authorized`` — we tolerate either variant.
    """
    client.set_cookie("uuid", admin_user.api_key)
    resp = client.post(
        "/v1/error",
        data=json.dumps({"error": "oh no"}),
        content_type="application/json",
    )
    assert resp.status_code in {301, 302, 303, 307, 308}
    location = resp.headers.get("Location") or ""
    assert "not_authorized" in location


@pytest.mark.security
def test_error_route_accepts_agent_cookie_returns_ok(
    client, admin_user, authorized_agent, monkeypatch
):
    """POST /v1/error with a valid agent cookie returns status 200 / msg OK."""
    # notify_admins -> send_email / send_pushover; stub them out so we don't
    # try to actually send mail in the test.
    import hashview.utils.utils as utils_mod

    monkeypatch.setattr(utils_mod, "send_email", lambda *a, **kw: True)
    monkeypatch.setattr(utils_mod, "send_pushover", lambda *a, **kw: None)

    client.set_cookie("uuid", authorized_agent.uuid)
    resp = client.post(
        "/v1/error",
        data=json.dumps({"error": "agent saw something"}),
        content_type="application/json",
    )
    body = _json_body(resp)
    assert body["status"] == 200
    assert body["msg"] == "OK"


@pytest.mark.security
def test_api_route_without_cookie_redirects_to_not_authorized(client):
    """GET /v1/rules without a cookie redirects to /v1/not_authorized."""
    resp = client.get("/v1/rules")
    assert 300 <= resp.status_code < 400
    location = resp.headers.get("Location", "")
    assert "not_authorized" in location
