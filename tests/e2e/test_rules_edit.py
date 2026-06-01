"""End-to-end coverage of the rules edit page.

Exercises:
    GET  /rules/edit/<id>          -> page renders, textarea has file contents
    POST /rules/edit/<id>          -> saving new content persists
    GET  /rules                    -> the row's edit anchor is visible
"""

import re
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import expect


EXAMPLE_RULE = Path(__file__).parent / "example_rule.rule"


def _open_rules_list(page, live_server):
    page.goto(f"{live_server}/rules", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name=re.compile(r"Rules"))).to_be_visible()


def _row_for_rule(page, name: str):
    return page.locator("tr", has=page.locator("td", has_text=name)).first


def _add_rule(page, live_server, name: str) -> None:
    page.goto(f"{live_server}/rules/add", wait_until="domcontentloaded")
    expect(page.get_by_role("heading", name=re.compile(r"Add Rules"))).to_be_visible()
    page.locator("input[name='name']").fill(name)
    page.set_input_files("input[name='rules']", str(EXAMPLE_RULE))
    page.get_by_role("button", name=re.compile(r"upload", re.I)).click()
    expect(page).to_have_url(re.compile(r".*/rules/?$"))
    expect(page.get_by_text("Rules File created!", exact=False)).to_be_visible()


def _delete_rule_via_modal(page, name: str) -> None:
    row = _row_for_rule(page, name)
    expect(row).to_be_visible()
    row.locator("button[data-bs-target^='#deleteModal']").click()
    modal = page.locator(".modal.show")
    expect(modal).to_be_visible()
    modal.locator("form[action*='/rules/delete/'] input[type='submit'], "
                  "form[action*='/rules/delete/'] button[type='submit']").first.click()
    expect(page).to_have_url(re.compile(r".*/rules/?$"))
    expect(page.get_by_text("Rule file has been deleted!", exact=False)).to_be_visible()


@pytest.mark.e2e
def test_rules_edit_page_renders_with_file_contents(page, live_server, login):
    """The edit page should load and display the file's existing contents."""
    login()
    name = f"e2e-rule-{uuid.uuid4().hex[:6]}"
    _add_rule(page, live_server, name)
    try:
        _open_rules_list(page, live_server)
        row = _row_for_rule(page, name)
        expect(row).to_be_visible()
        row.locator("a.btn-warning[href*='/rules/edit/']").first.click()
        expect(page).to_have_url(re.compile(r".*/rules/edit/\d+"))

        textarea = page.locator("textarea[name='content']")
        expect(textarea).to_be_visible()
        assert textarea.input_value() == EXAMPLE_RULE.read_text()

        body = page.content()
        for marker in ("UndefinedError", "Traceback", "Internal Server Error"):
            assert marker not in body, f"Unexpected error marker on page: {marker}"
    finally:
        _open_rules_list(page, live_server)
        _delete_rule_via_modal(page, name)


@pytest.mark.e2e
def test_rules_edit_can_save_changes(page, live_server, login):
    """Posting an edit should persist the new content on reload."""
    login()
    name = f"e2e-rule-{uuid.uuid4().hex[:6]}"
    _add_rule(page, live_server, name)
    try:
        _open_rules_list(page, live_server)
        row = _row_for_rule(page, name)
        expect(row).to_be_visible()
        row.locator("a.btn-warning[href*='/rules/edit/']").first.click()
        expect(page).to_have_url(re.compile(r".*/rules/edit/\d+"))
        edit_url = page.url

        textarea = page.locator("textarea[name='content']")
        expect(textarea).to_be_visible()
        textarea.fill("T0\nT1\n")

        page.get_by_role("button", name=re.compile(r"^update$", re.I)).click()

        page.goto(edit_url, wait_until="domcontentloaded")
        textarea = page.locator("textarea[name='content']")
        expect(textarea).to_be_visible()
        assert textarea.input_value() == "T0\nT1\n"
    finally:
        _open_rules_list(page, live_server)
        _delete_rule_via_modal(page, name)


@pytest.mark.e2e
def test_rules_edit_button_visible_on_list(page, live_server, login):
    """The edit anchor on the rules list must render visible with a real box.

    Guards against the historical 'btn-warn' class typo regression that would
    leave the anchor without bootstrap padding and effectively invisible.
    """
    login()
    name = f"e2e-rule-{uuid.uuid4().hex[:6]}"
    _add_rule(page, live_server, name)
    try:
        _open_rules_list(page, live_server)
        row = _row_for_rule(page, name)
        expect(row).to_be_visible()
        edit_anchor = row.locator("a.btn-warning[href*='/rules/edit/']")
        assert edit_anchor.count() == 1
        assert edit_anchor.is_visible()
        box = edit_anchor.bounding_box()
        assert isinstance(box, dict)
        assert box.get("width", 0) > 0
        assert box.get("height", 0) > 0
    finally:
        _open_rules_list(page, live_server)
        _delete_rule_via_modal(page, name)
