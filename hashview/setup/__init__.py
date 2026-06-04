import os
import secrets

from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy

from hashview.models import Rules, Settings, Tasks, Users, Wordlists
from hashview.utils.utils import (
    compress_to_gz,
    get_filehash,
    get_filesize,
    get_linecount,
    is_gzip,
)

DEFAULT_PASSWORD = 'hashview'


def default_tasks_need_added(db :SQLAlchemy) -> bool:
    return (0 == db.session.query(Tasks).count())


def add_default_tasks(db :SQLAlchemy):
    task = Tasks(
        name          = 'Rockyou Wordlist',
        owner_id      = '1',
        wl_id         = '2',
        rule_id       = None,
        hc_attackmode = 0,
    )
    db.session.add(task)

    task = Tasks(
        name          = 'Rockyou Wordlist + Best64 Rules',
        owner_id      = '1',
        wl_id         = '3',
        rule_id       = '1',
        hc_attackmode = 0,
    )
    db.session.add(task)

    # mask mode of all 8 characters
    task = Tasks(
        name          = '?a?a?a?a?a?a?a?a [8]',
        owner_id      = '1',
        wl_id         = None,
        rule_id       = None,
        hc_attackmode = 3,
        hc_mask       = '?a?a?a?a?a?a?a?a',
    )
    db.session.add(task)

    db.session.commit()


def default_rules_need_added(db :SQLAlchemy) -> bool:
    return (0 == db.session.query(Rules).count())


def add_default_rules(db :SQLAlchemy):
    os.system('gzip -d -k install/best64.rule.gz')
    rules_path = 'hashview/control/rules/best64.rule'
    os.replace('install/best64.rule', rules_path)
    rule = Rules(
        name     = 'Best64 Rule',
        owner_id = 1,
        path     = rules_path,
        checksum = get_filehash(rules_path),
        size     = get_linecount(rules_path),
    )
    db.session.add(rule)
    db.session.commit()


def default_static_wordlist_need_added(db :SQLAlchemy) -> bool:
    return (0 == db.session.query(Wordlists).filter_by(type='static').count())


def add_default_static_wordlist(db :SQLAlchemy):
    os.system('gzip -d -k install/rockyou.txt.gz')
    wordlist_path = 'hashview/control/wordlists/rockyou.txt'
    os.replace('install/rockyou.txt', wordlist_path)
    wordlist = Wordlists(
        name     = 'Rockyou.txt',
        owner_id = 1,
        type     = 'static',
        path     = wordlist_path,                # Can we make this a relative path?
        checksum = get_filehash(wordlist_path),
        size     = get_linecount(wordlist_path),
    )
    db.session.add(wordlist)
    db.session.commit()


def compress_existing_wordlists_if_needed(db :SQLAlchemy):
    """One-time-per-row migration to compressed-at-rest wordlist storage.

    Wordlists are now stored gzip-compressed (gzip -9). Installs that predate
    this change have uncompressed static wordlists on disk; this brings them
    in line on startup:

      - static + not gzip  -> compress to '<hex>.gz', set checksum = sha256 of
        the COMPRESSED file (the contract the agent verifies), recompute the
        line count with the SAME semantics as before (no drift), record
        byte_size, commit, THEN delete the old plaintext (write->commit->delete
        is crash-safe). The default Rockyou.txt seeded just before this runs is
        compressed by this same pass.
      - static + already gzip -> idempotent skip; only backfill byte_size if NULL.
      - dynamic -> never compressed (kept uncompressed on the server); only
        backfill byte_size if NULL.

    Idempotent (the gzip magic-byte check makes re-runs no-ops) and resilient:
    each row is handled in its own try/except with a per-row commit, a missing
    file is logged and skipped (never deletes the DB row), and any failure is
    contained so it can never abort startup.
    """
    from flask import current_app
    logger = current_app.logger

    for wordlist in db.session.query(Wordlists).all():
        try:
            path = wordlist.path
            if not path or not os.path.exists(path):
                logger.warning('Wordlist %s file missing (%s); skipping compression.', wordlist.id, path)
                continue

            if wordlist.type == 'dynamic':
                # Dynamic wordlists stay uncompressed; just backfill byte_size.
                if wordlist.byte_size is None:
                    wordlist.byte_size = get_filesize(path)
                    db.session.commit()
                continue

            # static
            if is_gzip(path):
                # Already compressed (new uploads, or a prior run). No-op aside
                # from backfilling byte_size if it was never recorded.
                if wordlist.byte_size is None:
                    wordlist.byte_size = get_filesize(path)
                    db.session.commit()
                continue

            # static + uncompressed: compress in place (new file in same dir).
            line_count = get_linecount(path)
            new_gz = os.path.join(os.path.dirname(path), secrets.token_hex(8) + '.gz')
            compress_to_gz(path, new_gz, 9)

            # write -> commit -> delete: only remove the old plaintext after the
            # new path/checksum are durably committed.
            wordlist.path = new_gz
            wordlist.size = line_count
            wordlist.checksum = get_filehash(new_gz)     # sha256 of the .gz
            wordlist.byte_size = get_filesize(new_gz)
            db.session.commit()

            if os.path.exists(path):
                os.remove(path)
            logger.info('Compressed static wordlist %s -> %s', wordlist.id, new_gz)
        except Exception:
            db.session.rollback()
            logger.exception('Failed to compress wordlist %s; leaving it untouched.', getattr(wordlist, 'id', '?'))


# The canonical dynamic wordlists. Order matters only for the seed-file
# layout; the dispatcher in hashview/utils/utils.py:update_dynamic_wordlist
# routes by substring (Passwords/Usernames/Customers/NTLM/Website).
_DYNAMIC_WORDLISTS = (
    ('(DYNAMIC) All Recovered Passwords', 'hashview/control/wordlists/dynamic-all.txt'),
    ('(DYNAMIC) All Usernames',           'hashview/control/wordlists/dynamic-usernames.txt'),
    ('(DYNAMIC) All Customers',           'hashview/control/wordlists/dynamic-customers.txt'),
    ('(DYNAMIC) All NTLM Hashes',         'hashview/control/wordlists/dynamic-ntlm.txt'),
    ('(DYNAMIC) Website Keywords',        'hashview/control/wordlists/dynamic-website-keywords.txt'),
)


def default_dynamic_wordlists_need_added(db :SQLAlchemy) -> bool:
    """True when any of the canonical (DYNAMIC) wordlists is missing.

    Replaces the previous all-or-nothing gate (count==0) so existing
    installs that already have the older 3 dynamic wordlists still get the
    new "(DYNAMIC) All NTLM Hashes" entry on next startup.
    """
    wanted = {name for name, _ in _DYNAMIC_WORDLISTS}
    present = {
        w.name for w in
        db.session.query(Wordlists).filter(Wordlists.name.in_(wanted)).all()
    }
    return bool(wanted - present)


def add_default_dynamic_wordlists(db :SQLAlchemy):
    """Ensure each canonical (DYNAMIC) wordlist exists; idempotent per name.

    Skips entries that are already in the DB so this can run safely on every
    startup. The previous implementation always inserted all four rows,
    which is why the gate had to be all-or-nothing.
    """
    for name, path in _DYNAMIC_WORDLISTS:
        if db.session.query(Wordlists).filter_by(name=name).first() is not None:
            continue
        # 'w' opens for writing and truncates — fine for a placeholder seed.
        with open(path, mode='w'):
            pass
        db.session.add(Wordlists(
            name     = name,
            owner_id = 1,
            type     = 'dynamic',
            path     = path,
            checksum = get_filehash(path),
            size     = 0,
        ))
    db.session.commit()


def admin_user_needs_added(db :SQLAlchemy) -> bool:
    return (0 >= db.session.query(Users).filter_by(admin=True).count())


def add_admin_user(db :SQLAlchemy, bcrypt :Bcrypt):
    default_password_hash = bcrypt.generate_password_hash(DEFAULT_PASSWORD).decode('utf-8')
    user = Users(
        first_name    = 'admin',
        last_name     = 'user',
        email_address = '',
        password      = default_password_hash,
        admin         = True,
    )
    db.session.add(user)
    db.session.commit()


def admin_pass_needs_changed(db :SQLAlchemy, bcrypt :Bcrypt) -> bool:
    result = db.session.query(Users.password).filter_by(id=1).first()
    if result is None:
        return True
    current_password_hash, *_ = result
    return bcrypt.check_password_hash(current_password_hash, DEFAULT_PASSWORD)


def settings_needs_added(db :SQLAlchemy) -> bool:
    settings = db.session.query(Settings).first()
    return settings is None
