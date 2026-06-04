"""Flask routes to handle Notifications"""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from hashview.jobs.forms import JobsNewHashFileForm
from hashview.models import (
    Hashes,
    HashfileHashes,
    Hashfiles,
    HashNotifications,
    JobNotifications,
    Jobs,
    Settings,
    db,
)

notifications = Blueprint('notifications', __name__)


def _hash_type_names():
    """hashcat mode -> concise friendly name, derived from the job-hashfile
    form's own choices (same mapping the jobs views use) for the HASHTYPE badge."""
    names = {}
    form = JobsNewHashFileForm()
    for sel in (form.hash_type, form.pwdump_hash_type, form.netntlm_hash_type,
                form.kerberos_hash_type, form.shadow_hash_type):
        for value, label in sel.choices:
            if value is not None and str(value) not in names:
                name = label.split(') ', 1)[1] if ') ' in label else label
                names[str(value)] = name.split(' / ')[0].split(',')[0].strip()
    return names


@notifications.route("/notifications", methods=['GET', 'POST'])
@login_required
def notifications_list():
    """Function to return list of notifications"""
    job_notifications = JobNotifications.query.filter_by(owner_id=current_user.id).all()
    hash_notifications = HashNotifications.query.filter_by(owner_id=current_user.id).all()
    hashfiles = Hashfiles.query.all()
    jobs = Jobs.query.all()
    # id -> Hashes (dict, not list) so the template can look up by hash_id without
    # an inner loop that would emit duplicate cells if a hash has >1 notification.
    hashes = {h.id: h for h in db.session.query(Hashes)
              .join(HashNotifications, Hashes.id == HashNotifications.hash_id).all()}

    # Representative account (username) per notified hash, for the ACCOUNT column.
    # Stored hex-encoded in HashfileHashes (decoded in the template).
    hash_account = {}
    for hn in hash_notifications:
        hfh = (HashfileHashes.query
               .filter(HashfileHashes.hash_id == hn.hash_id,
                       HashfileHashes.username.isnot(None))
               .first())
        hash_account[hn.hash_id] = hfh.username if hfh else None

    # Active delivery channels for the current user (the CHANNELS KPI): the channel
    # must be enabled instance-wide AND the user must have the per-channel config.
    settings = Settings.query.first()
    channels = {
        'email': bool(settings and settings.email_enabled and current_user.email_address),
        'pushover': bool(settings and settings.pushover_enabled and current_user.pushover_app_id and current_user.pushover_user_key),
        'slack': bool(settings and settings.slack_enabled and current_user.slack_id),
    }

    return render_template('notifications.html.j2', title='Notifications',
                           job_notifications=job_notifications,
                           hash_notifications=hash_notifications,
                           jobs=jobs, hashes=hashes, hashfiles=hashfiles,
                           hash_account=hash_account,
                           hash_type_names=_hash_type_names(),
                           channels=channels)

@notifications.route("/notifications/delete/job/<int:notification_id>", methods=['GET'])
@login_required
def notifications_job_delete(notification_id):
    """Function to delete a job notification"""
    notification = JobNotifications.query.get(notification_id)
    if current_user.admin or notification.owner_id == current_user.id:
        db.session.delete(notification)
        db.session.commit()
    else:
        flash('You do not have rights to delete this notification!', 'danger')
    return redirect(url_for('notifications.notifications_list'))

@notifications.route("/notifications/delete/hash/<int:notification_id>", methods=['GET'])
@login_required
def notifications_hash_delete(notification_id):
    """Function to delete a recovered hash notification"""
    notification = HashNotifications.query.get(notification_id)
    if current_user.admin or notification.owner_id == current_user.id:
        db.session.delete(notification)
        db.session.commit()
    else:
        flash('You do not have rights to delete this notification!', 'danger')
    return redirect(url_for('notifications.notifications_list'))
