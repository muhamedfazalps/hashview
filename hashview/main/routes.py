"""Flask routes to main page"""
import json
from datetime import datetime, timedelta

from flask import Blueprint, flash, jsonify, redirect, render_template
from flask_login import current_user, login_required
from sqlalchemy import and_

from hashview.models import (
    Agents,
    Customers,
    Hashes,
    HashfileHashes,
    Jobs,
    JobTasks,
    Settings,
    Tasks,
    Users,
    db,
)
from hashview.utils.utils import update_job_task_status

main = Blueprint('main', __name__)

def _chart_data():
    """7-day 'passwords recovered' series: (labels, values), oldest→newest.

    `values` is a per-day count of cracked hashes; it drives both the line chart and
    the 'Recovered today' / 'Cracked this week' KPIs.
    """
    today = datetime.now()
    labels = [(today - timedelta(days=i)).strftime("%b-%d") for i in range(6, -1, -1)]
    values = [
        Hashes.query.filter(
            and_(
                (Hashes.cracked == 1),
                (Hashes.recovered_at > today - timedelta(days=i + 1)),
                (Hashes.recovered_at < today - timedelta(days=i)),
            )
        ).count()
        for i in range(6, -1, -1)
    ]
    return labels, values


def _recovery_feed():
    """Most-recent recovered passwords for the live feed (max 10, deduped)."""
    from hashview.jobs.forms import JobsNewHashFileForm
    hash_type_names = {}
    try:
        _f = JobsNewHashFileForm()
        for _sel in (_f.hash_type, _f.pwdump_hash_type, _f.netntlm_hash_type,
                     _f.kerberos_hash_type, _f.shadow_hash_type):
            for _v, _lab in _sel.choices:
                if _v is not None and str(_v) not in hash_type_names:
                    _nm = _lab.split(') ', 1)[1] if ') ' in _lab else _lab
                    hash_type_names[str(_v)] = _nm.split(' / ')[0].split(',')[0].strip()
    except Exception:  # pragma: no cover - defensive: never break the dashboard
        hash_type_names = {}

    users = Users.query.all()
    user_names = {u.id: ((u.first_name or '') + ' ' + (u.last_name or '')).strip() for u in users}

    # Last 10 recovered passwords, deduped by (hash_id, username). The hash↔hashfile_hashes
    # join is one-to-many (same hash across hashfiles / repeated username rows), so a plain
    # LIMIT 10 gets eaten by duplicates. We fetch a bounded window of the most-recent joined
    # rows and dedupe by (hash_id, username) — collapsing exact duplicates while keeping
    # distinct accounts that happen to share the same password.
    recent_rows = db.session.query(Hashes, HashfileHashes.username) \
        .join(HashfileHashes, Hashes.id == HashfileHashes.hash_id) \
        .filter(Hashes.cracked == True) \
        .filter(Hashes.recovered_at.isnot(None)) \
        .order_by(Hashes.recovered_at.desc()) \
        .limit(100).all()
    recovery_feed = []
    seen = set()
    for h, username in recent_rows:
        key = (h.id, username)
        if key in seen:
            continue
        seen.add(key)
        recovery_feed.append({
            'key': f'{h.id}:{username}',
            'time': h.recovered_at.strftime('%H:%M:%S') if h.recovered_at else '—',
            # usernames/plaintexts are stored as plain text now; use as-is.
            'account': (username or '') or '—',
            'plaintext': h.plaintext or '',
            'type': hash_type_names.get(str(h.hash_type), str(h.hash_type)),
            'recovered_by': user_names.get(h.recovered_by) or '—',
        })
        if len(recovery_feed) >= 10:
            break
    return recovery_feed


def _agents_ctx():
    """Agents + their parsed hashcat progress.

    Shared by the running-job task table and the agent-fleet modal so the hc_status
    parse lives in one place.
    """
    agents = Agents.query.all()
    recovered_list = {}
    time_estimated_list = {}
    for agent in agents:
        if agent.hc_status:
            hc = json.loads(agent.hc_status)
            recovered_list[agent.id] = hc['Recovered']
            time_estimated_list[agent.id] = hc['Time_Estimated']
    return {
        'agents': agents,
        'recovered_list': recovered_list,
        'time_estimated_list': time_estimated_list,
    }


def _jobs_ctx():
    """Template context for the running-job cards + queue table.

    Shared by the full page (home) and the /dashboard/jobs poll so the markup has a
    single source of truth.
    """
    return {
        'running_jobs': Jobs.query.filter_by(status='Running').order_by(Jobs.priority.desc(), Jobs.queued_at.asc()).all(),
        'queued_jobs': Jobs.query.filter_by(status='Queued').order_by(Jobs.priority.desc(), Jobs.queued_at.asc()).all(),
        'users': Users.query.all(),
        'customers': Customers.query.all(),
        'job_tasks': JobTasks.query.all(),
        'tasks': Tasks.query.all(),
        'settings': Settings.query.first(),
        'datetime': datetime,
        'timedelta': timedelta,
        **_agents_ctx(),
    }


@main.route("/")
@login_required
def home():
    """Render the operations dashboard."""
    fig1_labels, fig1_values = _chart_data()
    return render_template(
        'home.html.j2',
        fig1_labels=fig1_labels,
        fig1_values=fig1_values,
        recovery_feed=_recovery_feed(),
        **_jobs_ctx(),
    )


@main.route("/dashboard/jobs")
@login_required
def dashboard_jobs():
    """HTML fragment: running-job cards + queue table (polled ~20s)."""
    return render_template('_dash_jobs.html.j2', **_jobs_ctx())


@main.route("/dashboard/recovery")
@login_required
def dashboard_recovery():
    """HTML fragment: live recovery feed table (polled ~5s)."""
    return render_template('_dash_recovery.html.j2', recovery_feed=_recovery_feed())


@main.route("/dashboard/fleet")
@login_required
def dashboard_fleet():
    """HTML fragment: agent-fleet modal contents (polled ~20s while the modal is open).

    agent_stats is supplied by the inject_nav_counts() context processor.
    """
    return render_template('_dash_fleet.html.j2', **_agents_ctx())


@main.route("/dashboard/summary")
@login_required
def dashboard_summary():
    """JSON: rendered KPI cards + chart series (polled ~15s).

    Computes the 7×COUNT chart data once and feeds both the KPI row and the line
    chart. agent_stats / job_queue are supplied to the KPI partial by the global
    inject_nav_counts() context processor.
    """
    fig1_labels, fig1_values = _chart_data()
    return jsonify({
        'status': 'ok',
        'kpis_html': render_template('_dash_kpis.html.j2', fig1_values=fig1_values),
        'chart': {'labels': fig1_labels, 'values': fig1_values},
    })

@main.route("/job_task/stop/<int:job_task_id>")
@login_required
def stop_job_task(job_task_id):
    """Function to stop specific task on a running job"""

    job_task = JobTasks.query.get(job_task_id)
    job = Jobs.query.get(job_task.job_id)

    if job_task and job:
        if current_user.admin or job.owner_id == current_user.id:
            update_job_task_status(job_task.id, 'Canceled')
        else:
            flash('You are unauthorized to stop this task', 'danger')

    return redirect("/")
