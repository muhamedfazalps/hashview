"""Behavior-pinning tests for the tasks routes guard branches.

Covers tasks_delete (job / task-group association blocks, ownership check,
happy path), task_edit (job-association block, ownership check, successful
edit) and tasks_add (attack mode 0 with and without a rule).
"""

from hashview.models import JobTasks, Rules, TaskGroups, Tasks, Users, Wordlists, db


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


def _make_wordlist(owner_id, name="wl-guards"):
    wl = Wordlists(name=name, owner_id=owner_id, type="static",
                   path="control/wordlists/wl-guards.gz", size=10,
                   checksum="0" * 64)
    db.session.add(wl)
    db.session.commit()
    return wl


def _make_rule(owner_id, name="rule-guards"):
    rule = Rules(name=name, owner_id=owner_id, path="control/rules/rg.rule",
                 checksum="1" * 64, size=1)
    db.session.add(rule)
    db.session.commit()
    return rule


def _make_task(owner_id, name="task-guards", wl_id=None):
    task = Tasks(name=name, owner_id=owner_id, wl_id=wl_id, rule_id=None,
                 hc_attackmode=0, loopback=False)
    db.session.add(task)
    db.session.commit()
    return task


# ---------------------------------------------------------------- tasks_delete

def test_tasks_delete_blocked_when_assigned_to_job(app, client):
    admin = _admin()
    _login(client, admin)
    task = _make_task(admin.id)
    db.session.add(JobTasks(job_id=1, task_id=task.id, status="Not Started"))
    db.session.commit()

    resp = client.post(f"/tasks/delete/{task.id}", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert Tasks.query.get(task.id) is not None  # NOT deleted

    follow = client.post(f"/tasks/delete/{task.id}", follow_redirects=True)
    assert b"associated to one or more jobs" in follow.data


def test_tasks_delete_blocked_when_in_task_group(app, client):
    admin = _admin()
    _login(client, admin)
    task = _make_task(admin.id)
    db.session.add(TaskGroups(name="tg", owner_id=admin.id, tasks=f'["{task.id}"]'))
    db.session.commit()

    resp = client.post(f"/tasks/delete/{task.id}", follow_redirects=True)
    assert b"associated to one or more Task Groups" in resp.data
    assert Tasks.query.get(task.id) is not None  # NOT deleted


def test_tasks_delete_non_owner_non_admin_denied(app, client):
    admin = _admin()
    user = _nonadmin()
    task = _make_task(admin.id)
    _login(client, user)

    resp = client.post(f"/tasks/delete/{task.id}", follow_redirects=True)
    assert b"unauthorized to delete this task" in resp.data
    assert Tasks.query.get(task.id) is not None  # NOT deleted


def test_tasks_delete_owner_happy_path(app, client):
    user = _nonadmin()
    task = _make_task(user.id)
    _login(client, user)

    resp = client.post(f"/tasks/delete/{task.id}", follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert Tasks.query.get(task.id) is None  # deleted


# ------------------------------------------------------------------ task_edit

def test_task_edit_blocked_when_assigned_to_job(app, client):
    admin = _admin()
    _login(client, admin)
    task = _make_task(admin.id, name="before-edit")
    db.session.add(JobTasks(job_id=1, task_id=task.id, status="Not Started"))
    db.session.commit()

    resp = client.post(f"/tasks/edit/{task.id}", data={"name": "after-edit"},
                       follow_redirects=True)
    assert b"currently associated to one or more jobs" in resp.data
    assert Tasks.query.get(task.id).name == "before-edit"  # unchanged


def test_task_edit_non_owner_denied(app, client):
    admin = _admin()
    user = _nonadmin()
    task = _make_task(admin.id, name="owned-by-admin")
    _login(client, user)

    resp = client.post(f"/tasks/edit/{task.id}", data={"name": "hijacked"},
                       follow_redirects=True)
    assert b"unauthorized to edit this task" in resp.data
    assert Tasks.query.get(task.id).name == "owned-by-admin"  # unchanged


def test_task_edit_owner_successful_post(app, client):
    user = _nonadmin()
    _login(client, user)
    wl = _make_wordlist(user.id)
    task = _make_task(user.id, name="old-name", wl_id=wl.id)

    resp = client.post(
        f"/tasks/edit/{task.id}",
        data={
            "name": "new-name",
            "hc_attackmode": "0",
            "wl_id": str(wl.id),
            "wl_id_2": str(wl.id),  # hidden select still submits a value in the browser
            "rule_id": "None",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (301, 302)
    edited = Tasks.query.get(task.id)
    assert edited.name == "new-name"
    assert edited.wl_id == wl.id
    assert edited.rule_id is None  # 'None' sentinel normalized to NULL
    assert edited.hc_attackmode == 0


# ------------------------------------------------------------------ tasks_add

def test_tasks_add_mode0_with_rule(app, client):
    admin = _admin()
    _login(client, admin)
    wl = _make_wordlist(admin.id)
    rule = _make_rule(admin.id)

    resp = client.post(
        "/tasks/add",
        data={
            "name": "dict-with-rule",
            "hc_attackmode": "0",
            "wl_id": str(wl.id),
            "wl_id_2": str(wl.id),
            "rule_id": str(rule.id),
        },
        follow_redirects=False,
    )
    assert resp.status_code in (301, 302)
    task = Tasks.query.filter_by(name="dict-with-rule").first()
    assert task is not None
    assert task.hc_attackmode == 0
    assert task.owner_id == admin.id
    assert task.wl_id == wl.id
    assert str(task.rule_id) == str(rule.id)


def test_tasks_add_mode0_rule_none_sentinel(app, client):
    admin = _admin()
    _login(client, admin)
    wl = _make_wordlist(admin.id)

    resp = client.post(
        "/tasks/add",
        data={
            "name": "dict-no-rule",
            "hc_attackmode": "0",
            "wl_id": str(wl.id),
            "wl_id_2": str(wl.id),
            "rule_id": "None",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (301, 302)
    task = Tasks.query.filter_by(name="dict-no-rule").first()
    assert task is not None
    assert task.rule_id is None  # sentinel stored as NULL, not the string 'None'
    assert task.wl_id == wl.id
