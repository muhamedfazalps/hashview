"""Flask routes to handle Settings"""
import os
from flask import Blueprint, render_template, abort, url_for, flash, request, redirect
from flask_login import login_required, current_user
import hashview
from hashview.settings.forms import HashviewSettingsForm
from hashview.models import Settings
from hashview.models import db


settings = Blueprint('settings', __name__)


def _human_size(num):
    """Human-readable byte size (e.g. 12.1 KB, 4.8 MB, 1.3 GB)."""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if num < 1024 or unit == 'TB':
            if unit == 'B':
                return '%d B' % num
            return ('%.1f %s' % (num, unit)).replace('.0 ', ' ')
        num /= 1024.0


#############################################
# Settings
#############################################

@settings.route("/settings", methods=['GET', 'POST'])
@login_required
def settings_list():
    """Function to return list of Settings"""

    if current_user.admin:
        hashview_form = HashviewSettingsForm()
        settings = Settings.query.first()

        tmp_folder_size = 0
        for file in os.scandir('hashview/control/tmp/'):
            tmp_folder_size += os.stat(file).st_size
        tmp_folder_size = _human_size(tmp_folder_size)

        if hashview_form.validate_on_submit():
            settings.retention_period = hashview_form.retention_period.data
            settings.max_runtime_jobs = hashview_form.max_runtime_jobs.data
            settings.max_runtime_tasks = hashview_form.max_runtime_tasks.data
            settings.enabled_job_weights = hashview_form.enabled_job_weights.data
            settings.crawl_min_word_length = hashview_form.crawl_min_word_length.data
            settings.crawl_user_agent = hashview_form.crawl_user_agent.data
            settings.crawl_force_lowercase = hashview_form.crawl_force_lowercase.data
            settings.crawl_depth = hashview_form.crawl_depth.data
            settings.crawl_threads = hashview_form.crawl_threads.data
            db.session.commit()
            flash('Updated Hashview settings!', 'success')
            return redirect(url_for('settings.settings_list'))
        elif request.method == 'GET':
            hashview_form.retention_period.data = settings.retention_period
            hashview_form.max_runtime_jobs.data = settings.max_runtime_jobs
            hashview_form.max_runtime_tasks.data = settings.max_runtime_tasks
            hashview_form.enabled_job_weights.data = settings.enabled_job_weights
            hashview_form.crawl_min_word_length.data = settings.crawl_min_word_length
            hashview_form.crawl_user_agent.data = settings.crawl_user_agent
            hashview_form.crawl_force_lowercase.data = settings.crawl_force_lowercase
            hashview_form.crawl_depth.data = settings.crawl_depth
            hashview_form.crawl_threads.data = settings.crawl_threads

        try:
            database_version = db.session.execute('SELECT version_num FROM alembic_version LIMIT 1;').scalar()
        except:
            database_version = 'error'

        return render_template(
            'settings.html.j2',
            title               = 'settings',
            settings            = settings,
            HashviewForm        = hashview_form,
            tmp_folder_size     = tmp_folder_size,
            application_version = hashview.__version__,
            database_version    = database_version,
        )

    abort(403)

@settings.route('/settings/clear_temp')
@login_required
def clear_temp_folder():
    """Function to clear temp folder"""
    if current_user.admin:
        for file in os.scandir('hashview/control/tmp/'):
            os.remove(file.path)
        return redirect(url_for('settings.settings_list'))

    abort(403)
