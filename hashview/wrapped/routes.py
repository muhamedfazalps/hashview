from flask import Blueprint, render_template
from flask_login import login_required, current_user
from hashview.models import Tasks, Users, Hashes
from hashview.models import db
from sqlalchemy import func, or_
import datetime

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

    # -------------------------------------------------------------------------
    # Query: Longest recovered passwords (global ranking)
    # Retrieves the top 10 longest passwords recovered by any user in the year.
    # -------------------------------------------------------------------------
    # Longest Password all
    #select h.id,h.recovered_at,CAST(unhex(h.plaintext) AS CHAR(100)),u.email_address from hashes as h join users as u on h.recovered_by = u.id where h.recovered_at > '2025-01-01' and h.recovered_at < '2026-01-01' ORDER BY LENGTH(h.plaintext) DESC limit 10;
    longest_password_all_table_raw = db.session.query(Hashes.plaintext, Hashes.recovered_at, Users.email_address).join(Users, Hashes.recovered_by==Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.hash_type != 7500) \
        .filter(Hashes.hash_type != 27000) \
        .filter(Hashes.hash_type != 27100) \
        .filter(Hashes.hash_type != 31500) \
        .filter(Hashes.hash_type != 31600) \
        .filter(Hashes.hash_type != 35300) \
        .filter(Hashes.hash_type != 35400) \
        .order_by(func.length(Hashes.plaintext).desc(), Hashes.recovered_at.asc()) \
        .limit(10) \
        .all()

    longest_password_all_table = []
    for entry in longest_password_all_table_raw:
        dict_entry = {}
        dict_entry['length'] = len(bytes.fromhex(entry.plaintext).decode('latin-1'))
        dict_entry['recovered_at'] = entry.recovered_at
        dict_entry['plaintext'] = bytes.fromhex(entry.plaintext).decode('latin-1')
        dict_entry['email_address'] = entry.email_address
        longest_password_all_table.append(dict_entry)

    # -------------------------------------------------------------------------
    # Query: Longest recovered password for the current (logged‑in) user
    # Retrieves the single longest password recovered by the current user.
    # -------------------------------------------------------------------------
    # Longest Password Personal
    longest_password_personal_raw = db.session.query(Hashes.plaintext) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .order_by(func.length(Hashes.plaintext).desc(), Hashes.recovered_at.asc()) \
        .filter(Hashes.recovered_by == current_user.id) \
        .first()

    longest_password_personal = bytes.fromhex(longest_password_personal_raw.plaintext).decode('latin-1')

    # -------------------------------------------------------------------------
    # Determine the personal ranking of the current user's longest password
    # among all users' longest passwords.
    # -------------------------------------------------------------------------
    # Find what position the person is for password length
    longest_password_all_raw = db.session.query(Hashes.plaintext, Hashes.recovered_by) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .order_by(func.length(Hashes.plaintext).desc()) \
        .all()   
    
    #longest_password_personal_rank = 0
    longest_password_all_cnt = len(longest_password_all_raw) -1
    longest_password_personal_rank = 1
    for entry in longest_password_all_raw:
        if entry.recovered_by == current_user.id:
            break
        elif entry.recovered_by != None:
            longest_password_personal_rank += 1

    # -------------------------------------------------------------------------
    # Query: Users with the most total passwords recovered
    # Retrieves the top 10 users ranked by count of passwords they recovered.
    # -------------------------------------------------------------------------
    # Most Passwords Recovered by user:
    # select count(h.id),u.email_address from hashes as h join users as u on h.recovered_by = u.id where h.recovered_by is not NULL and h.recovered_at > '2025-01-01' and h.cracked = '1' group by h.recovered_by ORDER BY COUNT(h.id) DESC LIMIT 10;
    most_passwords_recovered_all_raw = db.session.query(Hashes.recovered_by, Users.email_address, func.count(Hashes.id).label("row_count")).join(Users, Hashes.recovered_by == Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()

    most_passwords_recovered_all_table = []
    for entry in most_passwords_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        most_passwords_recovered_all_table.append(dict_entry)

    # -------------------------------------------------------------------------
    # Query: Total passwords recovered by each user (for ranking)
    # Used to compute the current user's percentile rank.
    # -------------------------------------------------------------------------
    # Total Passwords by you
    total_passwords_recovered = db.session.query(Hashes.recovered_by) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .all()

    total_passwords_recovered_personal_pct = 0
    personal_group_by_pos = len(total_passwords_recovered) -1
    for entry in total_passwords_recovered:
        if entry.recovered_by == current_user.id:
            total_passwords_recovered_personal_pct = round(personal_group_by_pos / (len(total_passwords_recovered)-1), 2) * 100
            break
        else:
            personal_group_by_pos -= 1

    # Total password personal cnt
    total_passwords_recovered_personal_cnt = db.session.query(Hashes.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.recovered_by == current_user.id) \
        .count() 

    #total_passwords_recovered_personal = total_passwords_recovered_personal_raw
    #total_passwords_recovered_personal_pct = total_passwords_recovered_personal / total_passwords_recovered_all_cnt

    # -------------------------------------------------------------------------
    # Query: NTLM (hash_type 1000) statistics – global totals
    # Retrieves top 10 users by NTLM hash count and builds ranking data.
    # -------------------------------------------------------------------------
    # Total NTLM recovered
    total_ntlm_recovered_all_raw = db.session.query(Hashes.recovered_by, Users.email_address, func.count(Hashes.id).label("row_count")).join(Users, Hashes.recovered_by == Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.hash_type == 1000) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()

    total_ntlm_recovered_all_table = []
    for entry in total_ntlm_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_ntlm_recovered_all_table.append(dict_entry)
    
    # Total NTLM recovered
    total_ntlm_recovered_all = db.session.query(Hashes.recovered_by) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.hash_type == 1000) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .all()

    total_ntlm_recovered_personal_pct = 0
    personal_group_by_pos = len(total_ntlm_recovered_all) -1
    for entry in total_ntlm_recovered_all:
        if entry.recovered_by == current_user.id:
            total_ntlm_recovered_personal_pct = round(personal_group_by_pos / (len(total_ntlm_recovered_all)-1), 2) * 100
            break
        else:
            personal_group_by_pos -= 1

    # Personal NTLM recovered
    total_ntlm_recovered_personal_cnt = db.session.query(Hashes.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.recovered_by == current_user.id) \
        .filter(Hashes.hash_type == 1000) \
        .count()

    # -------------------------------------------------------------------------
    # Query: NetNTLMv1 (hash_type 5500/27000) statistics – global totals
    # Retrieves top 10 users by NetNTLMv1 hash count and builds ranking data.
    # -------------------------------------------------------------------------
    # Total NetNTLMv1 recovered
    total_ntlmv1_recovered_all_raw = db.session.query(Hashes.recovered_by, Users.email_address, func.count(Hashes.id).label("row_count")).join(Users, Hashes.recovered_by == Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(or_(Hashes.hash_type == 5500, Hashes.hash_type == 27000)) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()

    total_ntlmv1_recovered_all_table = []
    for entry in total_ntlmv1_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_ntlmv1_recovered_all_table.append(dict_entry)
    
    # Total NTLMv2 recovered cnt
    total_ntlmv1_recovered_all = db.session.query(Hashes.recovered_by) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(or_(Hashes.hash_type == 5500, Hashes.hash_type == 27000)) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .all()
    
    total_ntlmv1_recovered_personal_pct = 0
    personal_group_by_pos = len(total_ntlmv1_recovered_all) -1
    for entry in total_ntlmv1_recovered_all:
        if entry.recovered_by == current_user.id:
            total_ntlmv1_recovered_personal_pct = round(personal_group_by_pos / (len(total_ntlmv1_recovered_all)-1), 2) * 100
        else:
            personal_group_by_pos -= 1


    # Personal NTLMv2 Recovered
    total_ntlmv1_recovered_personal_cnt = db.session.query(Hashes.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.recovered_by == current_user.id) \
        .filter(or_(Hashes.hash_type == 5500, Hashes.hash_type == 27000)) \
        .count()

    # -------------------------------------------------------------------------
    # Query: NetNTLMv2 (hash_type 5600/27100) statistics – global totals
    # Retrieves top 10 users by NetNTLMv2 hash count and builds ranking data.
    # -------------------------------------------------------------------------
    # Total NetNTLMv2 recovered
    total_ntlmv2_recovered_all_raw = db.session.query(Hashes.recovered_by, Users.email_address, func.count(Hashes.id).label("row_count")).join(Users, Hashes.recovered_by == Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(or_(Hashes.hash_type == 5600, Hashes.hash_type == 27100)) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()

    total_ntlmv2_recovered_all_table = []
    for entry in total_ntlmv2_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_ntlmv2_recovered_all_table.append(dict_entry)
    
    # Total NTLMv2 recovered cnt
    total_ntlmv2_recovered_all = db.session.query(Hashes.recovered_by) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(or_(Hashes.hash_type == 5600, Hashes.hash_type == 27100)) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .all()
    
    total_ntlmv2_recovered_personal_pct = 0
    personal_group_by_pos = len(total_ntlmv2_recovered_all) -1
    for entry in total_ntlmv2_recovered_all:
        if entry.recovered_by == current_user.id:
            total_ntlmv2_recovered_personal_pct = round(personal_group_by_pos / (len(total_ntlmv2_recovered_all)-1), 2) * 100
        else:
            personal_group_by_pos -= 1


    # Personal NTLMv2 Recovered
    total_ntlmv2_recovered_personal_cnt = db.session.query(Hashes.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.recovered_by == current_user.id) \
        .filter(or_(Hashes.hash_type == 5500, Hashes.hash_type == 5600, Hashes.hash_type == 27000, Hashes.hash_type == 27100)) \
        .count()

    # -------------------------------------------------------------------------
    # Query: Kerberos (multiple hash types) statistics – global totals
    # Retrieves top 10 users by Kerberos hash count and builds ranking data.
    # -------------------------------------------------------------------------
    # Total Kerberos Recovered
    total_kerberos_recovered_all_raw = db.session.query(Hashes.recovered_by, Users.email_address, func.count(Hashes.id).label("row_count")).join(Users, Hashes.recovered_by == Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(or_(Hashes.hash_type == 7500, Hashes.hash_type == 13100, Hashes.hash_type == 18200, Hashes.hash_type == 19600, Hashes.hash_type == 19700, Hashes.hash_type == 19800, Hashes.hash_type == 19900)) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()

    total_kerberos_recovered_all_table = []
    for entry in total_kerberos_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_kerberos_recovered_all_table.append(dict_entry)
    
    # Total kerberos recovered cnt
    total_kerberos_recovered_all = db.session.query(Hashes.recovered_by, func.count(Hashes.id).label("row_count")) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(or_(Hashes.hash_type == 7500, Hashes.hash_type == 13100, Hashes.hash_type == 18200, Hashes.hash_type == 19600, Hashes.hash_type == 19700, Hashes.hash_type == 19800, Hashes.hash_type == 19900)) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .all() 
    
    total_kerberos_recovered_personal_pct = 0
    for entry in total_kerberos_recovered_all:
        if entry.recovered_by == current_user.id:
            total_kerberos_recovered_personal_pct = round(entry.row_count / (len(total_kerberos_recovered_all)-1), 2) * 100

    # Personal Kerberos
    total_kerberos_recovered_personal_cnt = db.session.query(Hashes.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.recovered_by == current_user.id) \
        .filter(or_(Hashes.hash_type == 7500, Hashes.hash_type == 13100, Hashes.hash_type == 18200, Hashes.hash_type == 19600, Hashes.hash_type == 19700, Hashes.hash_type == 19800, Hashes.hash_type == 19900)) \
        .count()

    # -------------------------------------------------------------------------
    # Query: DCC2 statistics – global totals
    # Retrieves top 10 users by DCC2 hash count and builds ranking data.
    # -------------------------------------------------------------------------
    # Total Kerberos Recovered
    total_dcc2_recovered_all_raw = db.session.query(Hashes.recovered_by, Users.email_address, func.count(Hashes.id).label("row_count")).join(Users, Hashes.recovered_by == Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.hash_type == 2100) \
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()

    total_dcc2_recovered_all_table = []
    for entry in total_dcc2_recovered_all_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['email_address'] = entry.email_address
        total_dcc2_recovered_all_table.append(dict_entry)
    
    # Total dcc2 recovered cnt
    total_dcc2_recovered_all = db.session.query(Hashes.recovered_by, func.count(Hashes.id).label("row_count")) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.hash_type == 2100)\
        .group_by(Hashes.recovered_by) \
        .order_by(func.count(Hashes.id).desc()) \
        .all() 
    
    total_dcc2_recovered_personal_pct = 0
    for entry in total_dcc2_recovered_all:
        if entry.recovered_by == current_user.id:
            total_dcc2_recovered_personal_pct = round(entry.row_count / (len(total_dcc2_recovered_all)-1), 2) * 100

    # Personal Kerberos
    total_kerberos_dcc2_personal_cnt = db.session.query(Hashes.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.recovered_by == current_user.id) \
        .filter(Hashes.hash_type == 2100) \
        .count()

    # -------------------------------------------------------------------------
    # Query: Most effective tasks overall (by number of hashes recovered)
    # Retrieves top 10 tasks that contributed the most recovered hashes.
    # -------------------------------------------------------------------------
    # Most effective task
    #select count(h.id),t.name from hashes as h join tasks as t on t.id = h.task_id where h.task_id is not NULL and h.task_id != '0' and recovered_at > '2025-01-01' group by h.task_id order by count(h.id) DESC LIMIT 10;
    most_effective_tasks_raw = db.session.query(func.count(Hashes.id).label("row_count"), Tasks.name, Users.email_address).join(Tasks, Hashes.task_id == Tasks.id).join(Users, Tasks.owner_id==Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.task_id is not None) \
        .group_by(Hashes.task_id) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()
    
    most_effective_tasks_table = []
    for entry in most_effective_tasks_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_table.append(dict_entry)

    # -------------------------------------------------------------------------
    # Query: Most effective tasks for NTLM (hash_type 1000)
    # Retrieves top 10 tasks contributing to NTLM hash recovery.
    # -------------------------------------------------------------------------
    # Most effective tasks for hashtype 1000:
    #select count(h.id),t.name from hashes as h join tasks as t on t.id = h.task_id where h.task_id is not NULL and h.task_id != '0' and recovered_at > '2025-01-01' and h.hash_type='1000' group by h.task_id order by count(h.id) DESC LIMIT 10;
    most_effective_tasks_ntlm_raw = db.session.query(func.count(Hashes.id).label("row_count"), Tasks.name, Users.email_address).join(Tasks, Hashes.task_id == Tasks.id).join(Users, Tasks.owner_id==Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.task_id is not None) \
        .filter(Hashes.hash_type == 1000) \
        .group_by(Hashes.task_id) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()
    
    most_effective_tasks_ntlm_table = []
    for entry in most_effective_tasks_ntlm_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_ntlm_table.append(dict_entry)

    # -------------------------------------------------------------------------
    # Query: Most effective tasks for NetNTLMv1 (hash types 5500/27000)
    # Retrieves top 10 tasks contributing to NetNTLMv1 hash recovery.
    # -------------------------------------------------------------------------
    # Most effective tasks for hashtype 5500 and 27000
    #select count(h.id),t.name from hashes as h join tasks as t on t.id = h.task_id where h.task_id is not NULL and h.task_id != '0' and recovered_at > '2025-01-01' and h.hash_type='5600' group by h.task_id order by count(h.id) DESC LIMIT 10;
    most_effective_tasks_ntlmv1_raw = db.session.query(func.count(Hashes.id).label("row_count"), Tasks.name, Users.email_address).join(Tasks, Hashes.task_id == Tasks.id).join(Users, Tasks.owner_id==Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.task_id is not None) \
        .filter(or_(Hashes.hash_type == 5500, Hashes.hash_type == 27000)) \
        .group_by(Hashes.task_id) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()
    
    most_effective_tasks_ntlmv1_table = []
    for entry in most_effective_tasks_ntlmv1_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_ntlmv1_table.append(dict_entry)

    # -------------------------------------------------------------------------
    # Query: Most effective tasks for NetNTLMv2 (hash types 5600/27100)
    # Retrieves top 10 tasks contributing to NetNTLMv2 hash recovery.
    # -------------------------------------------------------------------------
    # Most effective tasks for hashtype 5600
    #select count(h.id),t.name from hashes as h join tasks as t on t.id = h.task_id where h.task_id is not NULL and h.task_id != '0' and recovered_at > '2025-01-01' and h.hash_type='5600' group by h.task_id order by count(h.id) DESC LIMIT 10;
    most_effective_tasks_ntlmv2_raw = db.session.query(func.count(Hashes.id).label("row_count"), Tasks.name, Users.email_address).join(Tasks, Hashes.task_id == Tasks.id).join(Users, Tasks.owner_id==Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.task_id is not None) \
        .filter(or_(Hashes.hash_type == 5600, Hashes.hash_type == 27100)) \
        .group_by(Hashes.task_id) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()
    
    most_effective_tasks_ntlmv2_table = []
    for entry in most_effective_tasks_ntlmv2_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_ntlmv2_table.append(dict_entry)

    # -------------------------------------------------------------------------
    # Query: Most effective tasks for Kerberos (hash_type 13100 and related)
    # Retrieves top 10 tasks contributing to Kerberos hash recovery.
    # -------------------------------------------------------------------------
    # Most effective tasks for hashtype 13100
    #select count(h.id),t.name from hashes as h join tasks as t on t.id = h.task_id where h.task_id is not NULL and h.task_id != '0' and recovered_at > '2025-01-01' and h.hash_type='13100' group by h.task_id order by count(h.id) DESC LIMIT 10;
    most_effective_tasks_kerberos_raw = db.session.query(func.count(Hashes.id).label("row_count"), Tasks.name, Users.email_address).join(Tasks, Hashes.task_id == Tasks.id).join(Users, Tasks.owner_id==Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.task_id is not None) \
        .filter(or_( 
            Hashes.hash_type == 7500, 
            Hashes.hash_type == 13100, 
            Hashes.hash_type == 18200, 
            Hashes.hash_type == 19600, 
            Hashes.hash_type == 19700, 
            Hashes.hash_type == 19800, 
            Hashes.hash_type == 19900,
            Hashes.hash_type == 35300,
            Hashes.hash_type == 35400,
            )) \
        .group_by(Hashes.task_id) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()
    
    most_effective_tasks_kerberos_table = []
    for entry in most_effective_tasks_kerberos_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_kerberos_table.append(dict_entry)


    # -------------------------------------------------------------------------
    # Query: Most effective tasks for dcc2
    # Retrieves top 10 tasks contributing to dcc2 hash recovery.
    # -------------------------------------------------------------------------
    # Most effective tasks for hashtype 2100
    #select count(h.id),t.name from hashes as h join tasks as t on t.id = h.task_id where h.task_id is not NULL and h.task_id != '0' and recovered_at > '2025-01-01' and h.hash_type='13100' group by h.task_id order by count(h.id) DESC LIMIT 10;
    most_effective_tasks_dcc2_raw = db.session.query(func.count(Hashes.id).label("row_count"), Tasks.name, Users.email_address).join(Tasks, Hashes.task_id == Tasks.id).join(Users, Tasks.owner_id==Users.id) \
        .filter(Hashes.cracked == '1') \
        .filter(Hashes.recovered_at > date_start) \
        .filter(Hashes.recovered_at < date_end) \
        .filter(Hashes.task_id is not None) \
        .filter(Hashes.hash_type == 2100) \
        .group_by(Hashes.task_id) \
        .order_by(func.count(Hashes.id).desc()) \
        .limit(10) \
        .all()
    
    most_effective_tasks_dcc2_table = []
    for entry in most_effective_tasks_dcc2_raw:
        dict_entry = {}
        dict_entry['count'] = entry.row_count
        dict_entry['task_name'] = entry.name
        dict_entry['task_author'] = entry.email_address
        most_effective_tasks_dcc2_table.append(dict_entry)

    # Render the wrapped statistics template with the collected data
    return render_template('wrapped.html.j2', title='Hashview Wrapped',
                           previous_year = year,
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
                           most_effective_tasks_dcc2_table=most_effective_tasks_dcc2_table
                           )
