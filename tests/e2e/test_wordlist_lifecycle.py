"""End-to-end coverage of the static wordlist lifecycle: upload then delete.

The flow exercised:
    GET  /wordlists/add  -> upload file with a unique name
    GET  /wordlists      -> verify the new wordlist row exists
    POST /wordlists/delete/<id>  (via the in-page delete modal)
    GET  /wordlists      -> verify the row is gone
"""

import re
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import expect


EXAMPLE_WORDLIST = Path(__file__).parent / "example_wordlist.txt"


def _open_wordlists_list(page, live_server):
    page.goto(f"{live_server}/wordlists", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name=re.compile(r"Wordlists"))).to_be_visible()


def _row_for_wordlist(page, name: str):
    """Locator for the table row containing the given wordlist name."""
    return page.locator("tr", has=page.locator("td", has_text=name)).first


def _add_static_wordlist(page, live_server, name: str) -> None:
    page.goto(f"{live_server}/wordlists/add", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name=re.compile(r"Add Wordlist"))).to_be_visible()
    page.locator("input[name='name']").fill(name)
    page.set_input_files("input[name='wordlist']", str(EXAMPLE_WORDLIST))
    page.get_by_role("button", name=re.compile(r"upload", re.I)).click()
    expect(page).to_have_url(re.compile(r".*/wordlists/?$"))
    expect(page.get_by_text("Wordlist created!", exact=False)).to_be_visible()


def _delete_wordlist_via_modal(page, name: str) -> None:
    row = _row_for_wordlist(page, name)
    expect(row).to_be_visible()
    # Each row's delete button targets #deleteModal<id>; click it to open the modal,
    # then submit the form inside the modal.
    row.locator("button[data-bs-target^='#deleteModal']").click()
    modal = page.locator(".modal.show")
    expect(modal).to_be_visible()
    modal.locator("form[action*='/wordlists/delete/'] input[type='submit'], "
                  "form[action*='/wordlists/delete/'] button[type='submit']").first.click()
    expect(page).to_have_url(re.compile(r".*/wordlists/?$"))
    expect(page.get_by_text("Wordlist has been deleted!", exact=False)).to_be_visible()


@pytest.mark.e2e
def test_static_wordlist_add_then_delete(page, live_server, login):
    """Upload a new static wordlist, then delete it and confirm it is gone."""
    login()
    name = f"e2e-wl-{uuid.uuid4().hex[:8]}"

    _add_static_wordlist(page, live_server, name)

    _open_wordlists_list(page, live_server)
    expect(_row_for_wordlist(page, name)).to_be_visible()

    _delete_wordlist_via_modal(page, name)

    _open_wordlists_list(page, live_server)
    assert _row_for_wordlist(page, name).count() == 0, (
        f"Wordlist '{name}' still present after delete"
    )
