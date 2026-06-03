"""Encrypted MySQL database backup for the Settings -> Data management feature.

Produces a `mysqldump | gzip -9 | openssl enc -aes-256-cbc` artifact encrypted
with a freshly generated one-time password. Hardened per the design pre-mortem:

  - The DB password is passed to mysqldump via a 0600 ``--defaults-extra-file``
    created atomically (``mkstemp``), never on the command line, and unlinked
    in a ``finally``.
  - The one-time encryption password is given ONLY to the openssl child via a
    scoped ``env`` (never mutating the parent process env, never on argv), so
    it can't leak to the mysqldump/gzip children or the web worker.
  - EVERY pipeline stage's return code is checked. A shell-less pipe does NOT
    fail when an upstream stage (mysqldump) dies, so without this a failed dump
    would be delivered as a valid-looking but empty/truncated "backup". On any
    failure the partial output is deleted and a BackupError is raised.
  - The encrypted output is created 0600 and a short-TTL sweep removes stale
    backups so a full encrypted DB never lingers in control/tmp.
"""
import hashlib
import os
import secrets
import shutil
import subprocess
import tempfile
import time

from sqlalchemy.engine.url import make_url


class BackupError(Exception):
    """Raised when a database backup cannot be produced."""


# Older encrypted backups are reaped after this many seconds (also enforced by
# the hourly retention cron); keeps un-downloaded full-DB dumps from lingering.
BACKUP_TTL_SECONDS = 3600
_MIN_BACKUP_BYTES = 64          # an empty openssl stream is ~48 bytes
_CHUNK = 1024 * 1024


def _require_tools():
    missing = [t for t in ('mysqldump', 'gzip', 'openssl') if shutil.which(t) is None]
    if missing:
        raise BackupError('Missing required tool(s): ' + ', '.join(missing))


def _write_defaults_file(url, tmp_dir):
    """Write a 0600 MySQL [client] defaults file (atomic create via mkstemp)."""
    # MySQL option-file double-quote syntax: '#' starts a comment, trailing
    # whitespace is trimmed, and backslash escapes are processed — so any
    # value (esp. the password) must be double-quoted with \\ and \" escaped,
    # or a password containing '#'/backslash/trailing-space would be silently
    # mis-parsed and mysqldump would fail to authenticate.
    def _q(value):
        return '"' + str(value).replace('\\', '\\\\').replace('"', '\\"') + '"'

    fd, path = tempfile.mkstemp(suffix='.cnf', dir=tmp_dir)   # 0600 by creation
    try:
        lines = ['[client]']
        if url.host:
            lines.append('host=' + _q(url.host))
        if url.port:                                          # omit when None (default config has no port)
            lines.append('port=' + str(url.port))            # numeric — no quoting needed
        lines.append('user=' + _q(url.username or ''))
        lines.append('password=' + _q(url.password or ''))
        os.write(fd, ('\n'.join(lines) + '\n').encode('utf-8'))
    finally:
        os.close(fd)
    return path


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(_CHUNK), b''):
            h.update(block)
    return h.hexdigest()


def _run_pipeline(dump_cmd, enc_path, password):
    """mysqldump(dump_cmd) | gzip -9 | openssl enc -> enc_path (0600).

    Raises BackupError unless every stage exits 0 and output is non-trivial.
    """
    gzip_bin = shutil.which('gzip') or 'gzip'
    openssl_bin = shutil.which('openssl') or 'openssl'

    dump_err = tempfile.TemporaryFile()
    # Create the output 0600 and atomically (O_EXCL); openssl writes via this fd.
    out_fd = os.open(enc_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    p1 = p2 = p3 = None
    try:
        p1 = subprocess.Popen(dump_cmd, stdout=subprocess.PIPE, stderr=dump_err)
        p2 = subprocess.Popen([gzip_bin, '-9', '-c'], stdin=p1.stdout, stdout=subprocess.PIPE)
        p3 = subprocess.Popen(
            [openssl_bin, 'enc', '-aes-256-cbc', '-pbkdf2', '-salt', '-pass', 'env:HV_BK_PASS'],
            stdin=p2.stdout, stdout=out_fd, stderr=subprocess.PIPE,
            env={**os.environ, 'HV_BK_PASS': password},      # passphrase ONLY to openssl
        )
        # Let upstream stages receive SIGPIPE if a downstream stage exits.
        p1.stdout.close()
        p2.stdout.close()
    finally:
        os.close(out_fd)

    _, ossl_err = p3.communicate()
    rc3 = p3.returncode
    rc2 = p2.wait()
    rc1 = p1.wait()
    dump_err.seek(0)
    derr = dump_err.read().decode('utf-8', 'replace').strip()
    dump_err.close()

    if rc1 != 0:
        first = derr.splitlines()[0] if derr else ''
        raise BackupError('Database dump failed (mysqldump exit %d). %s' % (rc1, first))
    if rc2 != 0:
        raise BackupError('Backup compression failed (gzip exit %d).' % rc2)
    if rc3 != 0:
        msg = (ossl_err or b'').decode('utf-8', 'replace').strip().splitlines()
        raise BackupError('Backup encryption failed (openssl exit %d). %s' % (rc3, msg[0] if msg else ''))
    if os.path.getsize(enc_path) < _MIN_BACKUP_BYTES:
        raise BackupError('Backup produced no data.')


def purge_stale_backups(tmp_dir, max_age_seconds=BACKUP_TTL_SECONDS):
    """Best-effort removal of *.sql.gz.enc older than max_age_seconds."""
    try:
        cutoff = time.time() - max_age_seconds
        for name in os.listdir(tmp_dir):
            if name.endswith('.sql.gz.enc'):
                p = os.path.join(tmp_dir, name)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                except OSError:
                    pass
    except OSError:
        pass


def create_encrypted_db_backup(db_uri, tmp_dir, dump_cmd=None):
    """Create an encrypted, gzip-compressed mysqldump of the Hashview database.

    Returns (enc_path, password, sha256_hex). The caller serves enc_path and
    shows the password + sha256 once. ``dump_cmd`` overrides the dump stage
    (used by tests to avoid requiring a live MySQL).
    """
    _require_tools()
    url = make_url(db_uri)
    if not url.get_backend_name().startswith('mysql'):
        raise BackupError('Database backup is only supported for MySQL deployments.')

    password = secrets.token_urlsafe(24)        # ~143 bits, URL-safe (shell/quoting-safe)
    enc_path = os.path.join(tmp_dir, secrets.token_hex(8) + '.sql.gz.enc')
    cnf_path = None
    try:
        if dump_cmd is None:
            cnf_path = _write_defaults_file(url, tmp_dir)
            dump_cmd = [
                'mysqldump',
                '--defaults-extra-file=' + cnf_path,
                '--single-transaction',
                '--routines',
                '--triggers',
                '--events',
                '--no-tablespaces',
                '--set-gtid-purged=OFF',        # so the dump restores into a fresh DB without SUPER
                url.database or 'hashview',
            ]
        _run_pipeline(dump_cmd, enc_path, password)
    except Exception:
        if os.path.exists(enc_path):
            try:
                os.remove(enc_path)
            except OSError:
                pass
        raise
    finally:
        if cnf_path and os.path.exists(cnf_path):
            try:
                os.remove(cnf_path)
            except OSError:
                pass

    return enc_path, password, _sha256(enc_path)
