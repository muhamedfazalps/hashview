"""Regression tests for main routes (function-coverage batch: main)."""

from datetime import datetime

from hashview.models import (
    Customers,
    Hashes,
    HashfileHashes,
    Jobs,
    JobTasks,
    Tasks,
    db,
)
from tests.unit.helpers import login, make_admin, make_customer


def test_home_renders_with_recovery_feed(app, client):
    # Seeding a cracked hash with a username drives the recovery-feed loop,
    # which exercises the nested _hexdec helper.
    admin = make_admin()
    login(client, admin)
    h = Hashes(sub_ciphertext="0" * 8, ciphertext="abc", hash_type=1000,
               cracked=True, plaintext="Summer2024",
               recovered_at=datetime(2024, 1, 2), recovered_by=admin.id)
    db.session.add(h)
    db.session.commit()
    db.session.add(HashfileHashes(hash_id=h.id, hashfile_id=1, username="alice"))
    db.session.commit()
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Summer2024" in resp.data


def test_stop_job_task_cancels(app, client):
    from hashview.models import Hashfiles
    admin = make_admin()
    login(client, admin)
    cust = make_customer()
    hf = Hashfiles(name="hf", customer_id=cust.id, owner_id=admin.id, runtime=0)
    db.session.add(hf)
    db.session.commit()
    job = Jobs(name="j", status="Running", customer_id=cust.id, owner_id=admin.id,
               hashfile_id=hf.id)
    db.session.add(job)
    db.session.commit()
    # update_job_task_status accrues runtime from started_at -> now, so a
    # running task needs a started_at.
    jt = JobTasks(job_id=job.id, task_id=1, status="Running", priority=3,
                  started_at=datetime.utcnow())
    db.session.add(jt)
    db.session.commit()
    resp = client.get(f"/job_task/stop/{jt.id}", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert JobTasks.query.get(jt.id).status == "Canceled"
