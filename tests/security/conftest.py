"""Conftest for security PoC tests.

Overrides the parent (tests/) autouse fixtures `ensure_setup` and
`configure_page`, which require Playwright + a live HTTP server. The tests
in this directory are plain Flask tests that build their own in-memory SQLite
app via Flask's test_client; they do not need a browser. Without these
overrides the `page` fixture (Playwright) would be pulled in, causing
`BrowserType.launch: Executable doesn't exist` errors in CI environments
where Chromium is not installed.
"""

import pytest


@pytest.fixture(autouse=True)
def ensure_setup():
    """Override parent autouse so live_server isn't requested for security tests."""
    return


@pytest.fixture(autouse=True)
def configure_page():
    """Override parent autouse so the Playwright `page` fixture isn't pulled."""
    return
