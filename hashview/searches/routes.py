import csv
import io
from flask import Blueprint, render_template, redirect, url_for, request, flash, send_file
from flask_login import login_required
from hashview.searches.forms import SearchForm
from hashview.models import Customers, Hashfiles, HashfileHashes, Hashes
from hashview.models import db
from hashview import jinja_hex_decode

searches = Blueprint('searches', __name__)

@searches.route("/search", methods=['GET', 'POST'])
@login_required
def searches_list():
    customers = Customers.query.all()
    hashfiles = Hashfiles.query.all()
    searchForm = SearchForm()
    redacted_data = False
    hash_results = None
    hashfile_results = None

    # TODO
    # We should be able to include Customers and Hashfiles in the following queries
    if searchForm.validate_on_submit():
        if searchForm.search_type.data == 'hash':
            print(f"[DEBUG] {searchForm.query.data}")
            # can be found in hashfiles, or not, or both?
            hash_results = db.session.query(Hashes).filter(Hashes.ciphertext==searchForm.query.data).all()
            hashfile_results = db.session.query(Hashes, HashfileHashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(Hashes.ciphertext==searchForm.query.data).all()
        elif searchForm.search_type.data == 'user':
            hashfile_results = db.session.query(Hashes, HashfileHashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(HashfileHashes.username.like('%' + searchForm.query.data.encode('latin-1').hex() + '%')).all()
        elif searchForm.search_type.data == 'password':
            hash_results = db.session.query(Hashes).filter(Hashes.plaintext == searchForm.query.data.encode('latin-1').hex()).all()
            hashfile_results = db.session.query(Hashes, HashfileHashes).join(HashfileHashes, Hashes.id==HashfileHashes.hash_id).filter(Hashes.plaintext == searchForm.query.data.encode('latin-1').hex()).all()
        else:
            flash('Invalid search option.', 'warning')
            return redirect(url_for('searches.searches_list'))
        
        if not hash_results and not hashfile_results:
            flash('No results found.', 'warning')

    elif request.args.get("hash_id"):
        hashfile_results = db.session.query(Hashes, HashfileHashes).join(HashfileHashes, Hashes.id == HashfileHashes.hash_id).filter(Hashes.id == request.args.get("hash_id"))
        if(hashfile_results.first()): #Without a value in the search input the export button will not pass the form validation
            searchForm.query.data = hashfile_results.first()[0].ciphertext #All hashs should be the same, so set the search input as the first rows hash value
            searchForm.search_type.data = 'hash' #Set the search type to hash
        else:
            hashfile_results = db.session.query(Hashes).filter(Hashes.id == request.args.get("hash_id")).all() #This is a hack to get the hash id to show up in the result
            redacted_data = True #This is a hack to get the hash id to show up in the result 
        if not hashfile_results:
            flash('No results found.', 'warning')
    else:
        customers = None
        results = None

    if hashfile_results and "export" in request.form: #Export Results
        return export_results(customers, results, hashfiles, searchForm.export_type.data)

    return render_template('search.html', title='Search', searchForm=searchForm, customers=customers, hash_results=hash_results, hashfile_results=hashfile_results, hashfiles=hashfiles, redacted_data=redacted_data)

#Creating this in memory instead of on disk to avoid any extra cleanup. This can be changed later if files get too large
def export_results(customers, results, hashfiles, separator):
    strIO = io.StringIO()
    separator = (',' if separator == "Comma" else ":")
    get_rows(strIO, customers, results, hashfiles, separator)
    byteIO = io.BytesIO()
    byteIO.write(strIO.getvalue().encode())
    byteIO.seek(0)
    strIO.close()
    return send_file(byteIO, download_name="search.txt", as_attachment=True)

#If this logic changes on in the html (search.html) it will need to change here as well
def get_rows(strIO, customers, results, hashfiles, separator):
    writer = csv.writer(strIO,delimiter=separator)
    for entry in results:
        col = ["None"] #set the first column to none incase the customer is not returned
        for hashfile in hashfiles:
            if hashfile.id == entry[1].hashfile_id:
                for customer in customers:
                    if customer.id == hashfile.customer_id:
                        col[0] = customer.name # Customer

        if entry[1].username: # Username
            col.append(jinja_hex_decode(entry[1].username))
        else:
            col.append("None")

        col.append(entry[0].ciphertext) # Hash

        if entry[0].cracked: #Plaintext
            col.append(jinja_hex_decode(entry[0].plaintext))
        else:
            col.append("unrecovered")

        writer.writerow([col[0],col[1],col[2],col[3]])
    return strIO
