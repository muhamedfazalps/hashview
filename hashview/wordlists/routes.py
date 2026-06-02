"""Flask routes to handle Wordlists"""
from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user
from hashview.wordlists.forms import WordlistsForm
from hashview.models import Tasks, Wordlists, Users, Rules, JobTasks, Hashes
from hashview.models import db
from hashview.utils.utils import save_file, get_linecount, get_filehash, update_dynamic_wordlist

wordlists = Blueprint('wordlists', __name__)


def _wl_ttype(task):
    """Friendly attack-type label for a task (matches the Tasks/Task-Groups views)."""
    if task.hc_attackmode == 0 and task.rule_id:
        return 'DICT + RULE'
    if task.hc_attackmode == 0:
        return 'DICTIONARY'
    if task.hc_attackmode == 1:
        return 'COMBINATOR'
    if task.hc_attackmode == 3:
        return 'MASK'
    if task.hc_attackmode in (6, 7):
        return 'HYBRID'
    return '?'


@wordlists.route("/wordlists", methods=['GET'])
@login_required
def wordlists_list():
    """Function to present list of wordlists"""

    static_wordlists = Wordlists.query.filter_by(type='static').all()
    dynamic_wordlists = Wordlists.query.filter_by(type='dynamic').all()
    wordlists = Wordlists.query.all()
    tasks = Tasks.query.all()
    users = Users.query.all()

    # --- per-wordlist info-modal data ---
    rule_names = {r.id: r.name for r in Rules.query.all()}
    user_names = {u.id: (((u.first_name or '') + ' ' + (u.last_name or '')).strip() or '—')
                  for u in users}
    recovered_by_task = {
        row.task_id: row.recovered_count
        for row in Hashes.query.with_entities(
            Hashes.task_id, db.func.count(Hashes.id).label('recovered_count')
        ).filter(Hashes.cracked == '1').group_by(Hashes.task_id).all()
    }
    jobs_by_task = {}
    for jt in JobTasks.query.all():
        jobs_by_task.setdefault(jt.task_id, set()).add(jt.job_id)

    wl_used_tasks = {}   # wordlist.id -> [{name, rule, type, hits}]
    wl_hits = {}         # wordlist.id -> summed historical hits
    wl_task_count = {}   # wordlist.id -> number of tasks using it
    wl_job_count = {}    # wordlist.id -> number of distinct jobs using those tasks
    wl_owner = {}        # wordlist.id -> owner display name
    for wl in wordlists:
        used = [t for t in tasks if t.wl_id == wl.id or t.wl_id_2 == wl.id]
        rows, job_ids, total = [], set(), 0
        for t in used:
            hits = recovered_by_task.get(t.id, 0)
            total += hits
            job_ids |= jobs_by_task.get(t.id, set())
            rows.append({
                'name': t.name,
                'rule': rule_names.get(t.rule_id) if t.rule_id else None,
                'type': _wl_ttype(t),
                'hits': hits,
            })
        wl_used_tasks[wl.id] = rows
        wl_hits[wl.id] = total
        wl_task_count[wl.id] = len(used)
        wl_job_count[wl.id] = len(job_ids)
        wl_owner[wl.id] = user_names.get(wl.owner_id, '—')

    return render_template('wordlists.html.j2', title='Wordlists',
                           static_wordlists=static_wordlists, dynamic_wordlists=dynamic_wordlists,
                           wordlists=wordlists, tasks=tasks, users=users,
                           wl_used_tasks=wl_used_tasks, wl_hits=wl_hits,
                           wl_task_count=wl_task_count, wl_job_count=wl_job_count,
                           wl_owner=wl_owner, wordlistsForm=WordlistsForm())

@wordlists.route("/wordlists/add", methods=['GET', 'POST'])
@login_required
def wordlists_add():
    """Function to add new wordlist"""

    form = WordlistsForm()
    if form.validate_on_submit():
        if form.wordlist.data:
            #wordlist_path = os.path.join(current_app.root_path, save_file('control/wordlists', form.wordlist.data))
            wordlist_path = save_file('control/wordlists', form.wordlist.data)
            print('File saved')
            wordlist = Wordlists(name=form.name.data,
                                owner_id=current_user.id,
                                type='static',
                                path=wordlist_path,
                                checksum=get_filehash(wordlist_path),
                                size=get_linecount(wordlist_path))
            db.session.add(wordlist)
            db.session.commit()
            flash('Wordlist created!', 'success')
            return redirect(url_for('wordlists.wordlists_list'))
    return render_template('wordlists_add.html.j2', title='Wordlist Add', form=form)

@wordlists.route("/wordlists/delete/<int:wordlist_id>", methods=['POST'])
@login_required
def wordlists_delete(wordlist_id):
    """Function to delete wordlist"""

    wordlist = Wordlists.query.get(wordlist_id)
    if current_user.admin or wordlist.owner_id == current_user.id:

        # prevent deletion of dynamic list
        if wordlist.type == 'dynamic':
            flash('Dynamic Wordlists can not be deleted.', 'danger')
            redirect(url_for('wordlists.wordlists_list'))

        # Check if associated with a Task
        tasks = Tasks.query.all()
        for task in tasks:
            if task.wl_id == wordlist_id:
                flash('Failed. Wordlist is associated to one or more tasks', 'danger')
                return redirect(url_for('wordlists.wordlists_list'))

        db.session.delete(wordlist)
        db.session.commit()
        flash('Wordlist has been deleted!', 'success')
    else:
        flash('Unauthorized Action!', 'danger')
    return redirect(url_for('wordlists.wordlists_list'))


@wordlists.route("/wordlists/update/<int:wordlist_id>", methods=['GET'])
@login_required
def dynamicwordlist_update(wordlist_id):
    """Function to update dynamic wordlist"""

    wordlist = Wordlists.query.get(wordlist_id)
    if wordlist.type == 'dynamic':
        update_dynamic_wordlist(wordlist_id)
        flash('Updated Dynamic Wordlist', 'success')
    else:
        flash('Invalid wordlist', 'danger')
    return redirect(url_for('wordlists.wordlists_list'))
