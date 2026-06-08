"""Import large wordlists copied onto the server (scp/rsync) into Hashview.

Users drop plaintext or gzip wordlists into control/wordlists_import/; the
Wordlists page lists them and an admin/user triggers a background import. Each
import reuses ingest_static_wordlist_file (so the result is identical to a GUI
upload: stored gzip-compressed at rest with size/checksum/byte_size), is
audit-logged, and the original is removed on success.

Safeguards:
- mtime quiescence: a file still being copied (mtime within QUIESCE_SECONDS)
  is left alone until it's stable.
- claim-by-rename: the file is renamed to <name>.importing before processing so
  a second trigger can't double-import it and the UI can show progress.
- plaintext/gz validation: gz is validated by the ingest; anything else must
  look like text (no NUL bytes) or it's rejected.
- failures leave a <name>.failed marker (never silently deleted) for diagnosis.
"""
import os
import time

from flask import current_app

from hashview.models import Users, db
from hashview.utils.audit import log_event
from hashview.utils.utils import ingest_static_wordlist_file, is_gzip

QUIESCE_SECONDS = 60          # a file modified more recently is treated as "still uploading"
_CLAIM_SUFFIX = '.importing'
_FAIL_SUFFIX = '.failed'
_SKIP_SUFFIXES = (_CLAIM_SUFFIX, _FAIL_SUFFIX)


def import_dir(app):
    """The on-disk drop folder for wordlist imports."""
    return os.path.join(app.root_path, 'control', 'wordlists_import')


def _human_size(num):
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if num < 1024 or unit == 'TB':
            return '%d B' % num if unit == 'B' else (f'{num:.1f} {unit}')
        num /= 1024.0


def looks_like_text_or_gz(path):
    """True if the file is a gzip stream or plausibly plaintext (no NUL bytes in
    the first 8 KB). Rejects obvious binaries placed in the drop folder."""
    if is_gzip(path):
        return True
    try:
        with open(path, 'rb') as fh:
            return b'\x00' not in fh.read(8192)
    except OSError:
        return False


def _derived_name(filename):
    """Wordlist display name from a filename: drop a trailing .gz then one ext."""
    name = filename
    if name.lower().endswith('.gz'):
        name = name[:-3]
    base = os.path.splitext(name)[0]
    return (base or name).strip() or filename


def _is_quiescent(path):
    """False while the file is still being written (mtime too recent)."""
    try:
        return (time.time() - os.path.getmtime(path)) >= QUIESCE_SECONDS
    except OSError:
        return False


def list_importable(app):
    """Cheap listing for the Wordlists page — never imports. Returns dicts:
    {name, size, uploading, status} for each candidate, plus any .failed markers."""
    directory = import_dir(app)
    out = []
    if not os.path.isdir(directory):
        return out
    for entry in os.scandir(directory):
        name = entry.name
        if name.startswith('.') or entry.is_symlink() or not entry.is_file():
            continue
        if name.endswith(_CLAIM_SUFFIX):
            out.append({'name': name[:-len(_CLAIM_SUFFIX)], 'size': '', 'uploading': False, 'status': 'importing'})
            continue
        if name.endswith(_FAIL_SUFFIX):
            out.append({'name': name[:-len(_FAIL_SUFFIX)], 'size': '', 'uploading': False, 'status': 'failed'})
            continue
        try:
            size = _human_size(entry.stat().st_size)
        except OSError:
            size = ''
        out.append({'name': name, 'size': size,
                    'uploading': not _is_quiescent(entry.path), 'status': 'pending'})
    out.sort(key=lambda f: f['name'].lower())
    return out


def run_import(app, filenames, owner_id):
    """Import the named drop-folder files. Returns a summary dict
    {imported, skipped, failed}. Each file is handled independently so one bad
    file never aborts the batch.

    MUST run inside an active app context (it uses the request-scoped DB
    session and the audit logger). The route's background thread reaches this
    via run_import_async, which establishes the context; tests call it
    directly inside the test's app context."""
    directory = import_dir(app)
    user = Users.query.get(owner_id)
    actor = (user.email_address, user.id) if user else (None, None)
    summary = {'imported': [], 'skipped': [], 'failed': []}

    for raw in filenames:
        fname = os.path.basename(raw or '')   # never trust the posted name
        if not fname or fname.startswith('.') or fname.endswith(_SKIP_SUFFIXES):
            continue
        src = os.path.join(directory, fname)
        if not os.path.isfile(src) or os.path.islink(src):
            summary['skipped'].append(fname)
            continue
        if not _is_quiescent(src):
            # still being copied — leave it for a later run
            summary['skipped'].append(fname)
            continue

        claimed = src + _CLAIM_SUFFIX
        try:
            os.rename(src, claimed)            # atomic claim; prevents double-import
        except OSError:
            summary['skipped'].append(fname)   # lost the race / vanished
            continue

        try:
            if not looks_like_text_or_gz(claimed):
                raise ValueError('not a plaintext or gzip wordlist')
            row = ingest_static_wordlist_file(claimed, owner_id, _derived_name(fname))
            db.session.add(row)
            db.session.commit()
            log_event('wordlist.create', actor=actor,
                      target=f'wordlist:{row.id} {row.name!r}',
                      detail='imported from drop folder')
            os.remove(claimed)                 # success — drop the original
            summary['imported'].append(fname)
        except Exception as exc:               # noqa: BLE001 - per-file isolation
            db.session.rollback()
            current_app.logger.exception('Wordlist import failed: %s', fname)
            log_event('wordlist.import_failed', outcome='failure', actor=actor,
                      detail=f'{fname}: {exc}')
            try:
                os.replace(claimed, src + _FAIL_SUFFIX)   # keep for diagnosis
            except OSError:
                pass
            summary['failed'].append(fname)
    return summary


def run_import_async(app, filenames, owner_id):
    """Thread target: establish a fresh app context (and thus a clean scoped DB
    session) for the background import, then run it."""
    with app.app_context():
        return run_import(app, filenames, owner_id)
