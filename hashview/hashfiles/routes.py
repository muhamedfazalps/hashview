"""Flask routes to handle Hashfiles"""
from flask import Blueprint, render_template, url_for, redirect, flash
from flask_login import login_required, current_user
from sqlalchemy.sql import exists
from hashview.models import Hashfiles, Customers, Jobs, HashfileHashes, HashNotifications, Hashes
from hashview.models import db
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

    cracked_rate = {}
    hash_type_dict = {}

    for hashfile in hashfiles:
        cracked_cnt = db.session.query(Hashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(Hashes.cracked == '1').filter(HashfileHashes.hashfile_id==hashfile.id).count()
        hash_cnt = db.session.query(Hashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(HashfileHashes.hashfile_id==hashfile.id).count()
        cracked_rate[hashfile.id] = "(" + str(cracked_cnt) + "/" + str(hash_cnt) + ")"
        if db.session.query(Hashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(HashfileHashes.hashfile_id==hashfile.id).first():
            hash_type_dict[hashfile.id] = db.session.query(Hashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(HashfileHashes.hashfile_id==hashfile.id).first().hash_type
        else:
            hash_type_dict[hashfile.id] = 'UNKNOWN'

    return render_template('hashfiles.html.j2', title='Hashfiles', hashfiles=hashfiles, customers=customers, cracked_rate=cracked_rate, jobs=jobs, hash_type_dict=hash_type_dict)

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
