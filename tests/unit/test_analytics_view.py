"""Unit tests for the redesigned /analytics page.

Exercises the three scopes the page supports via the customer_id / hashfile_id
query args (all data / per-customer / per-hashfile), the server-side aggregation
(top passwords, shared passwords, username==password, complexity histogram), and
that the template renders without error in each scope. Uses the in-memory SQLite
app from tests/unit/conftest.py.
"""

from datetime import datetime

from hashview.models import (
    Customers,
    Hashes,
    HashfileHashes,
    Hashfiles,
    Tasks,
    Users,
    db,
)


def _admin():
    user = Users(first_name="A", last_name="D", email_address="a@e.com",
                 password="x" * 60, admin=True, api_key="an-key")
    db.session.add(user)
    db.session.commit()
    return user


def _login(client, user):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def _hash(ciphertext, plaintext, cracked):
    h = Hashes(sub_ciphertext="0" * 8, ciphertext=ciphertext, hash_type=1000,
               cracked=cracked, plaintext=plaintext,
               recovered_at=datetime(2024, 1, 2) if cracked else None)
    db.session.add(h)
    db.session.commit()
    return h


def _seed():
    """One customer, one hashfile, 3 cracked + 1 uncracked accounts.

    'Password1' is shared by alice & bob; 'admin' uses its name as password.
    Returns (customer_id, hashfile_id).
    """
    cust = Customers(name="Acme Corp")
    db.session.add(cust)
    db.session.commit()
    hf = Hashfiles(name="corp_dump", customer_id=cust.id, owner_id=1, runtime=7200)
    db.session.add(hf)
    db.session.commit()
    rows = [
        ("aaa", "Password1", True, "alice"),
        ("bbb", "Password1", True, "bob"),
        ("ccc", "admin", True, "admin"),
        ("ddd", None, False, "carol"),
    ]
    for ct, pt, cracked, user in rows:
        h = _hash(ct, pt, cracked)
        db.session.add(HashfileHashes(hash_id=h.id, hashfile_id=hf.id, username=user))
    db.session.commit()
    return cust.id, hf.id


def test_analytics_all_scope(app, client):
    user = _admin(); _login(client, user)
    _seed()
    resp = client.get("/analytics")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Analytics" in html
    assert "Hashes Recovered" in html and "Accounts Recovered" in html
    assert "All Data" in html                       # summary title for the all scope
    assert "rollup" not in html                     # no customer rollup when unscoped
    assert "Password1" in html                       # top recovered password
    assert "Password Complexity Compliance" in html
    assert "admin" in html                           # username == password row


def test_analytics_customer_scope(app, client):
    user = _admin(); _login(client, user)
    customer_id, _hf = _seed()
    resp = client.get(f"/analytics?customer_id={customer_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Customer Summary" in html
    assert "rollup" in html                          # rollup shown when a customer is selected
    assert "Acme Corp" in html
    # hashfile select is enabled (has the per-file option) in customer scope
    assert f"hashfile_id" in html


def test_analytics_hashfile_scope(app, client):
    user = _admin(); _login(client, user)
    customer_id, hashfile_id = _seed()
    resp = client.get(f"/analytics?customer_id={customer_id}&hashfile_id={hashfile_id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Hashfile Summary" in html
    assert "Password1" in html


def test_analytics_empty_scope_renders(app, client):
    """A customer/hashfile with no cracked hashes must still render (placeholders)."""
    user = _admin(); _login(client, user)
    cust = Customers(name="Empty Co")
    db.session.add(cust); db.session.commit()
    hf = Hashfiles(name="nada", customer_id=cust.id, owner_id=1, runtime=0)
    db.session.add(hf); db.session.commit()
    h = _hash("eee", None, False)
    db.session.add(HashfileHashes(hash_id=h.id, hashfile_id=hf.id, username="nobody"))
    db.session.commit()
    resp = client.get(f"/analytics?customer_id={cust.id}&hashfile_id={hf.id}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "no recovered passwords" in html          # empty-state placeholder


def test_analytics_pattern_intelligence(app, client):
    """The Pattern Intelligence section: base words, themes, years, endings, and
    the 'how they fell' attack breakdown (incl. the task_id=None -> Unknown path)."""
    user = _admin(); _login(client, user)
    cust = Customers(name="Acme Corp")
    db.session.add(cust); db.session.commit()
    hf = Hashfiles(name="corp_dump", customer_id=cust.id, owner_id=1, runtime=3600)
    db.session.add(hf); db.session.commit()
    # a real wordlist task to attribute one crack to (the rest stay task_id=None)
    task = Tasks(name="RockYou", hc_attackmode=0, owner_id=1)
    db.session.add(task); db.session.commit()

    rows = [
        ("h1", "Summer2024!", "alice", task.id),   # base 'summer', season, year, ends '!', Wordlist
        ("h2", "Welcome1", "bob", None),            # base 'welcome', ends '1', Unknown
        ("h3", "Acme2023!", "carol", None),         # company token 'acme', year 2023
        ("h4", "qwerty123", "dave", None),          # keyboard walk, ends '123'
        ("h5", "admin", "admin", None),             # username == password
    ]
    for ct, pt, un, task_id in rows:
        h = _hash(ct, pt, True)
        h.task_id = task_id
        db.session.add(HashfileHashes(hash_id=h.id, hashfile_id=hf.id, username=un))
    db.session.commit()

    html = client.get(f"/analytics?customer_id={cust.id}").get_data(as_text=True)
    assert "pattern intelligence" in html
    assert "Top Base Words" in html and "summer" in html and "welcome" in html
    assert "Common Themes" in html and "Keyboard walk" in html
    assert "Year in Password" in html and "2024" in html and "2023" in html
    assert "Password Endings" in html
    # how they fell: one Wordlist (linked task) + the rest Unknown (task_id None)
    assert "How They Fell" in html and "Wordlist" in html and "Unknown" in html
    # structure / strength additions
    assert "brighter = more passwords" in html          # length x complexity heatmap
    assert "Password Strength" in html and "Very weak" in html
    assert "Password Rotation" in html                   # Summer2024!/Summer2023! share stem 'summer'
    # Export report prints the page to PDF in the browser (no server download)
    assert "window.print()" in html and "no-print" in html


def test_analytics_download_recovered_scoped(app, client):
    """The summary's download buttons hit the existing scoped download endpoint."""
    user = _admin(); _login(client, user)
    customer_id, hashfile_id = _seed()
    resp = client.get(f"/analytics/download?type=found&customer_id={customer_id}&hashfile_id={hashfile_id}")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Password1" in body                       # cracked export contains plaintext


def test_analytics_summary_above_donuts(app, client):
    """The scope summary card (with its download buttons) sits above the donuts."""
    user = _admin(); _login(client, user)
    customer_id, _hf = _seed()
    html = client.get(f"/analytics?customer_id={customer_id}").get_data(as_text=True)
    assert html.index("Customer Summary") < html.index("Hashes Recovered")
    assert "Download recovered" in html and "Download uncracked" in html
    # complexity compliance shows one decimal place (e.g. 99.9%)
    assert ".toFixed(1)" in html
    # whole-page print: the shell's 100vh/overflow is unpinned for print
    assert "height: auto !important" in html


def test_shared_password_row_download(app, client):
    """Clicking a shared-password row POSTs the plaintext and downloads its users."""
    user = _admin(); _login(client, user)
    customer_id, _hf = _seed()
    resp = client.post("/analytics/download/shared",
                       data={"plaintext": "Password1", "customer_id": str(customer_id), "hashfile_id": ""})
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert body.startswith("The following users were found to share the same password: Password1")
    assert "alice" in body and "bob" in body
    assert resp.headers["Content-Disposition"].startswith("attachment")


def test_shared_password_zip_download(app, client):
    """The card's download button zips one txt per shared-password group."""
    import io
    import zipfile
    user = _admin(); _login(client, user)
    customer_id, _hf = _seed()
    resp = client.get(f"/analytics/download/shared_zip?customer_id={customer_id}")
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(resp.data))
    names = archive.namelist()
    assert len(names) >= 1                            # at least the Password1 group
    content = "\n".join(archive.read(n).decode("utf-8") for n in names)
    assert "Password1" in content and "alice" in content and "bob" in content
