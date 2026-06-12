"""Regression tests for task_groups routes + form (function-coverage batch)."""

import json

import pytest
from wtforms.validators import ValidationError

from hashview.models import TaskGroups, Tasks, db
from hashview.task_groups.forms import TaskGroupsForm
from tests.unit.helpers import login, make_admin


def _task(owner, name="t"):
    t = Tasks(name=name, hc_attackmode=0, owner_id=owner.id)
    db.session.add(t)
    db.session.commit()
    return t


def _group(owner, task_ids, name="grp"):
    tg = TaskGroups(name=name, owner_id=owner.id, tasks=str(list(task_ids)))
    db.session.add(tg)
    db.session.commit()
    return tg


def test_task_groups_list_renders(app, client):
    admin = make_admin()
    login(client, admin)
    t = _task(admin, "memberA")
    _group(admin, [t.id], name="GroupShown")
    resp = client.get("/task_groups")
    assert resp.status_code == 200
    assert b"GroupShown" in resp.data


def test_task_groups_add_with_task_ids_creates_group(app, client):
    admin = make_admin()
    login(client, admin)
    t1, t2 = _task(admin, "a"), _task(admin, "b")
    resp = client.post("/task_groups/add", data={
        "name": "NewGroup", "task_ids": f"{t1.id},{t2.id}", "submit": "Create",
    }, follow_redirects=False)
    assert resp.status_code in (301, 302)
    tg = TaskGroups.query.filter_by(name="NewGroup").first()
    assert tg is not None
    assert json.loads(tg.tasks) == [t1.id, t2.id]


def test_assigned_tasks_renders(app, client):
    admin = make_admin()
    login(client, admin)
    t = _task(admin, "m")
    tg = _group(admin, [t.id])
    resp = client.get(f"/task_groups/assigned_tasks/{tg.id}")
    assert resp.status_code == 200


def test_assigned_tasks_add_task_appends(app, client):
    admin = make_admin()
    login(client, admin)
    t1, t2 = _task(admin, "a"), _task(admin, "b")
    tg = _group(admin, [t1.id])
    resp = client.get(f"/task_groups/assigned_tasks/{tg.id}/add_task/{t2.id}",
                      follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert json.loads(TaskGroups.query.get(tg.id).tasks) == [t1.id, t2.id]


def test_assigned_tasks_promote_task_moves_up(app, client):
    admin = make_admin()
    login(client, admin)
    t1, t2 = _task(admin, "a"), _task(admin, "b")
    tg = _group(admin, [t1.id, t2.id])
    resp = client.get(f"/task_groups/assigned_tasks/{tg.id}/promote_task/{t2.id}",
                      follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert json.loads(TaskGroups.query.get(tg.id).tasks) == [t2.id, t1.id]


def test_assigned_tasks_promote_top_is_noop(app, client):
    admin = make_admin()
    login(client, admin)
    t1, t2 = _task(admin, "a"), _task(admin, "b")
    tg = _group(admin, [t1.id, t2.id])
    client.get(f"/task_groups/assigned_tasks/{tg.id}/promote_task/{t1.id}",
               follow_redirects=False)
    assert json.loads(TaskGroups.query.get(tg.id).tasks) == [t1.id, t2.id]


def test_assigned_tasks_demote_task_moves_down(app, client):
    admin = make_admin()
    login(client, admin)
    t1, t2 = _task(admin, "a"), _task(admin, "b")
    tg = _group(admin, [t1.id, t2.id])
    resp = client.get(f"/task_groups/assigned_tasks/{tg.id}/demote_task/{t1.id}",
                      follow_redirects=False)
    assert resp.status_code in (301, 302)
    assert json.loads(TaskGroups.query.get(tg.id).tasks) == [t2.id, t1.id]


def test_validate_task_rejects_duplicate(app):
    admin = make_admin()
    _task(admin, "TakenName")
    form = TaskGroupsForm()

    class _Field:
        data = "TakenName"

    with pytest.raises(ValidationError):
        form.validate_task(_Field())
