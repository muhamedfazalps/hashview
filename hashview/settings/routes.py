"""Flask routes to handle Settings"""
import os
import re
from datetime import datetime

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import current_user, login_required

import hashview
from hashview.models import Settings, db
from hashview.settings.forms import DatabaseBackupForm, HashviewSettingsForm
from hashview.utils.backup import (
    BackupError,
    create_encrypted_db_backup,
    purge_stale_backups,
)

# control/tmp filename of a generated backup, e.g. '1a2b3c4d5e6f7a8b.sql.gz.enc'
_BACKUP_TOKEN_RE = re.compile(r'^[0-9a-f]{16}\.sql\.gz\.enc$')


settings = Blueprint('settings', __name__)


def _human_size(num):
    """Human-readable byte size (e.g. 12.1 KB, 4.8 MB, 1.3 GB)."""
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if num < 1024 or unit == 'TB':
            if unit == 'B':
                return '%d B' % num
            return (f'{num:.1f} {unit}').replace('.0 ', ' ')
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
            settings.email_enabled = hashview_form.email_enabled.data
            settings.pushover_enabled = hashview_form.pushover_enabled.data
            settings.slack_enabled = hashview_form.slack_enabled.data
            settings.slack_bot_token = hashview_form.slack_bot_token.data
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
            hashview_form.email_enabled.data = settings.email_enabled
            hashview_form.pushover_enabled.data = settings.pushover_enabled
            hashview_form.slack_enabled.data = settings.slack_enabled
            hashview_form.slack_bot_token.data = settings.slack_bot_token

        try:
            database_version = db.session.execute('SELECT version_num FROM alembic_version LIMIT 1;').scalar()
        except Exception:
            database_version = 'error'

        return render_template(
            'settings.html.j2',
            title               = 'settings',
            settings            = settings,
            HashviewForm        = hashview_form,
            backupForm          = DatabaseBackupForm(),
            tmp_folder_size     = tmp_folder_size,
            application_version = hashview.__version__,
            database_version    = database_version,
        )

    abort(403)


@settings.route("/settings/backup", methods=['POST'])
@login_required
def settings_backup():
    """Generate an encrypted, gzip-compressed mysqldump of the whole database.

    Returns JSON with the one-time decryption password, a one-time download
    URL, the ciphertext sha256, and decrypt instructions. The password is only
    ever placed in this response body — never logged.
    """
    if not current_user.admin:
        abort(403)
    form = DatabaseBackupForm()
    if not form.validate_on_submit():
        return jsonify({'status': 'error', 'msg': 'Invalid or expired session token. Reload the page and try again.'}), 400

    tmp_dir = os.path.join(current_app.root_path, 'control/tmp')
    purge_stale_backups(tmp_dir)        # reap any previous undownloaded backups
    try:
        enc_path, password, sha256 = create_encrypted_db_backup(
            current_app.config['SQLALCHEMY_DATABASE_URI'], tmp_dir)
    except BackupError as exc:
        return jsonify({'status': 'error', 'msg': str(exc)}), 500
    except Exception:
        current_app.logger.exception('Database backup failed.')   # never logs the password
        return jsonify({'status': 'error', 'msg': 'Backup failed — check the server logs.'}), 500

    token = os.path.basename(enc_path)
    download_name = 'hashview-backup-' + datetime.utcnow().strftime('%Y%m%d-%H%M%S') + '.sql.gz.enc'
    instructions = [
        "Decrypt (you'll be prompted for the one-time password above):",
        "    openssl enc -d -aes-256-cbc -pbkdf2 -in " + download_name + " -out backup.sql.gz",
        "Decompress:",
        "    gunzip backup.sql.gz",
        "Restore (optional):",
        "    mysql -u <user> -p hashview < backup.sql",
        "Requires OpenSSL 1.1.1+ (the -pbkdf2 flag is mandatory on decrypt).",
    ]
    return jsonify({
        'status': 'ok',
        'password': password,
        'download_url': url_for('settings.settings_backup_download', token=token),
        'download_name': download_name,
        'sha256': sha256,
        'instructions': instructions,
    })


@settings.route("/settings/backup/download/<token>", methods=['GET'])
@login_required
def settings_backup_download(token):
    """Stream a previously generated encrypted backup as an attachment."""
    if not current_user.admin:
        abort(403)
    if not _BACKUP_TOKEN_RE.match(token):
        abort(404)
    tmp_dir = os.path.join(current_app.root_path, 'control/tmp')
    if not os.path.exists(os.path.join(tmp_dir, token)):
        abort(404)
    # Friendly, dated name derived from the file's own mtime (the token is opaque).
    try:
        stamp = datetime.utcfromtimestamp(os.path.getmtime(os.path.join(tmp_dir, token)))
        download_name = 'hashview-backup-' + stamp.strftime('%Y%m%d-%H%M%S') + '.sql.gz.enc'
    except OSError:
        download_name = 'hashview-backup.sql.gz.enc'
    return send_from_directory(tmp_dir, token, as_attachment=True,
                               download_name=download_name, mimetype='application/octet-stream')

@settings.route('/settings/clear_temp')
@login_required
def clear_temp_folder():
    """Function to clear temp folder"""
    if current_user.admin:
        for file in os.scandir('hashview/control/tmp/'):
            os.remove(file.path)
        return redirect(url_for('settings.settings_list'))

    abort(403)
