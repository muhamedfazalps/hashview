"""Flask routes to handle Hashfiles"""
from flask import Blueprint, render_template, url_for, redirect, flash
from flask_login import login_required, current_user
from sqlalchemy.sql import exists
from hashview.models import Hashfiles, Customers, Jobs, HashfileHashes, HashNotifications, Hashes
from hashview.models import db
from hashview.jobs.forms import JobsNewHashFileForm
from sqlalchemy import func, case
from sqlalchemy.sql import exists

hashfiles = Blueprint('hashfiles', __name__)

@hashfiles.route("/hashfiles", methods=['GET', 'POST'])
@login_required

def hashfiles_list():
    """Function to return list of hashfiles"""
    hashfiles = Hashfiles.query.order_by(Hashfiles.uploaded_at.desc()).all()
    # customers = Customers.query.order_by(Customers.name).all()
    customers = Customers.query.filter(exists().where(Customers.id == Hashfiles.customer_id)).all()
    # Hashes.query.filter(~ exists().where(Hashes.id==HashfileHashes.hash_id)).filter_by(cracked = '0')
    # select * from customers where id in (select customer_id from hashfiles);
    jobs = Jobs.query.all()

    # Reverse-map hashcat modes -> friendly names from the new-hashfile form's own
    # select choices (same approach as jobs_assigned_hashfile). Falls back to the
    # numeric mode when a type isn't represented in the form.
    hash_type_names = {}
    try:
        _form = JobsNewHashFileForm()
        for _sel in (_form.hash_type, _form.pwdump_hash_type, _form.netntlm_hash_type,
                     _form.kerberos_hash_type, _form.shadow_hash_type):
            for _val, _label in _sel.choices:
                if _val is not None and str(_val) not in hash_type_names:
                    _name = _label.split(') ', 1)[1] if ') ' in _label else _label
                    hash_type_names[str(_val)] = _name.split(' / ')[0].split(',')[0].strip()
    except Exception:  # pragma: no cover - defensive: never break the list page
        hash_type_names = {}

    hash_type_dict = {}
    hashfile_stats = {}
    total_hashes = 0
    total_recovered = 0

    for hashfile in hashfiles:
        # one aggregated query per hashfile: total hashes, cracked count, representative mode
        agg = db.session.query(
            func.count(Hashes.id),
            func.coalesce(func.sum(case((Hashes.cracked == True, 1), else_=0)), 0),
            func.min(Hashes.hash_type)
        ).join(HashfileHashes, Hashes.id == HashfileHashes.hash_id) \
         .filter(HashfileHashes.hashfile_id == hashfile.id).first()
        hash_cnt = agg[0] or 0
        cracked_cnt = int(agg[1] or 0)
        hashfile_stats[hashfile.id] = {
            'cracked': cracked_cnt,
            'total': hash_cnt,
            'pct': round(cracked_cnt / hash_cnt * 100) if hash_cnt else 0,
        }
        total_hashes += hash_cnt
        total_recovered += cracked_cnt

        if hash_cnt and agg[2] is not None:
            _mode = str(agg[2])
            hash_type_dict[hashfile.id] = hash_type_names.get(_mode, _mode)
        else:
            hash_type_dict[hashfile.id] = 'UNKNOWN'

    overall_rate = round(total_recovered / total_hashes * 100) if total_hashes else 0

    return render_template('hashfiles.html.j2', title='Hashfiles', hashfiles=hashfiles,
                           customers=customers, jobs=jobs,
                           hash_type_dict=hash_type_dict, hashfile_stats=hashfile_stats,
                           total_hashes=total_hashes, total_recovered=total_recovered,
                           overall_rate=overall_rate)

@hashfiles.route("/hashfiles/delete/<int:hashfile_id>", methods=['GET', 'POST'])
@login_required
def hashfiles_delete(hashfile_id):
    """Function to delete hashfile by id"""
    hashfile = Hashfiles.query.get_or_404(hashfile_id)
    jobs = Jobs.query.filter_by(hashfile_id = hashfile_id).first()

    if hashfile:
        if current_user.admin or hashfile.owner_id == current_user.id:
            if jobs:
                flash('Error: Hashfile currently associated with a job.', 'danger')
                return redirect(url_for('hashfiles.hashfiles_list'))
            else:
                # Remove hashifle hash
                deleted_count = HashfileHashes.query.filter_by(hashfile_id = hashfile.id).delete(synchronize_session=False)
                print(f"[DEBUG] Deleted {deleted_count} Hashfile Hashes entries for hashfile ID {hashfile.id}")
                db.session.commit()

                # # remove hashfile 
                db.session.delete(hashfile)
                db.session.commit()

                # Remove all uncracked hashes not associated to a hashfile hash.
                deleted_count = Hashes.query.filter(
                    Hashes.cracked == 0
                ).filter(
                    ~exists().where(HashfileHashes.hash_id == Hashes.id)
                ).delete(synchronize_session=False)

                db.session.commit()
                print(f"[DEBUG] Deleted {deleted_count} orphaned uncracked hashes")

                # Remove notifications
                deleted_count = HashNotifications.query.filter(~exists().where(Hashes.id == HashNotifications.hash_id)).delete(synchronize_session=False)

                flash('Hashfile has been deleted!', 'success')
                return redirect(url_for('hashfiles.hashfiles_list'))
        else:
            flash('You do not have rights to delete this hashfile!', 'danger')
            return redirect(url_for('hashfiles.hashfiles_list'))
    else:
        flash('Error in deleting hashfile', 'danger')
        return redirect(url_for('hashfiles.hashfiles_list'))
