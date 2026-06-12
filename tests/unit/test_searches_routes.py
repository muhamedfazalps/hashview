"""Regression tests for searches routes + export helpers
(function-coverage batch: searches)."""

import io

from hashview.models import Customers, Hashes, HashfileHashes, Hashfiles, db
from hashview.searches.routes import export_results, get_rows
from tests.unit.helpers import login, make_admin


def _seed_cracked(username="bob", plaintext="Hunter2", ciphertext="deadbeef"):
    cust = Customers(name="SearchCo")
    db.session.add(cust)
    db.session.commit()
    hf = Hashfiles(name="hf", customer_id=cust.id, owner_id=1)
    db.session.add(hf)
    db.session.commit()
    h = Hashes(sub_ciphertext="0" * 8, ciphertext=ciphertext, hash_type=1000,
               cracked=True, plaintext=plaintext)
    db.session.add(h)
    db.session.commit()
    hfh = HashfileHashes(hash_id=h.id, hashfile_id=hf.id, username=username)
    db.session.add(hfh)
    db.session.commit()
    return cust, hf, h, hfh


def test_searches_list_get_renders(app, client):
    admin = make_admin()
    login(client, admin)
    resp = client.get("/search")
    assert resp.status_code == 200


def test_searches_list_password_search_finds_match(app, client):
    admin = make_admin()
    login(client, admin)
    _seed_cracked(plaintext="UniquePass1")
    resp = client.post("/search", data={
        "search_type": "password", "query": "UniquePass1",
        "export_type": "Comma", "submit": "Search",
    })
    assert resp.status_code == 200
    assert b"UniquePass1" in resp.data


def test_get_rows_writes_csv(app):
    cust, hf, h, hfh = _seed_cracked(username="carol", plaintext="pw1", ciphertext="abc123")
    str_io = io.StringIO()
    get_rows(str_io, [cust], [(h, hfh)], [hf], ",")
    out = str_io.getvalue()
    assert "SearchCo" in out
    assert "carol" in out
    assert "abc123" in out
    assert "pw1" in out


def test_export_results_returns_attachment(app):
    cust, hf, h, hfh = _seed_cracked(ciphertext="ffee00")
    # send_file needs a request context.
    with app.test_request_context("/search"):
        resp = export_results([cust], [(h, hfh)], [hf], "Colon")
    assert resp.status_code == 200
    assert resp.headers["Content-Disposition"].startswith("attachment")
