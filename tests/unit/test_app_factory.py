"""Regression tests for app-factory hooks + jinja helpers
(function-coverage batch: __init__)."""

import hashview
from hashview.models import Agents, db
from tests.unit.helpers import login, make_admin


def test_jinja_hex_decode_is_passthrough():
    # Stored values are now plain UTF-8 text; the filter just returns them.
    assert hashview.jinja_hex_decode("alice") == "alice"
    assert hashview.jinja_hex_decode("$HEX[6869]") == "$HEX[6869]"


def test_jinja_hex_decode_registered_as_filter(app):
    assert "jinja_hex_decode" in app.jinja_env.filters


def test_do_gui_setup_allows_static(app):
    # A request for a static asset must short-circuit (return None) without a
    # setup redirect.
    with app.test_request_context("/static/css/x.css"):
        assert hashview.do_gui_setup_if_needed() is None


def test_setup_defaults_if_needed_runs_without_raising(app):
    # Each step is wrapped in try/except and logged; calling it must complete
    # (returns None) on the in-memory app.
    with app.app_context():
        assert hashview.setup_defaults_if_needed() is None


def test_nav_count_helpers_run_when_rendering_with_agents(app, client):
    # The _connected/_state/_hps helpers live inside the inject_nav_counts
    # context processor and execute per agent when any template renders. Seed an
    # agent with a benchmark + recent check-in and render an authenticated page.
    admin = make_admin()
    login(client, admin)
    db.session.add(Agents(name="navagent", src_ip="127.0.0.1", uuid="nav-uuid",
                          status="Working", benchmark="284.6 GH/s",
                          last_checkin=__import__("datetime").datetime.utcnow()))
    db.session.commit()
    resp = client.get("/jobs")
    assert resp.status_code == 200
