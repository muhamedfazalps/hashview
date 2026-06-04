"""Flask routes to main page"""
import json
from datetime import datetime, timedelta

from flask import Blueprint, flash, redirect, render_template
from flask_login import current_user, login_required
from sqlalchemy import and_, or_

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

@main.route("/")
@login_required
def home():
    """Function to return the home page"""
    jobs = Jobs.query.filter(or_((Jobs.status.like('Running')),(Jobs.status.like('Queued')))).all()
    running_jobs = Jobs.query.filter_by(status = 'Running').order_by(Jobs.priority.desc(), Jobs.queued_at.asc()).all()
    queued_jobs = Jobs.query.filter_by(status = 'Queued').order_by(Jobs.priority.desc(), Jobs.queued_at.asc()).all()
    users = Users.query.all()
    customers = Customers.query.all()
    job_tasks = JobTasks.query.all()
    tasks = Tasks.query.all()
    agents = Agents.query.all()
    settings = Settings.query.first()

    recovered_list = {}
    time_estimated_list = {}

    # For line graph
    #fig1_cracked_cnt = db.session.query(Hashes, HashfileHashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).join(Hashfiles, HashfileHashes.hashfile_id==Hashfiles.id).filter(Hashfiles.uploaded_at == ).filter(Hashes.cracked == '1').count()
    today = datetime.now()
    fig1_labels = [(today - timedelta(days=i)).strftime("%b-%d") for i in range(6, -1, -1)]
    # hashfiles = Hashfiles.query.filter(Hashfiles.uploaded_at < filter_after).all()
    #foo = Hashes.query.filter_by(cracked=1).filter_by(recovered_at=)
    fig1_values = [
            Hashes.query.filter(
                and_(
                    (Hashes.cracked == 1),
                    (Hashes.recovered_at > today - timedelta(days=i+1)),
                    (Hashes.recovered_at < today - timedelta(days=i))
                    )
                ).count() for i in range(6, -1, -1)
            ]
    #fig1_values = ['7', '6', '5', '4', '3', '2', '1']


    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # Create Agent Progress
    for agent in agents:
        if agent.hc_status:
            recovered_list[agent.id] = json.loads(agent.hc_status)['Recovered']
            time_estimated_list[agent.id] = json.loads(agent.hc_status)['Time_Estimated']

    collapse_all = ""
    for job in jobs:
        collapse_all = collapse_all + "collapse" + str(job.id) + " "

    # Live recovery feed: most recent cracked hashes (time, account, plaintext, type).
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

    def _hexdec(v):
        # hashview stores usernames/plaintexts hex-encoded; decode safely.
        if not v:
            return ''
        try:
            return bytes.fromhex(v).decode('latin-1')
        except (ValueError, TypeError):
            return v

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
            'account': _hexdec(username) or '—',
            'plaintext': _hexdec(h.plaintext),
            'type': hash_type_names.get(str(h.hash_type), str(h.hash_type)),
            'recovered_by': user_names.get(h.recovered_by) or '—',
        })
        if len(recovery_feed) >= 10:
            break

    return render_template('home.html.j2', jobs=jobs, running_jobs=running_jobs, queued_jobs=queued_jobs, users=users, customers=customers, job_tasks=job_tasks, tasks=tasks, agents=agents, recovered_list=recovered_list, time_estimated_list=time_estimated_list, collapse_all=collapse_all, timestamp=timestamp, datetime=datetime, timedelta=timedelta, fig1_labels=fig1_labels, fig1_values=fig1_values, settings=settings, recovery_feed=recovery_feed)

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
