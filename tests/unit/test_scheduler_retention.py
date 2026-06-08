"""Regression test for the hourly DATA_RETENTION scheduled job.

`data_retention_cleanup` used to call `db.init_app(app)` on every run, which
raises in Flask-SQLAlchemy 3.x ("instance has already been registered") and
aborted the cleanup before it did anything. This asserts the job now runs to
completion: it must not raise, it must purge jobs older than the retention
window, and it must leave recent jobs intact.
"""
import os
from datetime import datetime, timedelta

import pytest

from hashview.models import Customers, Jobs, Settings, Users
from hashview.models import db as _db
from hashview.scheduler import data_retention_cleanup


@pytest.mark.security
def test_data_retention_cleanup_runs_and_purges_stale_jobs(app, tmp_path, monkeypatch):
    # The cleanup reaps control/tmp via the relative path 'hashview/control/tmp';
    # chdir to a temp dir (with an empty stand-in) so the test never touches the
    # real control/tmp.
    monkeypatch.chdir(tmp_path)
    os.makedirs(tmp_path / 'hashview' / 'control' / 'tmp')

    _db.session.add(Settings(retention_period=30, max_runtime_jobs=0, max_runtime_tasks=0))
    cust = Customers(name='Acme')
    user = Users(first_name='A', last_name='B', email_address='a@e.test',
                 password='x' * 60, admin=True)
    _db.session.add_all([cust, user])
    _db.session.commit()

    old = Jobs(name='old-job', status='Completed', customer_id=cust.id, owner_id=user.id,
               created_at=datetime.utcnow() - timedelta(days=90))
    fresh = Jobs(name='fresh-job', status='Completed', customer_id=cust.id, owner_id=user.id,
                 created_at=datetime.utcnow())
    _db.session.add_all([old, fresh])
    _db.session.commit()
    old_id, fresh_id = old.id, fresh.id

    # Must not raise (the regression) and must reach the cleanup body.
    data_retention_cleanup(app)

    # data_retention_cleanup commits in its own (nested) app context, so drop the
    # outer session's identity map and read the DB directly for the assertions.
    _db.session.expire_all()
    assert Jobs.query.filter_by(id=old_id).first() is None       # past 30-day window -> purged
    assert Jobs.query.filter_by(id=fresh_id).first() is not None  # recent -> kept
