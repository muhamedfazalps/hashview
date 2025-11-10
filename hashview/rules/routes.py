import os
from flask import Blueprint, render_template, flash, url_for, redirect, current_app, request
from flask_login import login_required, current_user
from hashview.models import Rules, Tasks, Jobs, JobTasks, Users
from hashview.rules.forms import RulesForm
from hashview.utils.utils import save_file, get_linecount, get_filehash
from hashview.models import db


rules = Blueprint('rules', __name__)

#############################################
# Rules
#############################################

@rules.route("/rules", methods=['GET'])
@login_required
def rules_list():
    rules = Rules.query.all()
    tasks = Tasks.query.all()
    jobs = Jobs.query.all()
    jobtasks = JobTasks.query.all()
    users = Users.query.all()
    return render_template('rules.html', title='Rules', rules=rules, tasks=tasks, jobs=jobs, jobtasks=jobtasks, users=users)

@rules.route("/rules/add", methods=['GET', 'POST'])
@login_required
def rules_add():
    form = RulesForm()
    if form.validate_on_submit():
        if form.rules.data:
            rules_path = os.path.join(current_app.root_path, save_file('control/rules', form.rules.data))

            rule = Rules(   name=form.name.data,
                            owner_id=current_user.id,
                            path=rules_path,
                            size=get_linecount(rules_path),
                            checksum=get_filehash(rules_path))
            db.session.add(rule)
            db.session.commit()
            flash(f'Rules File created!', 'success')
            return redirect(url_for('rules.rules_list'))
    return render_template('rules_add.html', title='Rules Add', form=form)

@rules.route("/rules/edit/<int:rule_id>", methods=['GET', 'POST'])
@login_required
def rules_view(rule_id):
    rule = Rules.query.get_or_404(rule_id)
    # Read file content
    try:
        with open(rule.path, 'r') as f:
            content = f.read()
    except Exception as e:
        flash(f'Error reading file: {e}', 'danger')
        return redirect(url_for('rules.rules_list'))

    can_edit = current_user.admin or rule.owner_id == current_user.id

    if request.method == 'POST':
        if not can_edit:
            flash('Unauthorized action!', 'danger')
            return redirect(url_for('rules.rules_view', rule_id=rule.id))
        new_content = request.form.get('content')
        try:
            with open(rule.path, 'w') as f:
                f.write(new_content)
            # Update metadata
            rule.size = get_linecount(rule.path)
            rule.checksum = get_filehash(rule.path)
            db.session.commit()
            flash('Rule file updated.', 'success')
        except Exception as e:
            flash(f'Error saving file: {e}', 'danger')
        return redirect(url_for('rules.rules_view', rule_id=rule.id))

    return render_template('rules_edit.html', rule=rule, content=content, can_edit=can_edit)
 

@rules.route("/rules/delete/<int:rule_id>", methods=['GET', 'POST'])
@login_required
def rules_delete(rule_id):
    rule = Rules.query.get(rule_id)
    if current_user.admin or rule.owner_id == current_user.id:
        # Check if part of a task
        tasks = Tasks.query.filter_by(rule_id=rule.id).first()
        if tasks:
            flash('Rules is currently used in a task and can not be delete.', 'danger')
        else:
            db.session.delete(rule)
            db.session.commit()
        flash('Rule file has been deleted!', 'success')
    else:
        flash('Unauthorized action!', 'danger')
    return redirect(url_for('rules.rules_list'))
