import pytest
from flask import Response

from hashview import create_app
from hashview.models import Rules, Users, db


@pytest.mark.security
def test_rules_download_command_injection_poc(monkeypatch):
    """
    PoC: show that a crafted Rules.path is rejected by the allow-list.
    """
    app = create_app(
        testing=True,
        config_overrides={
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "WTF_CSRF_ENABLED": False,
            "HASHVIEW_SKIP_SETUP": True,
            "HASHVIEW_SKIP_GUI_SETUP": True,
            "HASHVIEW_DISABLE_SCHEDULER": True,
        },
    )

    with app.app_context():
        db.create_all()
        user = Users(
            first_name="Test",
            last_name="User",
            email_address="test@example.com",
            password="x" * 60,
            admin=True,
            api_key="test-api-key",
        )
        db.session.add(user)
        db.session.commit()

        # includes `whoami` to show the injection payload is rejected
        injected_path = "evil; whoami; #.rule"
        rule = Rules(
            name="evil-rule",
            owner_id=user.id,
            path=injected_path,
            size=1,
            checksum="0" * 64,
        )
        db.session.add(rule)
        db.session.commit()

        import hashview.api.routes as api_routes

        monkeypatch.setattr(
            api_routes,
            "send_from_directory",
            lambda *args, **kwargs: Response("ok", status=200),
        )
        monkeypatch.setattr(api_routes.subprocess, "run", lambda *a, **k: None)

        client = app.test_client()
        client.set_cookie("uuid", "test-api-key")
        resp = client.get(f"/v1/rules/{rule.id}")
        assert resp.status_code == 400


@pytest.mark.security
def test_rules_download_uses_subprocess_run_list_args(monkeypatch, tmp_path):
    app = create_app(
        testing=True,
        config_overrides={
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "WTF_CSRF_ENABLED": False,
            "HASHVIEW_SKIP_SETUP": True,
            "HASHVIEW_SKIP_GUI_SETUP": True,
            "HASHVIEW_DISABLE_SCHEDULER": True,
        },
    )

    with app.app_context():
        db.create_all()
        user = Users(
            first_name="Test",
            last_name="User",
            email_address="test@example.com",
            password="x" * 60,
            admin=True,
            api_key="test-api-key",
        )
        db.session.add(user)
        db.session.commit()

        rule = Rules(
            name="safe-rule",
            owner_id=user.id,
            path="safe.rule",
            size=1,
            checksum="0" * 64,
        )
        db.session.add(rule)
        db.session.commit()

        captured = {}

        def fake_run(args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            return None

        import hashview.api.routes as api_routes

        monkeypatch.setattr(api_routes.subprocess, "run", fake_run)
        monkeypatch.setattr(
            api_routes,
            "send_from_directory",
            lambda *args, **kwargs: Response("ok", status=200),
        )

        client = app.test_client()
        client.set_cookie("uuid", "test-api-key")
        resp = client.get(f"/v1/rules/{rule.id}")

        assert resp.status_code == 200
        assert isinstance(captured["args"], list)
        assert captured["args"][:3] == ["gzip", "-9", "-k"]
        assert captured["kwargs"].get("check") is True


@pytest.mark.security
def test_rules_download_rejects_invalid_extension(monkeypatch):
    app = create_app(
        testing=True,
        config_overrides={
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "SQLALCHEMY_TRACK_MODIFICATIONS": False,
            "WTF_CSRF_ENABLED": False,
            "HASHVIEW_SKIP_SETUP": True,
            "HASHVIEW_SKIP_GUI_SETUP": True,
            "HASHVIEW_DISABLE_SCHEDULER": True,
        },
    )

    with app.app_context():
        db.create_all()
        user = Users(
            first_name="Test",
            last_name="User",
            email_address="test@example.com",
            password="x" * 60,
            admin=True,
            api_key="test-api-key",
        )
        db.session.add(user)
        db.session.commit()

        rule = Rules(
            name="bad-rule",
            owner_id=user.id,
            path="bad.exe",
            size=1,
            checksum="0" * 64,
        )
        db.session.add(rule)
        db.session.commit()

        import hashview.api.routes as api_routes

        monkeypatch.setattr(
            api_routes,
            "send_from_directory",
            lambda *args, **kwargs: Response("ok", status=200),
        )
        monkeypatch.setattr(api_routes.subprocess, "run", lambda *a, **k: None)

        client = app.test_client()
        client.set_cookie("uuid", "test-api-key")
        resp = client.get(f"/v1/rules/{rule.id}")
        assert resp.status_code == 400
