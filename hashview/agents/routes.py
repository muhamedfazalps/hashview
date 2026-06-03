"""Flask routes to handle Agents"""
import os
from flask import Blueprint, render_template, abort, flash, redirect, url_for, send_from_directory
from flask_login import login_required, current_user
import hashview
from hashview.agents.forms import AgentsForm
from hashview.models import Agents, JobTasks
from hashview.models import db
from sqlalchemy import text

agents = Blueprint('agents', __name__)


def _fmt_age(seconds):
    """Relative 'last heartbeat' label: now, 5s ago, 14m ago, 1h 14m ago, 1d 1h ago."""
    s = max(0, int(seconds))
    if s < 1:
        return 'now'
    if s < 60:
        return '%ds ago' % s
    m = s // 60
    if m < 60:
        return '%dm ago' % m
    h, rm = m // 60, m % 60
    if h < 24:
        return ('%dh %dm ago' % (h, rm)) if rm else ('%dh ago' % h)
    dy, rh = h // 24, h % 24
    return ('%dd %dh ago' % (dy, rh)) if rh else ('%dd ago' % dy)


def _agent_ages(agents):
    """Static relative 'last heartbeat' string per agent, measured against the DATABASE
    clock (last_checkin is stamped with func.now()), so it's independent of this process's
    timezone. The agents page isn't realtime, so this is computed once at render and shown
    as a static value — it does not tick."""
    try:
        db_now = db.session.execute(text("SELECT NOW()")).scalar()
    except Exception:
        db_now = None
    out = {}
    for a in agents:
        try:
            if a.last_checkin and db_now:
                out[a.id] = _fmt_age((db_now - a.last_checkin).total_seconds())
            else:
                out[a.id] = None
        except Exception:
            out[a.id] = None
    return out

@agents.route("/agents", methods=['GET', 'POST'])
@login_required
def agents_list():
    """Function to list agents"""
    if current_user.admin:
        agents_form = AgentsForm()

        if agents_form.validate_on_submit():
            agent_name = agents_form.name.data
            agent_id = agents_form.id.data

            agent = Agents.get(agent_id)
            agent.name = agent_name
            db.session.commit()

            flash('Updated Agents Name', 'success')
            return redirect(url_for('agents.agents_list'))
        else:
            agents = Agents.query.all()
            return render_template('agents.html.j2', title='agents', agents=agents,
                                   agent_age=_agent_ages(agents), agentsForm=agents_form)
    else:
        abort(403)

@agents.route("/agents/edit/<int:agent_id>", methods=['GET', 'POST'])
@login_required
def agents_edit(agent_id):
    """Function to edit agents"""
    if current_user.admin:
        agents_form = AgentsForm()

        if agents_form.validate_on_submit():
            agent_name = agents_form.name.data
            agent_id = agents_form.id.data

            agent = Agents.query.get(agent_id)
            agent.name = agent_name
            db.session.commit()

            flash('Updated Agents Name', 'success')
            return redirect(url_for('agents.agents_list'))
        else:
            agent = Agents.query.get(agent_id)
            return render_template('agents_edit.html.j2', title='agents', agent=agent, agentsForm=agents_form)
    else:
        flash('You are unauthorized to edit agent data.', 'danger')
        return redirect(url_for('agents.agents_list'))

@agents.route("/agents/<int:agent_id>/authorize", methods=['GET'])
@login_required
def agents_authorize(agent_id):
    """Function to authorize agents"""
    if current_user.admin:
        agent = Agents.query.get(agent_id)

        agent.status = 'Authorized'
        db.session.commit()

        flash('Agent Authorized', 'success')
        return redirect(url_for('agents.agents_list'))
    else:
        abort(403)

@agents.route("/agents/<int:agent_id>/deauthorize", methods=['GET'])
@login_required
def agents_deauthorize(agent_id):
    """Function to deauthorize agents"""
    if current_user.admin:
        agent = Agents.query.get(agent_id)

        if agent.status == 'Working':
            flash('Agent was working. The active task was not stopped and you will not receive the results.', 'warning')

        agent.status = 'Pending'
        db.session.commit()

        flash('Agent Deauthorized', 'success')
        return redirect(url_for('agents.agents_list'))
    else:
        abort(403)


@agents.route("/agents/delete/<int:agent_id>", methods=['GET', 'POST'])
@login_required
def agents_delete(agent_id):
    """Function to delete agent"""
    if current_user.admin:
        jobtasks = JobTasks.query.filter_by(agent_id = agent_id).count()
        if jobtasks > 0:
            flash('Error: Agent is active with a task.', 'danger')
        else:
            agent = Agents.query.get(agent_id)
            db.session.delete(agent)
            db.session.commit()
            flash('Agent removed', 'success')
        return redirect(url_for('agents.agents_list'))
    else:
        abort(403)

@agents.route("/agents/download", methods=['GET'])
@login_required
def agents_download():
    """Function to download agent"""
    version = hashview.__version__
    filename = 'hashview-agent.' + version + '.tgz'
    cmd = 'tar -czf hashview/control/tmp/' + filename + ' -C install hashview-agent'
    os.system(cmd)

    return send_from_directory('control/tmp', filename, as_attachment=True)
