from flask import Blueprint, render_template, redirect, flash, url_for, current_app, request
from flask_login import login_required, current_user
from sqlalchemy import func
from hashview.jobs.forms import JobsForm, JobsNewHashFileForm, JobsNotificationsForm, JobSummaryForm
from hashview.models import HashNotifications, JobNotifications, Jobs, Customers, Hashfiles, Users, HashfileHashes, Hashes, JobTasks, Tasks, TaskGroups, Settings, Wordlists
from hashview.utils.utils import save_file, import_hashfilehashes, build_hashcat_command, validate_pwdump_hashfile, validate_netntlm_hashfile, validate_kerberos_hashfile, validate_shadow_hashfile, validate_user_hash_hashfile, validate_hash_only_hashfile
from hashview.models import db
from datetime import datetime
import os
import secrets
import json

jobs = Blueprint('jobs', __name__)

@jobs.route("/jobs", methods=['GET', 'POST'])
@login_required
def jobs_list():
    # Add pagination to reduce load time when many jobs exist
    page = request.args.get('page', 1, type=int)
    per_page = 20  # Adjust as needed

    # Check if filtering by current user
    show_only_mine = request.args.get('show_only_mine', 'false')

    # Build query based on filter
    if show_only_mine == 'true':
        pagination = Jobs.query.filter_by(owner_id=current_user.id).order_by(Jobs.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    else:
        pagination = Jobs.query.order_by(Jobs.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    jobs = pagination.items

    customers = Customers.query.all()
    users = Users.query.all()
    hashfiles = Hashfiles.query.all()
    job_tasks = JobTasks.query.all()
    tasks = Tasks.query.all()
    return render_template(
        'jobs.html',
        title='Jobs',
        jobs=jobs,
        customers=customers,
        users=users,
        hashfiles=hashfiles,
        job_tasks=job_tasks,
        tasks=tasks,
        pagination=pagination,
        show_only_mine=show_only_mine
    )

@jobs.route("/jobs/add", methods=['GET', 'POST'])
@login_required
def jobs_add():
    jobs = Jobs.query.all()
    customers = Customers.query.order_by(Customers.name).all()
    jobsForm = JobsForm()
    settings = Settings.query.first()
    if jobsForm.validate_on_submit():
        customer_id = jobsForm.customer_id.data
        if jobsForm.customer_id.data == 'add_new':
            customer = Customers(name=jobsForm.customer_name.data)
            db.session.add(customer)
            db.session.commit()
            customer_id = customer.id

        if settings.enabled_job_weights:
            if int(jobsForm.priority.data) >= 1 and int(jobsForm.priority.data) <=5:
                job_priority = jobsForm.priority.data
            else:
                job_priority = 3
        else:
            job_priority = 3

        job = Jobs( name = jobsForm.name.data,
                    priority = job_priority,
                    status = 'Incomplete',
                    customer_id = customer_id,
                    owner_id = current_user.id,
                    limit_recovered = jobsForm.limit_recovered.data)
        db.session.add(job)
        db.session.commit()
        return redirect(str(job.id)+"/assigned_hashfile/")
    return render_template('jobs_add.html', title='Jobs', jobs=jobs, customers=customers, jobsForm=jobsForm, settings=settings)

@jobs.route("/jobs/<int:job_id>/assigned_hashfile/", methods=['GET', 'POST'])
@login_required
def jobs_assigned_hashfile(job_id):
    job = Jobs.query.get(job_id)
    hashfiles = Hashfiles.query.filter_by(customer_id=job.customer_id)
    jobsNewHashFileForm = JobsNewHashFileForm()
    hashfile_cracked_rate = {}

    if job.status == 'Running' or job.status == 'Queued':
        flash('You can not edit a running or queued job. First stop and remove job from queue before editing.', 'danger')
        return redirect(url_for('jobs.list', job_id=job_id))

    for hashfile in hashfiles:
        cracked_cnt = db.session.query(Hashes).outerjoin(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(Hashes.cracked == '1').filter(HashfileHashes.hashfile_id==hashfile.id).count()
        total = db.session.query(Hashes).outerjoin(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(HashfileHashes.hashfile_id==hashfile.id).count()
        hashfile_cracked_rate[hashfile.id] = "(" + str(cracked_cnt) + "/" + str(total) + ")"

    if jobsNewHashFileForm.validate_on_submit():

        hashfile_path = ""
        hashfile_name = ""
        if jobsNewHashFileForm.hashfile.data:
            # User submitted a file upload
            hashfile_path = os.path.join(current_app.root_path, save_file('control/tmp', jobsNewHashFileForm.hashfile.data))
            hashfile_name = jobsNewHashFileForm.hashfile.data.filename
        elif jobsNewHashFileForm.hashfilehashes.data:
            # User submitted copied/pasted hashes
            # Going to have to save a file manually instead of using save_file since save_file requires form data to be passed and we're not collecting that object for this tab

            if len(jobsNewHashFileForm.name.data) == 0:
                flash('You must assign a name to the hashfile', 'danger')
                return redirect(url_for('jobs.jobs_assigned_hashfile', job_id=job_id))
            else:
                hashfile_name = jobsNewHashFileForm.name.data

            random_hex = secrets.token_hex(8)
            hashfile_path = 'hashview/control/tmp/' + random_hex
            hashfilehashes_file = open(hashfile_path, 'w+')
            hashfilehashes_file.write(jobsNewHashFileForm.hashfilehashes.data)
            hashfilehashes_file.close()

        if len(hashfile_path) > 0:
            if jobsNewHashFileForm.file_type.data == 'pwdump':
                has_problem = validate_pwdump_hashfile(hashfile_path, jobsNewHashFileForm.pwdump_hash_type.data)
                hash_type = jobsNewHashFileForm.pwdump_hash_type.data
            elif jobsNewHashFileForm.file_type.data == 'NetNTLM':
                has_problem = validate_netntlm_hashfile(hashfile_path, jobsNewHashFileForm.netntlm_hash_type.data)
                hash_type = jobsNewHashFileForm.netntlm_hash_type.data
            elif jobsNewHashFileForm.file_type.data == 'kerberos':
                has_problem = validate_kerberos_hashfile(hashfile_path, jobsNewHashFileForm.kerberos_hash_type.data) 
                hash_type = jobsNewHashFileForm.kerberos_hash_type.data
            elif jobsNewHashFileForm.file_type.data == 'shadow':
                has_problem = validate_shadow_hashfile(hashfile_path, jobsNewHashFileForm.shadow_hash_type.data)
                hash_type = jobsNewHashFileForm.shadow_hash_type.data
            elif jobsNewHashFileForm.file_type.data == 'user_hash':
                has_problem = validate_user_hash_hashfile(hashfile_path, jobsNewHashFileForm.hash_type.data)
                hash_type = jobsNewHashFileForm.hash_type.data
            elif jobsNewHashFileForm.file_type.data == 'hash_only':
                has_problem = validate_hash_only_hashfile(hashfile_path, jobsNewHashFileForm.hash_type.data) 
                hash_type = jobsNewHashFileForm.hash_type.data                                         
            else:
                has_problem = 'Invalid File Format'

            if has_problem:
                flash(has_problem, 'danger')
                return redirect(url_for('jobs.jobs_assigned_hashfile', job_id=job_id))
            else:
                hashfile = Hashfiles(name=hashfile_name, customer_id=job.customer_id, owner_id=current_user.id)
                db.session.add(hashfile)
                db.session.commit()

                # Parse Hashfile
                if not import_hashfilehashes(   hashfile_id=hashfile.id,
                                                hashfile_path=hashfile_path,
                                                file_type=jobsNewHashFileForm.file_type.data,
                                                hash_type=hash_type
                                                ):
                    return ('Something went wrong. Check the filetype / hashtype and try again.')

                hashfile_hashes_cnt = db.session.query(HashfileHashes).filter_by(hashfile_id=hashfile.id).count()
                if hashfile_hashes_cnt == 0:
                    db.session.delete(hashfile)
                    db.session.commit()
                    flash('No valid hashes found in the hashfile. Hashfile not added.', 'danger')
                    return redirect(url_for('jobs.jobs_assigned_hashfile', job_id=job_id))


                # Delete hashfile file on disk
                # TODO
                job.hashfile_id = hashfile.id
                db.session.commit()

            return redirect(str(hashfile.id))

    elif request.method == 'POST' and request.form['hashfile_id']:
        # User selected an existing hashfile
        job.hashfile_id = request.form['hashfile_id']
        db.session.commit()
        return redirect("/jobs/" + str(job.id)+"/notifications")

    else:
        for error in jobsNewHashFileForm.name.errors:
            print(str(error))
        for error in jobsNewHashFileForm.file_type.errors:
            print(str(error))
        for error in jobsNewHashFileForm.hash_type.errors:
            print(str(error))
        for error in jobsNewHashFileForm.hashfile.errors:
            print(str(error))
        for error in jobsNewHashFileForm.hashfilehashes.errors:
            print(str(error))
        for error in jobsNewHashFileForm.submit.errors:
            print(str(error))

    return render_template('jobs_assigned_hashfiles.html', title='Jobs Assigned Hashfiles', hashfiles=hashfiles, job=job, jobsNewHashFileForm=jobsNewHashFileForm, hashfile_cracked_rate=hashfile_cracked_rate)

@jobs.route("/jobs/<int:job_id>/assigned_hashfile/<int:hashfile_id>", methods=['GET'])
@login_required
def jobs_assigned_hashfile_cracked(job_id, hashfile_id):
    job = Jobs.query.get(job_id)
    hashfile = Hashfiles.query.get(hashfile_id)
    # Can be optimized to only return the hash and plaintext
    cracked_hashfiles_hashes = db.session.query(Hashes, HashfileHashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(Hashes.cracked == '1').filter(HashfileHashes.hashfile_id==hashfile.id).all()
    cracked_hashfiles_hashes_cnt = db.session.query(Hashes).join(HashfileHashes, Hashes.id == HashfileHashes.hash_id).filter(Hashes.cracked == '1').filter(HashfileHashes.hashfile_id==hashfile.id).count()
    if cracked_hashfiles_hashes_cnt > 0:
        flash(str(cracked_hashfiles_hashes_cnt) + " instacracked Hashes!", 'success')
    # Oppertunity for either a stored procedure or for some fancy queries.

    return render_template('jobs_assigned_hashfiles_cracked.html', title='Jobs Assigned Hashfiles Cracked', hashfile=hashfile, job=job, cracked_hashfiles_hashes=cracked_hashfiles_hashes)

@jobs.route("/jobs/<int:job_id>/tasks", methods=['GET'])
@login_required
def jobs_list_tasks(job_id):
    job = Jobs.query.get(job_id)
    tasks = Tasks.query.order_by(Tasks.name.asc()).all()
    job_tasks = JobTasks.query.filter_by(job_id=job_id)
    task_groups = TaskGroups.query.all()
    wordlists = Wordlists.query.all()
    # Right now we're doing nested loops in the template, this could probably be solved with a left/join select

    return render_template('jobs_assigned_tasks.html', title='Jobs Assigned Tasks', job=job, tasks=tasks, job_tasks=job_tasks, task_groups=task_groups, wordlists=wordlists)

@jobs.route("/jobs/<int:job_id>/assign_task/<int:task_id>", methods=['GET'])
@login_required
def jobs_assign_task(job_id, task_id):

    # Someone smarter than me can turn this into a single DB Query

    jobtask_exists = JobTasks.query.filter_by(job_id=job_id, task_id=task_id).first()
    wordlist = Wordlists.query.get(Tasks.query.get(task_id).wl_id)
    # hc_attackmode = Tasks.query.get(task_id).hc_attackmode
    
    if jobtask_exists:
        #if hc_attackmode == '0' or hc_attackmode == '1' or hc_attackmode == '6' or hc_attackmode == '7':
        if wordlist:
            if wordlist.type == 'static':
                flash('Task already assigned to the job.', 'warning')
            else:
                job_task = JobTasks(job_id=job_id, task_id=task_id, status='Not Started')
                db.session.add(job_task)
                db.session.commit() 
        else:
            flash('Task already assigned to the job.', 'warning')
    else:
        job_task = JobTasks(job_id=job_id, task_id=task_id, status='Not Started')
        db.session.add(job_task)
        db.session.commit()

    return redirect("/jobs/"+str(job_id)+"/tasks")

@jobs.route("/jobs/<int:job_id>/assign_task_group/<int:task_group_id>", methods=['GET'])
@login_required
def jobs_assign_task_group(job_id, task_group_id):
    task_group = TaskGroups.query.get(task_group_id)

    for task_group_entry in json.loads(task_group.tasks):
        # Check if task.hc_attackmode = 0, 1, 6, or 7. If so allow duplicates
        jobtask_exists = JobTasks.query.filter_by(job_id=job_id, task_id=task_group_entry).first()
        wordlist = Wordlists.query.get(Tasks.query.get(task_group_entry).wl_id)

        if jobtask_exists:
            if wordlist:
                if wordlist.type == 'static':
                    continue
                else:
                    job_task = JobTasks(job_id=job_id, task_id=task_group_entry, status='Not Started')
                    db.session.add(job_task)
                    db.session.commit()
            else:
                continue
        else:
            job_task = JobTasks(job_id=job_id, task_id=task_group_entry, status='Not Started')
            db.session.add(job_task)
            db.session.commit()


        # job_task = JobTasks(job_id=job_id, task_id=task_group_entry, status='Not Started')
        # db.session.add(job_task)
        # db.session.commit()

    return redirect("/jobs/" + str(job_id) + "/tasks")

@jobs.route("/jobs/<int:job_id>/assign_task/lucky", methods=['GET'])
@login_required
def jobs_assign_lucky_task_group(job_id):

    job = Jobs.query.get(job_id)
    hashfile = Hashfiles.query.get(job.hashfile_id)
    hashfile_hashes = HashfileHashes.query.filter_by(hashfile_id=hashfile.id).first()
    hash = Hashes.query.get(hashfile_hashes.hash_id)


    # Get top 10 effective tasks
    most_effective_tasks_raw = db.session.query(func.count(Hashes.id).label("row_count"), Hashes.task_id, Tasks.name,).join(Tasks, Hashes.task_id == Tasks.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.task_id is not None) \
        .filter(Hashes.task_id != '0') \
        .filter(Hashes.hash_type == hash.hash_type) \
        .group_by(Hashes.task_id) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()

    if len(most_effective_tasks_raw) == 0:
        flash('Not enough data to generate top tasks.', 'danger')
    else:
    # for each effective task 
        for entry in most_effective_tasks_raw:
            job_tasks = JobTasks.query.filter_by(job_id=job_id).all()
            if entry.task_id not in {job_task.task_id for job_task in job_tasks}:
                job_task = JobTasks(job_id=job_id, task_id=entry.task_id, status='Not Started')
                db.session.add(job_task)
                db.session.commit()

        flash('Successfully Added Top 10 Tasks', 'success')
    return redirect("/jobs/" + str(job_id) + "/tasks")

@jobs.route("/jobs/<int:job_id>/move_task_up/<int:task_id>", methods=['GET'])
@login_required
def jobs_move_task_up(job_id, task_id):
    job = Jobs.query.get(job_id)
    job_tasks = JobTasks.query.filter_by(job_id=job_id).all()
    tasks = Tasks.query.all()

    # We create an array of all related jobtasks, remove existing jobtasks, re-arrange, and create new jobtasks (this way we dont have to worry about non-contigous jobtasks ids)
    temp_jobtasks = []
    new_jobtasks = []

    for entry in job_tasks:
        temp_jobtasks.append(str(entry.task_id))

    if temp_jobtasks[0] == str(task_id):
        flash('Task is already at the top', 'warning')
        return redirect("/jobs/"+str(job_id)+"/tasks")
    else:
        setLength = len(temp_jobtasks) - 1
        elementIndex = temp_jobtasks.index(str(task_id))
        temp_value = temp_jobtasks[elementIndex - 1]
        temp_jobtasks[elementIndex - 1] = str(task_id)
        temp_jobtasks[elementIndex] = str(temp_value)

    new_jobtasks = temp_jobtasks

    JobTasks.query.filter_by(job_id=job_id).delete()
    db.session.commit()

    for entry in new_jobtasks:
        job_task = JobTasks(job_id=job_id, task_id=entry, status='Not Started')
        db.session.add(job_task)
        db.session.commit()

    return redirect("/jobs/"+str(job_id)+"/tasks")

@jobs.route("/jobs/<int:job_id>/move_task_down/<int:task_id>", methods=['GET'])
@login_required
def jobs_move_task_down(job_id, task_id):
    job = Jobs.query.get(job_id)
    job_tasks = JobTasks.query.filter_by(job_id=job_id).all()
    tasks = Tasks.query.all()

    # We create an array of all related jobtasks, remove existing jobtasks, re-arrange, and create new jobtasks (this way we dont have to worry about non-contigous jobtasks ids)
    temp_jobtasks = []
    new_jobtasks = []

    for entry in job_tasks:
        temp_jobtasks.append(str(entry.task_id))

    if temp_jobtasks[-1] == str(task_id):
        flash('Task is already at the bottom', 'warning')
        return redirect("/jobs/"+str(job_id)+"/tasks")
    else:
        for index in range(len(temp_jobtasks)):
            if int(index+1) <= len(temp_jobtasks):
                if  temp_jobtasks[int(index)] == str(task_id):
                    new_jobtasks.append(temp_jobtasks[int(index+1)])
                    new_jobtasks.append(str(task_id))
                    del temp_jobtasks[int(index+1)]
                else:
                    new_jobtasks.append(temp_jobtasks[int(index)])

    JobTasks.query.filter_by(job_id=job_id).delete()
    db.session.commit()

    for entry in new_jobtasks:
        job_task = JobTasks(job_id=job_id, task_id=entry, status='Not Started')
        db.session.add(job_task)
        db.session.commit()

    return redirect("/jobs/"+str(job_id)+"/tasks")

@jobs.route("/jobs/<int:job_id>/remove_task/<int:task_id>", methods=['GET'])
@login_required
def jobs_remove_task(job_id, task_id):
    job_task = JobTasks.query.filter_by(job_id=job_id, task_id=task_id).first()
    db.session.delete(job_task)
    db.session.commit()

    return redirect("/jobs/"+str(job_id)+"/tasks")

@jobs.route("/jobs/<int:job_id>/remove_all_tasks", methods=['GET'])
@login_required
def jobs_remove_all_tasks(job_id):
    job_tasks = JobTasks.query.filter_by(job_id=job_id)
    for tasks in job_tasks:
        db.session.delete(tasks)
    db.session.commit()
    return redirect("/jobs/"+str(job_id)+"/tasks")

@jobs.route("/jobs/<int:job_id>/notifications", methods=['GET', 'POST'])
@login_required
def jobs_assign_notifications(job_id):
    form = JobsNotificationsForm()
    job = Jobs.query.get(job_id)

    # Moving task check to /summary. Otherwise this will always skip /notifications now that notifications are before tasks
    # populate the forms dynamically with the choices in the database
    # form.hashes.choices = [(str(c[0].id), str(bytes.fromhex(c[1].username).decode('latin-1')) + ':' + c[0].ciphertext) for c in db.session.query(Hashes, HashfileHashes).outerjoin(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(Hashes.cracked == '0').filter(HashfileHashes.hashfile_id==job.hashfile_id).all()]

    if form.validate_on_submit():
        if form.job_completion_email.data == True:
            # Check if we already have a notification set
            pre_existing_job_notification = JobNotifications.query.filter_by(job_id=job_id, owner_id=current_user.id, method='email').first()
            if pre_existing_job_notification == None:
                job_notification = JobNotifications(
                    owner_id = current_user.id,
                    job_id = job_id,
                    method = 'email'
                )
                db.session.add(job_notification)
                db.session.commit()
        if form.job_completion_pushover.data == True:
            pre_existing_job_notification = JobNotifications.query.filter_by(job_id=job_id, owner_id=current_user.id, method='push').first()
            if pre_existing_job_notification == None:
                job_notification = JobNotifications(
                    owner_id = current_user.id,
                    job_id = job_id,
                    method = 'push'
                )
                db.session.add(job_notification)
                db.session.commit()
        if form.hash_completion_pushover.data == True and form.hash_completion_email.data == True:
            return redirect("/jobs/"+str(job_id)+"/notifications/both/hashes")
        elif form.hash_completion_pushover.data == True and form.hash_completion_email.data == False:
            return redirect("/jobs/"+str(job_id)+"/notifications/push/hashes")
        elif form.hash_completion_pushover.data == False and form.hash_completion_email.data == True:
            return redirect("/jobs/"+str(job_id)+"/notifications/email/hashes")
        else:
            return redirect("/jobs/" + str(job_id)+ "/tasks")
    else:
        return render_template('jobs_assigned_notifications.html', title='Jobs Assigned Notifications', job=job, form=form)

@jobs.route("/jobs/<int:job_id>/notifications/<method>/hashes", methods=['GET', 'POST'])
@login_required
def jobs_assign_notification_hashes(job_id, method):
    job = Jobs.query.get(job_id)
    hashes = db.session.query(Hashes, HashfileHashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(Hashes.cracked == '0').filter(HashfileHashes.hashfile_id==job.hashfile_id).with_entities(Hashes.id, HashfileHashes.username, Hashes.ciphertext).all()
    existing_hash_notifications = HashNotifications.query.filter_by(owner_id=current_user.id)
    if request.method == 'POST':
        for entry in hashes:
            for selected in request.form.getlist('selected'):
                if str(selected) == str(entry[0]):
                    hash_notification_exists = HashNotifications.query.filter_by(hash_id=entry[0]).filter_by(owner_id=current_user.id).first()
                    if not hash_notification_exists:
                        if method == 'push' or method == 'email':
                            hash_notification = HashNotifications(
                                owner_id = current_user.id,
                                hash_id = entry[0],
                                method = method
                            )
                            db.session.add(hash_notification)
                            db.session.commit()
                        elif method == 'both':
                            hash_notification_email = HashNotifications(
                                owner_id = current_user.id,
                                hash_id = entry[0],
                                method = 'email'
                            )
                            hash_notification_pushover = HashNotifications(
                                owner_id = current_user.id,
                                hash_id = entry[0],
                                method = 'push'
                            )
                            db.session.add(hash_notification_email)
                            db.session.add(hash_notification_pushover)
                            db.session.commit()
                        else:
                            continue
                            
        # Some for entry in request/post
        # add hash notification if not already set
        #return redirect("/jobs/"+str(job_id)+"/summary")
        return redirect("/jobs/"+str(job_id)+"/tasks")
    else:
        return render_template('jobs_assigned_notifications_hashes.html', title='Assigned Hash Notifications', job=job, hashes=hashes, existing_hash_notifications=existing_hash_notifications)

@jobs.route("/jobs/delete/<int:job_id>", methods=['GET', 'POST'])
@login_required
def jobs_delete(job_id):
    job = Jobs.query.get(job_id)
    if current_user.admin or job.owner_id == current_user.id:
        JobTasks.query.filter_by(job_id=job_id).delete()
        JobNotifications.query.filter_by(job_id=job_id).delete()

        db.session.delete(job)
        db.session.commit()
        flash('Job has been deleted!', 'success')
        return redirect(url_for('jobs.jobs_list'))
    else:
        flash('You do not have rights to delete this job!', 'danger')
        return redirect(url_for('jobs.jobs_list'))

@jobs.route("/jobs/<int:job_id>/summary", methods=['GET', 'POST'])
@login_required
def jobs_summary(job_id):

    # Check if job has any assigned tasks, and if not, send the user back to the task assigned page.
    job_tasks = JobTasks.query.filter_by(job_id=job_id).all()
    if len(job_tasks) == 0:
        flash('You must assign at least one task.', 'warning')
        return redirect("/jobs/"+str(job_id)+"/tasks")

    job = Jobs.query.get(job_id)
    form = JobSummaryForm()

    settings = Settings.query.first()
    tasks = Tasks.query.all()
    hashfile = Hashfiles.query.get(job.hashfile_id)
    customer = Customers.query.get(job.customer_id)
    cracked_cnt = db.session.query(Hashes).outerjoin(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(Hashes.cracked == '1').filter(HashfileHashes.hashfile_id==hashfile.id).count()
    hash_total = db.session.query(Hashes).outerjoin(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(HashfileHashes.hashfile_id==hashfile.id).count()
    cracked_rate = str(cracked_cnt) + '/' + str(hash_total)
    hash_notification_cnt = db.session.query(HashNotifications).join(HashfileHashes, HashNotifications.hash_id==HashfileHashes.hash_id).filter(HashfileHashes.hashfile_id == hashfile.id).count()
    hash_notification = db.session.query(HashNotifications).join(HashfileHashes, HashNotifications.hash_id==HashfileHashes.hash_id).filter(HashfileHashes.hashfile_id == hashfile.id).first()
    job_notification = JobNotifications.query.filter_by(job_id = job.id).first()

    job_notification = JobNotifications.query.filter_by(job_id=job_id).first()

    if form.validate_on_submit():
        for job_task in job_tasks:
            job_task.status = 'Ready'

        job.status = 'Ready'
        job.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.session.commit()

        flash('Job successfully created', 'success')

        return redirect(url_for('jobs.jobs_list'))
    else:
        return render_template('jobs_summary.html', title='Job Summary', job=job, form=form, job_notification=job_notification, cracked_rate=cracked_rate, job_tasks=job_tasks, hash_notification_cnt=hash_notification_cnt, customer=customer, hashfile=hashfile, tasks=tasks, hash_notification=hash_notification, settings=settings)

@jobs.route("/jobs/start/<int:job_id>", methods=['GET'])
@login_required
def jobs_start(job_id):
    job = Jobs.query.get(job_id)
    job_tasks = JobTasks.query.filter_by(job_id = job_id).all()

    if job and job_tasks:
        if current_user.admin or job.owner_id == current_user.id:
            job.status = 'Queued'
            job.queued_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            for job_task in job_tasks:
                job_task.status = 'Queued'
                job_task.priority = job.priority
                job_task.command = build_hashcat_command(job.id, job_task.task_id)

            db.session.commit()
            flash('Job has been Started!', 'success')
            return redirect(url_for('main.home'))
        else:
            flash('You do not have rights to start this job!', 'danger')
            return redirect(url_for('jobs.jobs_list'))
    else:
        flash('Error in starting job', 'danger')
        return redirect(url_for('jobs.jobs_list'))

@jobs.route("/jobs/stop/<int:job_id>", methods=['GET'])
@login_required
def jobs_stop(job_id):
    job = Jobs.query.get(job_id)
    job_tasks = JobTasks.query.filter_by(job_id = job_id).all()

    if job:
        if current_user.admin or job.owner_id == current_user.id:
            if job.status == 'Running' or job.status == 'Queued':
                job.status = 'Canceled'
                job.ended_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

                for job_task in job_tasks:
                        job_task.status = 'Canceled'
                        job_task.agent_id = None
                db.session.commit()
                flash('Job has been stopped!', 'success')
            else:
                flash('Job not activly running.', 'danger')
        else:
            flash('You do not have rights to stop this job!', 'danger')
    else:
        flash('Error in stopping job', 'danger')
    return redirect(url_for('jobs.jobs_list'))
