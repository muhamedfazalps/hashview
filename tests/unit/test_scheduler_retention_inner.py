"""Direct tests for hashview.scheduler._data_retention_cleanup_inner.

The outer data_retention_cleanup wrapper swallows exceptions; these tests call
the inner function directly so failures surface, and pin the three behaviors:
aged rows are purged, the retention_period setting is honored, and a run with
nothing aged is a no-op (including the control/tmp file reaping rules).
"""

import os
import time
from datetime import datetime, timedelta

from hashview.models import (
    Customers,
    Hashes,
    HashfileHashes,
    Hashfiles,
    JobNotifications,
    Jobs,
    JobTasks,
    Settings,
    Tasks,
    Users,
    db,
)
from hashview.scheduler import _data_retention_cleanup_inner


def _admin():
    u = Users(first_name="Ad", last_name="Min", email_address="admin@example.com",
              password="x" * 60, admin=True)
    db.session.add(u)
    db.session.commit()
    return u


def _make_task(owner_id, name="task-retention"):
    task = Tasks(name=name, owner_id=owner_id, wl_id=None, rule_id=None,
                 hc_attackmode=0, loopback=False)
    db.session.add(task)
    db.session.commit()
    return task


def _settings(retention_period=30):
    s = Settings(retention_period=retention_period, max_runtime_jobs=0,
                 max_runtime_tasks=0)
    db.session.add(s)
    db.session.commit()
    return s


def _setup_tmp(app, tmp_path, monkeypatch):
    """The cleanup reaps <current_app.root_path>/control/tmp; point root_path at a
    temp dir with a control/tmp stand-in so the test never touches the real
    control/tmp."""
    monkeypatch.setattr(app, "root_path", str(tmp_path))
    tmp_dir = tmp_path / "control" / "tmp"
    os.makedirs(tmp_dir)
    return tmp_dir


def _run_inner(app):
    _data_retention_cleanup_inner(db, app.extensions["mail"], app.logger)


def test_inner_purges_aged_job_and_hashfile_rows(app, tmp_path, monkeypatch):
    _setup_tmp(app, tmp_path, monkeypatch)
    _settings(retention_period=30)
    admin = _admin()
    cust = Customers(name="Acme")
    db.session.add(cust)
    db.session.commit()

    aged = datetime.utcnow() - timedelta(days=90)

    # aged job with a job task + job notification
    job = Jobs(name="old-job", status="Completed", customer_id=cust.id,
               owner_id=admin.id, created_at=aged)
    db.session.add(job)
    db.session.commit()
    task = _make_task(admin.id, name="task-aged-job")
    db.session.add(JobTasks(job_id=job.id, task_id=task.id, status="Not Started"))
    db.session.add(JobNotifications(owner_id=admin.id, job_id=job.id, method="email"))

    # aged hashfile with an uncracked, unshared hash
    hashfile = Hashfiles(name="old.txt", customer_id=cust.id, owner_id=admin.id,
                         uploaded_at=aged)
    db.session.add(hashfile)
    db.session.commit()
    h = Hashes(sub_ciphertext="a" * 32, ciphertext="b" * 32, hash_type=1000,
               cracked=False)
    db.session.add(h)
    db.session.commit()
    db.session.add(HashfileHashes(hash_id=h.id, hashfile_id=hashfile.id))
    db.session.commit()
    job_id, hashfile_id, hash_id = job.id, hashfile.id, h.id

    _run_inner(app)
    db.session.expire_all()

    assert Jobs.query.get(job_id) is None
    assert JobTasks.query.filter_by(job_id=job_id).count() == 0
    assert JobNotifications.query.filter_by(job_id=job_id).count() == 0
    assert Hashfiles.query.get(hashfile_id) is None
    assert HashfileHashes.query.filter_by(hashfile_id=hashfile_id).count() == 0
    assert Hashes.query.get(hash_id) is None  # uncracked + unshared -> purged


def test_inner_respects_retention_period_setting(app, tmp_path, monkeypatch):
    _setup_tmp(app, tmp_path, monkeypatch)
    _settings(retention_period=100)  # window wider than the rows' age
    admin = _admin()
    cust = Customers(name="Acme")
    db.session.add(cust)
    db.session.commit()

    aged_90 = datetime.utcnow() - timedelta(days=90)
    job = Jobs(name="90day-job", status="Completed", customer_id=cust.id,
               owner_id=admin.id, created_at=aged_90)
    hashfile = Hashfiles(name="90day.txt", customer_id=cust.id,
                         owner_id=admin.id, uploaded_at=aged_90)
    db.session.add_all([job, hashfile])
    db.session.commit()
    job_id, hashfile_id = job.id, hashfile.id

    _run_inner(app)
    db.session.expire_all()

    # 90 days old but the retention window is 100 days -> kept
    assert Jobs.query.get(job_id) is not None
    assert Hashfiles.query.get(hashfile_id) is not None


def test_inner_noop_when_nothing_aged(app, tmp_path, monkeypatch):
    tmp_dir = _setup_tmp(app, tmp_path, monkeypatch)
    _settings(retention_period=30)
    admin = _admin()
    cust = Customers(name="Acme")
    db.session.add(cust)
    db.session.commit()

    job = Jobs(name="fresh-job", status="Completed", customer_id=cust.id,
               owner_id=admin.id, created_at=datetime.utcnow())
    hashfile = Hashfiles(name="fresh.txt", customer_id=cust.id,
                         owner_id=admin.id, uploaded_at=datetime.utcnow())
    db.session.add_all([job, hashfile])
    db.session.commit()
    job_id, hashfile_id = job.id, hashfile.id

    fresh_file = tmp_dir / "fresh-upload"
    fresh_file.write_text("data")

    _run_inner(app)
    db.session.expire_all()

    assert Jobs.query.get(job_id) is not None
    assert Hashfiles.query.get(hashfile_id) is not None
    assert fresh_file.exists()  # within retention window -> left alone


def test_inner_reaps_tmp_files_by_age_and_keeps_gitignore(app, tmp_path, monkeypatch):
    tmp_dir = _setup_tmp(app, tmp_path, monkeypatch)
    _settings(retention_period=30)

    old_file = tmp_dir / "stale-upload"
    old_file.write_text("old")
    stale = time.time() - 40 * 86400
    os.utime(old_file, (stale, stale))

    gitignore = tmp_dir / ".gitignore"
    gitignore.write_text("*")
    os.utime(gitignore, (stale, stale))

    # one-time DB backups are reaped after an hour regardless of the
    # (day-granular) retention period
    backup = tmp_dir / "backup.sql.gz.enc"
    backup.write_text("enc")
    two_hours_ago = time.time() - 7200
    os.utime(backup, (two_hours_ago, two_hours_ago))

    _run_inner(app)

    assert not old_file.exists()       # past retention window -> removed
    assert gitignore.exists()          # always kept
    assert not backup.exists()         # backups reaped within the hour


def test_inner_purges_job_referencing_aged_hashfile(app, tmp_path, monkeypatch):
    # A *fresh* job that references an aged hashfile is deleted along with it.
    _setup_tmp(app, tmp_path, monkeypatch)
    _settings(retention_period=30)
    admin = _admin()
    cust = Customers(name="Acme")
    db.session.add(cust)
    db.session.commit()

    hashfile = Hashfiles(name="aged.txt", customer_id=cust.id, owner_id=admin.id,
                         uploaded_at=datetime.utcnow() - timedelta(days=90))
    db.session.add(hashfile)
    db.session.commit()
    job = Jobs(name="fresh-but-doomed", status="Completed", customer_id=cust.id,
               owner_id=admin.id, created_at=datetime.utcnow(),
               hashfile_id=hashfile.id)
    db.session.add(job)
    db.session.commit()
    task = _make_task(admin.id, name="task-doomed-job")
    db.session.add(JobTasks(job_id=job.id, task_id=task.id, status="Not Started"))
    db.session.add(JobNotifications(owner_id=admin.id, job_id=job.id, method="email"))
    db.session.commit()
    job_id, hashfile_id = job.id, hashfile.id

    _run_inner(app)
    db.session.expire_all()

    assert Hashfiles.query.get(hashfile_id) is None
    assert Jobs.query.get(job_id) is None  # cascaded via the hashfile branch
    assert JobTasks.query.filter_by(job_id=job_id).count() == 0
    assert JobNotifications.query.filter_by(job_id=job_id).count() == 0


def test_outer_wrapper_swallows_failures(app, tmp_path, monkeypatch):
    # No Settings row -> the inner function raises; the scheduled-job wrapper
    # must swallow it (log + continue) rather than crash the scheduler thread.
    from hashview.scheduler import data_retention_cleanup
    _setup_tmp(app, tmp_path, monkeypatch)
    data_retention_cleanup(app)  # must not raise
