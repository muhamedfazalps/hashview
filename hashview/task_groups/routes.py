"""Flask routes to handle Task Groups"""
import json
from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from hashview.task_groups.forms import TaskGroupsForm
from hashview.models import Tasks, TaskGroups, Users, Hashes
from hashview.models import db


task_groups = Blueprint('task_groups', __name__)

@task_groups.route("/task_groups", methods=['GET', 'POST'])
@login_required
def task_groups_list():
    """Function to list task groups"""
    task_groups = TaskGroups.query.all()
    tasks = Tasks.query.all()
    users = Users.query.all()

    tasks_by_id = {t.id: t for t in tasks}
    user_names = {u.id: (((u.first_name or '') + ' ' + (u.last_name or '')).strip() or '—')
                  for u in users}

    # Historical hits (recovered passwords) per task, summed across each group's tasks.
    recovered_by_task = {
        row.task_id: row.recovered_count
        for row in Hashes.query.with_entities(
            Hashes.task_id, db.func.count(Hashes.id).label('recovered_count')
        ).filter(Hashes.cracked == '1').group_by(Hashes.task_id).all()
    }

    group_tasks = {}   # group.id -> ordered list of Task objects
    group_hits = {}    # group.id -> summed historical hits
    group_owner = {}   # group.id -> owner display name
    for group in task_groups:
        try:
            ids = json.loads(group.tasks) if group.tasks else []
        except (ValueError, TypeError):
            ids = []
        ordered = [tasks_by_id[i] for i in ids if i in tasks_by_id]
        group_tasks[group.id] = ordered
        group_hits[group.id] = sum(recovered_by_task.get(t.id, 0) for t in ordered)
        group_owner[group.id] = user_names.get(group.owner_id, '—')

    return render_template('task_groups.html.j2', title='Task Groups', task_groups=task_groups,
                           users=users, tasks=tasks, group_tasks=group_tasks,
                           group_hits=group_hits, group_owner=group_owner,
                           task_group_form=TaskGroupsForm())

@task_groups.route("/task_groups/add", methods=['GET', 'POST'])
@login_required
def task_groups_add():
    """Function to add task group"""

    task_group_form = TaskGroupsForm()
    tasks = Tasks.query
    if task_group_form.validate_on_submit():
        # The "New group" modal posts an ordered, comma-separated list of task ids in
        # `task_ids`; the legacy standalone page does not send that field.
        if 'task_ids' in request.form:
            valid_ids = {t.id for t in Tasks.query.all()}
            ordered = []
            for piece in request.form.get('task_ids', '').split(','):
                piece = piece.strip()
                if piece.isdigit():
                    tid = int(piece)
                    if tid in valid_ids and tid not in ordered:
                        ordered.append(tid)
            task_group = TaskGroups(name=task_group_form.name.data, owner_id=current_user.id, tasks=str(ordered))
            db.session.add(task_group)
            db.session.commit()
            flash(f'Task group {task_group_form.name.data} created!', 'success')
            return redirect(url_for('task_groups.task_groups_list'))
        # Legacy flow: create an empty group then go to the assign-tasks page.
        task_group = TaskGroups(name=task_group_form.name.data, owner_id=current_user.id, tasks=str([]))
        db.session.add(task_group)
        db.session.commit()
        flash(f'Task {task_group_form.name.data} created!', 'success')
        return redirect("assigned_tasks/"+str(task_group.id))
    return render_template('task_groups_add.html.j2', title='Tasks Add', tasks=tasks, task_group_form=task_group_form)

@task_groups.route("/task_groups/edit", methods=['POST'])
@login_required
def task_groups_edit():
    """Update a task group's name and ordered task list (from the edit modal)."""
    task_group = TaskGroups.query.get_or_404(request.form.get('group_id', type=int))
    if not (current_user.admin or task_group.owner_id == current_user.id):
        abort(403)
    task_group_form = TaskGroupsForm()
    if task_group_form.validate_on_submit():
        valid_ids = {t.id for t in Tasks.query.all()}
        ordered = []
        for piece in request.form.get('task_ids', '').split(','):
            piece = piece.strip()
            if piece.isdigit():
                tid = int(piece)
                if tid in valid_ids and tid not in ordered:
                    ordered.append(tid)
        task_group.name = task_group_form.name.data
        task_group.tasks = str(ordered)
        db.session.commit()
        flash(f'Task group {task_group_form.name.data} updated!', 'success')
    else:
        flash('Could not update task group.', 'danger')
    return redirect(url_for('task_groups.task_groups_list'))

@task_groups.route("/task_groups/assigned_tasks/<int:task_group_id>", methods=['GET', 'POST'])
@login_required
def task_groups_assigned_tasks(task_group_id):
    """Function to list assigned tasks for task group"""

    task_group = TaskGroups.query.get(task_group_id)
    tasks = Tasks.query
    task_group_tasks = json.loads(task_group.tasks)
    return render_template('task_groups_assigntask.html.j2', title='Task Group: Assign Tasks', task_group=task_group, tasks=tasks, task_group_tasks=task_group_tasks)

@task_groups.route("/task_groups/assigned_tasks/<int:task_group_id>/add_task/<int:task_id>", methods=['GET'])
@login_required
def task_groups_assigned_tasks_add_task(task_group_id, task_id):
    """Function to assign task to task group"""

    task_group = TaskGroups.query.get(task_group_id)
    task_group_tasks = json.loads(task_group.tasks)
    task_group_tasks.append(task_id)
    task_group.tasks = str(task_group_tasks)
    db.session.commit()
    return redirect("/task_groups/assigned_tasks/"+str(task_group.id))

@task_groups.route("/task_groups/assigned_tasks/<int:task_group_id>/remove_task/<int:task_id>", methods=['GET'])
@login_required
def task_groups_assigned_tasks_remove_task(task_group_id, task_id):
    """Function to remove task to task group"""

    task_group = TaskGroups.query.get(task_group_id)
    task_group_tasks = json.loads(task_group.tasks)
    task_group_tasks.remove(task_id)
    task_group.tasks = str(task_group_tasks)
    db.session.commit()
    return redirect("/task_groups/assigned_tasks/"+str(task_group.id))

@task_groups.route("/task_groups/assigned_tasks/<int:task_group_id>/promote_task/<int:task_id>", methods=['GET'])
@login_required
def task_groups_assigned_tasks_promote_task(task_group_id, task_id):
    """Function to move assigned task up higher in queue on task group"""

    task_group = TaskGroups.query.get(task_group_id)
    task_group_tasks = json.loads(task_group.tasks)
    if task_group_tasks[0] == task_id:
        # Cant promote further
        return redirect("/task_groups/assigned_tasks/"+str(task_group.id))
    else:
        new_task_group_tasks = []
        # Creating manual index since for loop doesnt allow you to modify the itterator value
        index = 0
        while index < len(task_group_tasks):
            if index+1 < len(task_group_tasks):
                if task_group_tasks[index+1] == task_id:
                    new_task_group_tasks.append(task_id)
                    new_task_group_tasks.append(task_group_tasks[index])
                    index = index + 1
                else:
                    new_task_group_tasks.append(task_group_tasks[index])
            else:
                new_task_group_tasks.append(task_group_tasks[index])
            index+=1
    task_group.tasks = str(new_task_group_tasks)
    db.session.commit()
    return redirect("/task_groups/assigned_tasks/"+str(task_group.id))

@task_groups.route("/task_groups/assigned_tasks/<int:task_group_id>/demote_task/<int:task_id>", methods=['GET'])
@login_required
def task_groups_assigned_tasks_demote_task(task_group_id, task_id):
    """Function to move assigned task up lower in queue on task group"""

    task_group = TaskGroups.query.get(task_group_id)
    task_group_tasks = json.loads(task_group.tasks)
    if task_group_tasks[-1] == task_id:
        # Cant demote further
        return redirect("/task_groups/assigned_tasks/"+str(task_group.id))
    else:
        new_task_group_tasks = []
        # Creating manual index since for loop doesnt allow you to modify the itterator value
        index = 0
        while index < len(task_group_tasks):
            if index+1 < len(task_group_tasks):
                if task_group_tasks[index] == task_id:
                    new_task_group_tasks.append(task_group_tasks[index+1])
                    new_task_group_tasks.append(task_id)
                    index = index + 1
                else:
                    new_task_group_tasks.append(task_group_tasks[index])
            else:
                new_task_group_tasks.append(task_group_tasks[index])
            index+=1
    task_group.tasks = str(new_task_group_tasks)
    db.session.commit()
    return redirect("/task_groups/assigned_tasks/"+str(task_group.id))

@task_groups.route("/task_groups/delete/<int:task_group_id>", methods=['POST'])
@login_required
def task_groups_delete(task_group_id):
    """Function to delete task group"""

    task_group = TaskGroups.query.get(task_group_id)
    if current_user.admin or task_group.owner_id == current_user.id:
        db.session.delete(task_group)
        db.session.commit()
        flash('Task Group has been deleted!', 'success')
        return redirect(url_for('task_groups.task_groups_list'))

    abort(403)
