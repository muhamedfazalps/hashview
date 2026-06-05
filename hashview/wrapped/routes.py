import datetime

from flask import Blueprint, render_template
from flask_login import current_user, login_required
from sqlalchemy import func

from hashview.models import Hashes, Tasks, Users, db

wrapped = Blueprint('wrapped', __name__)

@wrapped.route("/wrapped", methods=['GET'])
@login_required
def wrapped_list():
    """Render the Wrapped statistics page with various hash recovery metrics.

    This route is protected by ``login_required`` and collects data for the
    previous calendar year. It gathers statistics such as longest recovered
    passwords, most recovered passwords, hash type specific counts, and the
    most effective tasks. The collected data is passed to the
    ``wrapped.html`` template for rendering.
    """

    # Determine the calendar year for which statistics are displayed (previous year)
    # Build start and end date strings for the query range
    # Get previous year (will need to update this once we're ready to go live)
    year = datetime.datetime.now().year
    date_start = str(year) + '-01-01'
    date_end = str(year) + '-12-31'

    # Hash types excluded from "longest password" rankings (network protocol hashes).
    excluded_hash_types_for_length = (7500, 27000, 27100, 31500, 31600, 35300, 35400)

    # ---- Longest recovered passwords (global ranking, top 10 by length) ----
    longest_password_all_table_raw = (
        db.session.query(Hashes.plaintext, Hashes.recovered_at, Users.email_address)
        .join(Users, Hashes.recovered_by == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type.notin_(excluded_hash_types_for_length))
        .order_by(func.length(Hashes.plaintext).desc(), Hashes.recovered_at.asc())
        .limit(10)
        .all()
    )

    longest_password_all_table = []
    for entry in longest_password_all_table_raw:
        dict_entry = {}
        dict_entry['length'] = len(entry.plaintext or '')
        dict_entry['recovered_at'] = entry.recovered_at
        dict_entry['plaintext'] = entry.plaintext
        dict_entry['email_address'] = entry.email_address
        longest_password_all_table.append(dict_entry)

    # ---- Longest recovered password for the current user ----
    longest_password_personal_raw = (
        db.session.query(Hashes.plaintext)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .order_by(func.length(Hashes.plaintext).desc(), Hashes.recovered_at.asc())
        .filter(Hashes.recovered_by == current_user.id)
        .first()
    )

    if longest_password_personal_raw:
        longest_password_personal = longest_password_personal_raw.plaintext
    else:
        longest_password_personal = ''

    # ---- Current user's rank among all users' longest passwords ----
    longest_password_all_raw = (
        db.session.query(Hashes.plaintext, Hashes.recovered_by)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .order_by(func.length(Hashes.plaintext).desc())
        .all()
    )

    longest_password_all_cnt = max(len(longest_password_all_raw) - 1, 0)
    longest_password_personal_rank = 1
    for entry in longest_password_all_raw:
        if entry.recovered_by == current_user.id:
            break
        if entry.recovered_by is not None:
            longest_password_personal_rank += 1

    # ---- Top 10 users by total passwords recovered ----
    most_passwords_recovered_all_raw = (
        db.session.query(
            Hashes.recovered_by,
            Users.email_address,
            func.count(Hashes.id).label("row_count"),
        )
        .join(Users, Hashes.recovered_by == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    most_passwords_recovered_all_table = []
    for entry in most_passwords_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        most_passwords_recovered_all_table.append(dict_entry)

    # ---- Current user's percentile rank by total passwords recovered ----
    total_passwords_recovered = (
        db.session.query(Hashes.recovered_by)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .all()
    )

    total_passwords_recovered_personal_pct = 0
    personal_group_by_pos = len(total_passwords_recovered) - 1
    for entry in total_passwords_recovered:
        if entry.recovered_by == current_user.id:
            total_passwords_recovered_personal_pct = round(
                personal_group_by_pos / (len(total_passwords_recovered) - 1 or 1), 2) * 100
            break
        personal_group_by_pos -= 1

    total_passwords_recovered_personal_cnt = (
        db.session.query(Hashes.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.recovered_by == current_user.id)
        .count()
    )

    # ---- NTLM (hash_type 1000) — top 10 users + personal percentile/count ----
    total_ntlm_recovered_all_raw = (
        db.session.query(
            Hashes.recovered_by,
            Users.email_address,
            func.count(Hashes.id).label("row_count"),
        )
        .join(Users, Hashes.recovered_by == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type == 1000)
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    total_ntlm_recovered_all_table = []
    for entry in total_ntlm_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_ntlm_recovered_all_table.append(dict_entry)

    total_ntlm_recovered_all = (
        db.session.query(Hashes.recovered_by)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type == 1000)
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .all()
    )

    total_ntlm_recovered_personal_pct = 0
    personal_group_by_pos = len(total_ntlm_recovered_all) - 1
    for entry in total_ntlm_recovered_all:
        if entry.recovered_by == current_user.id:
            total_ntlm_recovered_personal_pct = round(
                personal_group_by_pos / (len(total_ntlm_recovered_all) - 1 or 1), 2) * 100
            break
        personal_group_by_pos -= 1

    total_ntlm_recovered_personal_cnt = (
        db.session.query(Hashes.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.recovered_by == current_user.id)
        .filter(Hashes.hash_type == 1000)
        .count()
    )

    # ---- NetNTLMv1 (hash_type 5500/27000) — top 10 users + personal percentile/count ----
    ntlmv1_hash_types = (5500, 27000)

    total_ntlmv1_recovered_all_raw = (
        db.session.query(
            Hashes.recovered_by,
            Users.email_address,
            func.count(Hashes.id).label("row_count"),
        )
        .join(Users, Hashes.recovered_by == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type.in_(ntlmv1_hash_types))
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    total_ntlmv1_recovered_all_table = []
    for entry in total_ntlmv1_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_ntlmv1_recovered_all_table.append(dict_entry)

    total_ntlmv1_recovered_all = (
        db.session.query(Hashes.recovered_by)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type.in_(ntlmv1_hash_types))
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .all()
    )

    total_ntlmv1_recovered_personal_pct = 0
    personal_group_by_pos = len(total_ntlmv1_recovered_all) - 1
    for entry in total_ntlmv1_recovered_all:
        if entry.recovered_by == current_user.id:
            total_ntlmv1_recovered_personal_pct = round(
                personal_group_by_pos / (len(total_ntlmv1_recovered_all) - 1 or 1), 2) * 100
        else:
            personal_group_by_pos -= 1

    total_ntlmv1_recovered_personal_cnt = (
        db.session.query(Hashes.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.recovered_by == current_user.id)
        .filter(Hashes.hash_type.in_(ntlmv1_hash_types))
        .count()
    )

    # ---- NetNTLMv2 (hash_type 5600/27100) — top 10 users + personal percentile/count ----
    ntlmv2_hash_types = (5600, 27100)
    ntlmv1_v2_all_hash_types = (5500, 5600, 27000, 27100)

    total_ntlmv2_recovered_all_raw = (
        db.session.query(
            Hashes.recovered_by,
            Users.email_address,
            func.count(Hashes.id).label("row_count"),
        )
        .join(Users, Hashes.recovered_by == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type.in_(ntlmv2_hash_types))
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    total_ntlmv2_recovered_all_table = []
    for entry in total_ntlmv2_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_ntlmv2_recovered_all_table.append(dict_entry)

    total_ntlmv2_recovered_all = (
        db.session.query(Hashes.recovered_by)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type.in_(ntlmv2_hash_types))
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .all()
    )

    total_ntlmv2_recovered_personal_pct = 0
    personal_group_by_pos = len(total_ntlmv2_recovered_all) - 1
    for entry in total_ntlmv2_recovered_all:
        if entry.recovered_by == current_user.id:
            total_ntlmv2_recovered_personal_pct = round(
                personal_group_by_pos / (len(total_ntlmv2_recovered_all) - 1 or 1), 2) * 100
        else:
            personal_group_by_pos -= 1

    total_ntlmv2_recovered_personal_cnt = (
        db.session.query(Hashes.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.recovered_by == current_user.id)
        .filter(Hashes.hash_type.in_(ntlmv1_v2_all_hash_types))
        .count()
    )

    # ---- Kerberos (multiple hash types) — top 10 users + personal percentile/count ----
    kerberos_hash_types = (7500, 13100, 18200, 19600, 19700, 19800, 19900)

    total_kerberos_recovered_all_raw = (
        db.session.query(
            Hashes.recovered_by,
            Users.email_address,
            func.count(Hashes.id).label("row_count"),
        )
        .join(Users, Hashes.recovered_by == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type.in_(kerberos_hash_types))
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    total_kerberos_recovered_all_table = []
    for entry in total_kerberos_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_kerberos_recovered_all_table.append(dict_entry)

    total_kerberos_recovered_all = (
        db.session.query(
            Hashes.recovered_by,
            func.count(Hashes.id).label("row_count"),
        )
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type.in_(kerberos_hash_types))
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .all()
    )

    total_kerberos_recovered_personal_pct = 0
    for entry in total_kerberos_recovered_all:
        if entry.recovered_by == current_user.id:
            total_kerberos_recovered_personal_pct = round(
                entry.row_count / (len(total_kerberos_recovered_all) - 1 or 1), 2) * 100

    total_kerberos_recovered_personal_cnt = (
        db.session.query(Hashes.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.recovered_by == current_user.id)
        .filter(Hashes.hash_type.in_(kerberos_hash_types))
        .count()
    )

    # ---- DCC2 (hash_type 2100) — top 10 users + personal percentile/count ----
    total_dcc2_recovered_all_raw = (
        db.session.query(
            Hashes.recovered_by,
            Users.email_address,
            func.count(Hashes.id).label("row_count"),
        )
        .join(Users, Hashes.recovered_by == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type == 2100)
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    total_dcc2_recovered_all_table = []
    for entry in total_dcc2_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_dcc2_recovered_all_table.append(dict_entry)

    total_dcc2_recovered_all = (
        db.session.query(
            Hashes.recovered_by,
            func.count(Hashes.id).label("row_count"),
        )
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.hash_type == 2100)
        .group_by(Hashes.recovered_by)
        .order_by(func.count(Hashes.id).desc())
        .all()
    )

    total_dcc2_recovered_personal_pct = 0
    for entry in total_dcc2_recovered_all:
        if entry.recovered_by == current_user.id:
            total_dcc2_recovered_personal_pct = round(
                entry.row_count / (len(total_dcc2_recovered_all) - 1 or 1), 2) * 100

    total_kerberos_dcc2_personal_cnt = (
        db.session.query(Hashes.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.recovered_by == current_user.id)
        .filter(Hashes.hash_type == 2100)
        .count()
    )

    # ---- Most effective tasks (overall, then per-hash-type) ----
    most_effective_tasks_raw = (
        db.session.query(
            func.count(Hashes.id).label("row_count"),
            Tasks.name,
            Users.email_address,
        )
        .join(Tasks, Hashes.task_id == Tasks.id)
        .join(Users, Tasks.owner_id == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.task_id.isnot(None))
        .group_by(Hashes.task_id)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    most_effective_tasks_table = []
    for entry in most_effective_tasks_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_table.append(dict_entry)

    most_effective_tasks_ntlm_raw = (
        db.session.query(
            func.count(Hashes.id).label("row_count"),
            Tasks.name,
            Users.email_address,
        )
        .join(Tasks, Hashes.task_id == Tasks.id)
        .join(Users, Tasks.owner_id == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.task_id.isnot(None))
        .filter(Hashes.hash_type == 1000)
        .group_by(Hashes.task_id)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    most_effective_tasks_ntlm_table = []
    for entry in most_effective_tasks_ntlm_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_ntlm_table.append(dict_entry)

    most_effective_tasks_ntlmv1_raw = (
        db.session.query(
            func.count(Hashes.id).label("row_count"),
            Tasks.name,
            Users.email_address,
        )
        .join(Tasks, Hashes.task_id == Tasks.id)
        .join(Users, Tasks.owner_id == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.task_id.isnot(None))
        .filter(Hashes.hash_type.in_(ntlmv1_hash_types))
        .group_by(Hashes.task_id)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    most_effective_tasks_ntlmv1_table = []
    for entry in most_effective_tasks_ntlmv1_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_ntlmv1_table.append(dict_entry)

    most_effective_tasks_ntlmv2_raw = (
        db.session.query(
            func.count(Hashes.id).label("row_count"),
            Tasks.name,
            Users.email_address,
        )
        .join(Tasks, Hashes.task_id == Tasks.id)
        .join(Users, Tasks.owner_id == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.task_id.isnot(None))
        .filter(Hashes.hash_type.in_(ntlmv2_hash_types))
        .group_by(Hashes.task_id)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    most_effective_tasks_ntlmv2_table = []
    for entry in most_effective_tasks_ntlmv2_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_ntlmv2_table.append(dict_entry)

    kerberos_task_hash_types = kerberos_hash_types + (35300, 35400)
    most_effective_tasks_kerberos_raw = (
        db.session.query(
            func.count(Hashes.id).label("row_count"),
            Tasks.name,
            Users.email_address,
        )
        .join(Tasks, Hashes.task_id == Tasks.id)
        .join(Users, Tasks.owner_id == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.task_id.isnot(None))
        .filter(Hashes.hash_type.in_(kerberos_task_hash_types))
        .group_by(Hashes.task_id)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    most_effective_tasks_kerberos_table = []
    for entry in most_effective_tasks_kerberos_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_kerberos_table.append(dict_entry)

    most_effective_tasks_dcc2_raw = (
        db.session.query(
            func.count(Hashes.id).label("row_count"),
            Tasks.name,
            Users.email_address,
        )
        .join(Tasks, Hashes.task_id == Tasks.id)
        .join(Users, Tasks.owner_id == Users.id)
        .filter(Hashes.cracked == '1')
        .filter(Hashes.recovered_at > date_start)
        .filter(Hashes.recovered_at < date_end)
        .filter(Hashes.task_id.isnot(None))
        .filter(Hashes.hash_type == 2100)
        .group_by(Hashes.task_id)
        .order_by(func.count(Hashes.id).desc())
        .limit(10)
        .all()
    )

    most_effective_tasks_dcc2_table = []
    for entry in most_effective_tasks_dcc2_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_dcc2_table.append(dict_entry)

    # Render the wrapped statistics template with the collected data
    return render_template(
        'wrapped.html.j2',
        title='Hashview Wrapped',
        previous_year=year,
        longest_password_all_table=longest_password_all_table,
        longest_password_personal=longest_password_personal,
        longest_password_personal_rank=longest_password_personal_rank,
        longest_password_all_cnt=longest_password_all_cnt,
        most_passwords_recovered_all_table=most_passwords_recovered_all_table,
        total_passwords_recovered_personal_cnt=total_passwords_recovered_personal_cnt,
        total_passwords_recovered_personal_pct=total_passwords_recovered_personal_pct,
        total_ntlm_recovered_personal_cnt=total_ntlm_recovered_personal_cnt,
        total_ntlm_recovered_personal_pct=total_ntlm_recovered_personal_pct,
        total_ntlm_recovered_all_table=total_ntlm_recovered_all_table,
        total_ntlmv1_recovered_personal_cnt=total_ntlmv1_recovered_personal_cnt,
        total_ntlmv1_recovered_personal_pct=total_ntlmv1_recovered_personal_pct,
        total_ntlmv1_recovered_all_table=total_ntlmv1_recovered_all_table,
        total_ntlmv2_recovered_personal_cnt=total_ntlmv2_recovered_personal_cnt,
        total_ntlmv2_recovered_personal_pct=total_ntlmv2_recovered_personal_pct,
        total_ntlmv2_recovered_all_table=total_ntlmv2_recovered_all_table,
        total_kerberos_recovered_personal_cnt=total_kerberos_recovered_personal_cnt,
        total_kerberos_recovered_personal_pct=total_kerberos_recovered_personal_pct,
        total_kerberos_recovered_all_table=total_kerberos_recovered_all_table,
        total_dcc2_recovered_personal_cnt=total_kerberos_dcc2_personal_cnt,
        total_dcc2_recovered_personal_pct=total_dcc2_recovered_personal_pct,
        total_dcc2_recovered_all_table=total_dcc2_recovered_all_table,
        most_effective_tasks_table=most_effective_tasks_table,
        most_effective_tasks_ntlm_table=most_effective_tasks_ntlm_table,
        most_effective_tasks_ntlmv1_table=most_effective_tasks_ntlmv1_table,
        most_effective_tasks_ntlmv2_table=most_effective_tasks_ntlmv2_table,
        most_effective_tasks_kerberos_table=most_effective_tasks_kerberos_table,
        most_effective_tasks_dcc2_table=most_effective_tasks_dcc2_table,
    )
