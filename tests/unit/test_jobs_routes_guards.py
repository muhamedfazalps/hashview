"""Behavior-pinning tests for the jobs routes guard branches.

Covers jobs_delete (owner cascade + non-owner denied), the
jobs_assign_task / jobs_remove_task round trip (including duplicate-assign
behavior for static vs dynamic wordlists) and the jobs_assigned_hashfile GET
view (own hashfiles listed, another customer's hashfiles not offered).
"""

from hashview.models import (
    Customers,
    Hashfiles,
    Jobs,
    JobTasks,
    Tasks,
    Users,
    Wordlists,
    db,
)


def _admin():
    u = Users(first_name="Ad", last_name="Min", email_address="admin@example.com",
              password="x" * 60, admin=True)
    db.session.add(u)
    db.session.commit()
    return u


def _nonadmin():
    u = Users(first_name="No", last_name="Body", email_address="user@example.com",
              password="x" * 60, admin=False)
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def _make_customer(name="Acme"):
    c = Customers(name=name)
    db.session.add(c)
    db.session.commit()
    return c


def _make_job(owner_id, customer_id, name="job-guards", status="Incomplete"):
    job = Jobs(name=name, status=status, customer_id=customer_id,
               owner_id=owner_id)
    db.session.add(job)
    db.session.commit()
    return job


def _make_wordlist(owner_id, name="wl-jobs", wl_type="static"):
    wl = Wordlists(name=name, owner_id=owner_id, type=wl_type,
                   path=f"control/wordlists/{name}.gz", size=10,
                   checksum="0" * 64)
    db.session.add(wl)
    db.session.commit()
    return wl


def _make_task(owner_id, wl_id, name="task-jobs"):
    task = Tasks(name=name, owner_id=owner_id, wl_id=wl_id, rule_id=None,
                 hc_attackmode=0, loopback=False)
    db.session.add(task)
    db.session.commit()
    return task


# ----------------------------------------------------------------- jobs_delete

def test_jobs_delete_owner_cascades_jobtasks(app, client):
    user = _nonadmin()
    customer = _make_customer()
    job = _make_job(user.id, customer.id)
    wl = _make_wordlist(user.id)
    task = _make_task(user.id, wl.id)
    db.session.add(JobTasks(job_id=job.id, task_id=task.id, status="Not Started"))
    db.session.commit()
    job_id = job.id
    _login(client, user)

    resp = client.post(f"/jobs/delete/{job_id}", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert Jobs.query.get(job_id) is None
    assert JobTasks.query.filter_by(job_id=job_id).count() == 0  # cascaded


def test_jobs_delete_non_owner_denied(app, client):
    admin = _admin()
    user = _nonadmin()
    customer = _make_customer()
    job = _make_job(admin.id, customer.id)
    _login(client, user)

    resp = client.post(f"/jobs/delete/{job.id}", follow_redirects=True)
    assert b"do not have rights to delete this job" in resp.data
    assert Jobs.query.get(job.id) is not None  # NOT deleted


# --------------------------------------------- jobs_assign_task / remove_task

def test_jobs_assign_then_remove_task_round_trip(app, client):
    user = _nonadmin()
    customer = _make_customer()
    job = _make_job(user.id, customer.id)
    wl = _make_wordlist(user.id)
    task = _make_task(user.id, wl.id)
    _login(client, user)

    resp = client.get(f"/jobs/{job.id}/assign_task/{task.id}",
                      follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert JobTasks.query.filter_by(job_id=job.id, task_id=task.id).count() == 1

    resp = client.get(f"/jobs/{job.id}/remove_task/{task.id}",
                      follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert JobTasks.query.filter_by(job_id=job.id, task_id=task.id).count() == 0


def test_jobs_assign_duplicate_static_wordlist_task_rejected(app, client):
    user = _nonadmin()
    customer = _make_customer()
    job = _make_job(user.id, customer.id)
    wl = _make_wordlist(user.id, wl_type="static")
    task = _make_task(user.id, wl.id)
    _login(client, user)

    client.get(f"/jobs/{job.id}/assign_task/{task.id}")
    resp = client.get(f"/jobs/{job.id}/assign_task/{task.id}",
                      follow_redirects=True)
    assert b"Task already assigned to the job." in resp.data
    assert JobTasks.query.filter_by(job_id=job.id, task_id=task.id).count() == 1


def test_jobs_assign_duplicate_dynamic_wordlist_task_allowed(app, client):
    # Tasks whose wordlist is dynamic may be assigned repeatedly (the wordlist
    # content changes between runs).
    user = _nonadmin()
    customer = _make_customer()
    job = _make_job(user.id, customer.id)
    wl = _make_wordlist(user.id, name="wl-dyn", wl_type="dynamic")
    task = _make_task(user.id, wl.id)
    _login(client, user)

    client.get(f"/jobs/{job.id}/assign_task/{task.id}")
    client.get(f"/jobs/{job.id}/assign_task/{task.id}")
    assert JobTasks.query.filter_by(job_id=job.id, task_id=task.id).count() == 2


# ------------------------------------------------------ jobs_assigned_hashfile

def test_jobs_assigned_hashfile_lists_own_customers_hashfiles_only(app, client):
    user = _nonadmin()
    customer = _make_customer("Mine")
    other_customer = _make_customer("Theirs")
    job = _make_job(user.id, customer.id)
    own_hf = Hashfiles(name="own-hashfile.txt", customer_id=customer.id,
                       owner_id=user.id)
    foreign_hf = Hashfiles(name="foreign-hashfile.txt",
                           customer_id=other_customer.id, owner_id=user.id)
    db.session.add_all([own_hf, foreign_hf])
    db.session.commit()
    _login(client, user)

    resp = client.get(f"/jobs/{job.id}/assigned_hashfile/")
    assert resp.status_code == 200
    assert b"own-hashfile.txt" in resp.data           # offered
    assert b"foreign-hashfile.txt" not in resp.data   # other customer's: not offered


def test_jobs_assigned_hashfile_select_existing_sets_job_hashfile(app, client):
    user = _nonadmin()
    customer = _make_customer()
    job = _make_job(user.id, customer.id)
    hf = Hashfiles(name="picked.txt", customer_id=customer.id, owner_id=user.id)
    db.session.add(hf)
    db.session.commit()
    _login(client, user)

    resp = client.post(f"/jobs/{job.id}/assigned_hashfile/",
                       data={"hashfile_id": str(hf.id)},
                       follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert resp.headers["Location"].endswith(f"/jobs/{job.id}/notifications")
    assert int(Jobs.query.get(job.id).hashfile_id) == hf.id
