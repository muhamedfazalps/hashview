import json

from flask import Blueprint, render_template, redirect, flash
from flask_login import login_required, current_user
from sqlalchemy import or_, and_

from hashview.models import Jobs, JobTasks, Users, Customers, Tasks, Agents, HashfileHashes, Hashes, Hashfiles, Settings
from hashview.utils.utils import update_job_task_status
from hashview.models import db

from datetime import datetime, timedelta

main = Blueprint('main', __name__)

@main.route("/")
@login_required
def home():
    jobs = Jobs.query.filter(or_((Jobs.status.like('Running')),(Jobs.status.like('Queued'))))
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
        collapse_all = (collapse_all + "collapse" + str(job.id) + " ")

    return render_template('home.html', jobs=jobs, running_jobs=running_jobs, queued_jobs=queued_jobs, users=users, customers=customers, job_tasks=job_tasks, tasks=tasks, agents=agents, recovered_list=recovered_list, time_estimated_list=time_estimated_list, collapse_all=collapse_all, timestamp=timestamp, datetime=datetime, timedelta=timedelta, fig1_labels=fig1_labels, fig1_values=fig1_values, settings=settings)

@main.route("/job_task/stop/<int:job_task_id>")
@login_required
def stop_job_task(job_task_id):
    job_task = JobTasks.query.get(job_task_id)
    job = Jobs.query.get(job_task.job_id)

    if job_task and job:
        if current_user.admin or job.owner_id == current_user.id:
            update_job_task_status(job_task.id, 'Canceled')
        else:
            flash('You are unauthorized to stop this task', 'danger')

    return redirect("/")


