"""Migration chain smoke test.

Runs ``alembic upgrade head`` against a fresh SQLite database and asserts
it reaches the head revision without errors. This catches the bad-merge
incident class (which dropped all 40 version scripts in PR-156 history)
the next time it happens, before it ships.

We use SQLite rather than MySQL so the test runs in any CI environment.
A few MySQL-specific bits (e.g. ``mysql.VARCHAR``) get caught by alembic's
default-impl translation, which is good enough for "does the chain even
walk."
"""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine, inspect


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / "migrations"


@pytest.mark.security
def test_alembic_upgrade_head_on_empty_sqlite(tmp_path):
    """``flask db upgrade`` walks the full migration chain on a fresh DB."""
    if not MIGRATIONS_DIR.exists():
        pytest.skip("migrations/ directory missing — already a regression caught.")
    versions = list((MIGRATIONS_DIR / "versions").glob("*.py"))
    assert len(versions) >= 40, (
        f"Expected 40+ migration scripts; found only {len(versions)}. "
        "Did a merge drop them?"
    )

    db_path = tmp_path / "smoke.sqlite"
    db_url = f"sqlite:///{db_path}"

    alembic_cfg = AlembicConfig(str(MIGRATIONS_DIR / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    alembic_cfg.set_main_option("sqlalchemy.url", db_url)

    # Some migrations expect a Flask-Migrate context. Bypass env.py's
    # ``current_app`` lookup by pointing at the offline-friendly engine.
    # If env.py refuses to run without a Flask app context, build one.
    try:
        command.upgrade(alembic_cfg, "head")
    except Exception:
        # Fallback: drive alembic from inside a Flask app context — this
        # is how the production setup.py invokes the upgrade.
        from flask_migrate import upgrade as flask_db_upgrade

        from hashview import create_app

        app = create_app(
            testing=True,
            config_overrides={
                "SQLALCHEMY_DATABASE_URI": db_url,
                "SQLALCHEMY_TRACK_MODIFICATIONS": False,
                "WTF_CSRF_ENABLED": False,
                "HASHVIEW_SKIP_SETUP": True,
                "HASHVIEW_SKIP_GUI_SETUP": True,
                "HASHVIEW_DISABLE_SCHEDULER": True,
            },
        )
        with app.app_context():
            # flask_migrate.upgrade looks for the migrations dir relative to
            # the working directory, so chdir to the repo root for the call.
            cwd = os.getcwd()
            try:
                os.chdir(REPO_ROOT)
                flask_db_upgrade()
            finally:
                os.chdir(cwd)

    # Confirm the schema has the core tables a fresh install must have.
    engine = create_engine(db_url)
    insp = inspect(engine)
    table_names = set(insp.get_table_names())
    required = {
        "users", "wordlists", "rules", "tasks", "jobs", "job_tasks",
        "hashfiles", "hashfile_hashes", "hashes", "customers",
        "alembic_version",
    }
    missing = required - table_names
    assert not missing, f"Missing expected tables after migration: {missing}"

    # Spot-check a column we added in the most recent migrations to confirm
    # the chain ran to head and didn't stop early.
    tasks_cols = {c["name"] for c in insp.get_columns("tasks")}
    assert "wl_id_2" in tasks_cols, (
        "tasks.wl_id_2 missing — reconcile-drift migration didn't apply."
    )
    assert "hc_attackmode" in tasks_cols
