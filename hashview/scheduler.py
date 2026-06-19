"""Function file to scheduler"""
from functools import partial
from logging import Logger

from flask import Flask
from flask_apscheduler import APScheduler
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy

scheduler = APScheduler()


def try_send_email(user, subject :str, plaintext_body :str, mailer :Mail) -> bool:
    """ try to send an email, returning an error message on failure """

    error = 'unknown error'
    try:
        error = f"failed to get user's email address from user: {user!r}"
        address = user.email_address

        error = f"failed to create message from: {subject} | {address} | {plaintext_body}"
        message = Message(
            subject    = subject,
            recipients = [ address, ],
            body       = plaintext_body,
        )

        error = f"failed to send message with mailer: {mailer!r}"
        mailer.send(message)

    except Exception:
        return error

    return None


def _data_retention_cleanup_inner(db :SQLAlchemy, mailer :Mail, logger :Logger):
    """ description needed """

    import time
    from datetime import datetime, timedelta
    from pathlib import Path
    from textwrap import dedent

    from hashview.models import (
        Hashes,
        HashfileHashes,
        Hashfiles,
        HashNotifications,
        JobNotifications,
        Jobs,
        JobTasks,
        Settings,
        Users,
    )

    try_send_email_ = partial(try_send_email, mailer=mailer)

    logger.debug('I am retaining all the data: %s', datetime.now())

    setting = Settings.query.get('1')
    retention_period = setting.retention_period
    filter_after = datetime.today() - timedelta(days = retention_period)

    # Remove job, job tasks and job notifications
    jobs = Jobs.query.filter(Jobs.created_at < filter_after).all()
    for job in jobs:
        # Send email saying we've deleted their job
        user = Users.query.get(job.owner_id)
        subject = f'Hashview removed an old job: {job.name}'
        message = dedent(f'''\
            Hello {user.first_name},

            In accordance to the data retention policy of {retention_period} days,
            your job "{job.name}" was deleted.
        ''')
        if (error := try_send_email_(user, subject, message)):
            logger.error(error)

        JobTasks.query.filter_by(job_id=job.id).delete()
        JobNotifications.query.filter_by(job_id=job.id).delete()

        db.session.delete(job)
        db.session.commit()

        logger.debug("Job Name: %s  Owner ID: %s has been Deleted", job.name, job.owner_id)

    # Remove Hashfiles (jobs younger than the retention period that reference
    # these hashfiles get removed too).
    hashfiles = Hashfiles.query.filter(Hashfiles.uploaded_at < filter_after).all()
    for hashfile in hashfiles:
        # Job, jobtask and job notifications
        jobs = Jobs.query.filter_by(hashfile_id = hashfile.id).all()
        for job in jobs:
            logger.debug("Hashfile->jobs: Job Name: %s", job.name)
            user = Users.query.get(job.owner_id)
            subject = f'Hashview removed a job that was associated to an old hash file: {job.name}'
            message = dedent(f'''\
                Hello ' + str(user.first_name) + ',

                In accordance to the data retention policy of {retention_period} days,
                your hashfile "{hashfile.name}" was associated with a job "{job.name}".
                This job was deleted.
            ''')
            if (error := try_send_email_(user, subject, message)):
                logger.error(error)

            JobTasks.query.filter_by(job_id=job.id).delete()
            JobNotifications.query.filter_by(job_id=job.id).delete()

            db.session.delete(job)
            db.session.commit()

            logger.debug(
                "Job Name: %s  Owner ID: %s has been Deleted, "
                "it was associated with Hashfile ID: %s, Hashfile Name: %s",
                job.name, job.owner_id, hashfile.id, hashfile.name,
            )

        # Hashfiles, HashfileHashes and Hash notifications
        logger.debug('Hashfile Name: %s    Owner ID: %s', hashfile.name, hashfile.owner_id)
        logger.debug('Hashfile ID: %s', hashfile.id)
        user = Users.query.get(hashfile.owner_id)
        subject = f'Hashview removed an old Hashfile: {hashfile.name}'
        message = dedent(f'''\
            Hello {user.first_name},

            In accordance to the data retention policy of {retention_period} days,
            your hashfile "{hashfile.name}" was removed.
        ''')
        if (error := try_send_email_(user, subject, message)):
            logger.error(error)

        hashfile_hashes = HashfileHashes.query.filter_by(hashfile_id = hashfile.id).all()
        for hashfile_hash in hashfile_hashes:
            # Capture the id BEFORE deleting anything: a commit/flush expires this
            # instance, and the DB-level hashfile_hashes.hash_id -> hashes.id FK
            # (ON DELETE CASCADE) removes this row when its hash is deleted, so its
            # attributes must not be read afterwards (that raised ObjectDeletedError).
            hash_id = hashfile_hash.hash_id
            db.session.delete(hashfile_hash)
            db.session.flush()  # apply the association delete before the orphan check below

            # Purge the underlying hash only if it is now unreferenced by ANY hashfile
            # and is uncracked (cracked recoveries are kept for reporting). delete()
            # returns the affected row count, so notifications are cleared only when the
            # hash actually was. The post-delete count() is dialect-independent, unlike
            # the old .distinct('hashfile_id') (a no-op outside PostgreSQL).
            if HashfileHashes.query.filter_by(hash_id=hash_id).count() == 0:
                if Hashes.query.filter_by(id=hash_id, cracked=0).delete():
                    HashNotifications.query.filter_by(hash_id=hash_id).delete()
        db.session.delete(hashfile)
        db.session.commit()

        logger.debug(
            "Hashfile ID: %s  Hashfile Name: %s has been Deleted",
            hashfile.id, hashfile.name,
        )

    # Clean temp folder of files older than RETENTION PERIOD
    tmp_directory = Path('hashview/control/tmp').resolve()
    retention_limit = time.time() - retention_period * 86400
    # Encrypted one-time DB backups are single-use and contain the whole
    # database; reap them within an hour regardless of the (day-granular)
    # retention period so an un-downloaded backup never lingers.
    backup_limit = time.time() - 3600
    for child in tmp_directory.iterdir():
        if '.gitignore' == child.name:
            logger.debug(
                'DataRetentionCleanup.TempFile Progressing with StepResult(Ignored: %s).',
                child,
            )
            continue

        limit = backup_limit if child.name.endswith('.sql.gz.enc') else retention_limit
        if child.stat().st_mtime < limit:
            child.unlink()
            logger.debug(
                'DataRetentionCleanup.TempFile Progressing with StepResult(Removed: %s).',
                child,
            )
            continue

        logger.debug(
            'DataRetentionCleanup.TempFile Progressing with StepResult(LeftAlone: %s).',
            child,
        )


def data_retention_cleanup(app :Flask):
    """ Function to manage retention cleanup """
    with app.app_context():
        try:
            app.logger.info('DataRetentionCleanup ScheduledJob Progressing.')

            # db is already registered on the app in create_app(); re-running
            # db.init_app(app) here raises in Flask-SQLAlchemy 3.x
            # ("instance has already been registered"), which aborted the whole
            # cleanup every hour. The app_context above is all that's needed.
            from hashview.models import db

            mailer = app.extensions['mail']
            logger = app.logger
            _data_retention_cleanup_inner(db, mailer, logger)

        except Exception:
            app.logger.exception(
                'DataRetentionCleanup ScheduledJob is Complete with Result(Failure).')

        else:
            app.logger.info(
                'DataRetentionCleanup ScheduledJob is Complete with Result(Success).')
