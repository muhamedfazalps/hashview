"""Tests keeping hashview/api_docs/openapi.yaml honest.

Three guarantees:
  1. The spec is structurally valid OpenAPI (same check as CI / pre-commit).
  2. info.version matches hashview.__version__.
  3. Two-way parity between the spec's paths/methods and the Flask url_map's
     /v1 rules — a new/changed /v1 route without a spec update fails loudly,
     as does a spec entry for a route that no longer exists.

Plus auth/serving tests for the login-gated /api/docs pages.
"""

import os
import re

import pytest
import yaml

import hashview
from hashview.models import Users
from hashview.models import db as _db

SPEC_PATH = os.path.join(os.path.dirname(hashview.__file__), 'api_docs', 'openapi.yaml')

# Methods that can appear as operations in an OpenAPI path item.
_HTTP_METHODS = {'get', 'put', 'post', 'delete', 'options', 'head', 'patch', 'trace'}


def _load_spec():
    with open(SPEC_PATH) as fh:
        return yaml.safe_load(fh)


def _flask_to_openapi(rule):
    """Convert a Werkzeug rule to an OpenAPI path template.

    ``/v1/jobs/<int:job_id>`` -> ``/v1/jobs/{job_id}`` (converter prefixes
    like ``int:`` are dropped; bare ``<name>`` works too).
    """
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule)


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


@pytest.fixture()
def web_user(app):
    user = Users(
        first_name="Docs",
        last_name="Reader",
        email_address="docs@example.test",
        password="x" * 60,
        admin=False,
        api_key="docs-api-key",
    )
    _db.session.add(user)
    _db.session.commit()
    return user


# ---------------------------------------------------------------------------
# Spec validity
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_openapi_spec_is_structurally_valid():
    """The committed spec parses and passes openapi-spec-validator."""
    try:
        from openapi_spec_validator import validate as _validate
    except ImportError:  # older library API
        from openapi_spec_validator import validate_spec as _validate

    spec = _load_spec()
    _validate(spec)  # raises on an invalid document


@pytest.mark.security
def test_openapi_version_matches_package():
    """info.version must track hashview.__version__ (bump both together)."""
    spec = _load_spec()
    assert spec["info"]["version"] == hashview.__version__


@pytest.mark.security
def test_openapi_paths_match_v1_routes(app):
    """Two-way parity between the Flask /v1 url_map and the spec's paths."""
    app_ops = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/v1"):
            continue
        path = _flask_to_openapi(rule.rule)
        for method in (rule.methods or set()) - {"HEAD", "OPTIONS"}:
            app_ops.add((path, method.lower()))

    spec = _load_spec()
    spec_ops = {
        (path, method)
        for path, item in spec["paths"].items()
        for method in item
        if method in _HTTP_METHODS
    }

    missing_from_spec = sorted(app_ops - spec_ops)
    missing_from_app = sorted(spec_ops - app_ops)
    assert app_ops == spec_ops, (
        f"/v1 routes and openapi.yaml have drifted.\n"
        f"In the app but MISSING FROM THE SPEC: {missing_from_spec}\n"
        f"In the spec but NOT A ROUTE: {missing_from_app}"
    )


# ---------------------------------------------------------------------------
# Serving (/api/docs + /api/docs/openapi.yaml)
# ---------------------------------------------------------------------------


@pytest.mark.security
def test_api_docs_routes_require_login(client):
    """Both docs routes are behind the web login (not the API cookie)."""
    for path in ("/api/docs", "/api/docs/openapi.yaml"):
        resp = client.get(path)
        assert 300 <= resp.status_code < 400, path
        assert "/login" in resp.headers.get("Location", ""), path


@pytest.mark.security
def test_api_docs_page_renders_when_logged_in(client, web_user):
    """Authenticated GET /api/docs returns the Swagger UI page."""
    _login(client, web_user)
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "swagger-ui" in html
    # The user has an api_key, so the try-it-out cookie helper is rendered.
    assert "hvDocsAuth" in html


@pytest.mark.security
def test_api_docs_tryitout_helper_requires_api_key(client, web_user):
    """Without an api_key the cookie helper must not be rendered."""
    web_user.api_key = None
    _db.session.commit()
    _login(client, web_user)
    resp = client.get("/api/docs")
    assert resp.status_code == 200
    assert "hvDocsAuth" not in resp.get_data(as_text=True)


@pytest.mark.security
def test_openapi_yaml_served_when_logged_in(client, web_user):
    """Authenticated GET of the spec returns parseable YAML."""
    _login(client, web_user)
    resp = client.get("/api/docs/openapi.yaml")
    assert resp.status_code == 200
    assert "yaml" in (resp.content_type or "")
    served = yaml.safe_load(resp.get_data(as_text=True))
    assert served["openapi"].startswith("3.0")
    assert served["info"]["title"] == "Hashview API"
