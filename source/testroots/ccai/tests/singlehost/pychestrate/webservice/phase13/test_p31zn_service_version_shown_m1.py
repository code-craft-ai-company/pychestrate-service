"""
.. module:: test_p31zn_service_version_shown_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The running release is shown in the account menu (DOC-13).

.. moduleauthor:: Code Craft AI LLC

Nothing in the UI said which release was running, so a bug report could not
name one. The shell document carries the release the service reads from
``pyproject.toml`` (``service-version``), and the account menu shows it under
Sign out. The admin health document names it too.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from playwright.sync_api import Browser

from ccai import testbase

from ccai.pychestrate.webservice.public_endpoint import UNKNOWN_RELEASE, service_release
from ccai.pychestrate.webservice.webinterface.site_shell import shell_document
from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    SHELL_SERVICE_VERSION,
    open_shell_page,
    render_shell_html,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}


def test_the_shell_document_carries_the_release_the_service_reads_from_pyproject():
    """
    **Feature: release communication (DOC-13)**
    **Property: the value the server puts in the shell document is the
    service's release, and not the placeholder for an unreadable one.**
    """
    testbase.assert_equal(
        (shell_document._service_version_for_shell(), service_release() != UNKNOWN_RELEASE),
        (service_release(), True),
    )
    return


def test_an_unreadable_release_leaves_the_attribute_out_and_never_stops_the_page():
    """
    **Feature: release communication (DOC-13)**
    **Property: when the release cannot be read (unknown, or the lookup
    raises) the server passes an empty string, so the document has no
    ``service-version`` attribute and the page still renders.**
    """
    from ccai.pychestrate.webservice import public_endpoint

    original = public_endpoint.service_release
    try:
        public_endpoint.service_release = lambda: UNKNOWN_RELEASE
        unknown = shell_document._service_version_for_shell()

        def _fail() -> str:
            raise OSError("pyproject.toml unreadable")

        public_endpoint.service_release = _fail
        failed = shell_document._service_version_for_shell()
    finally:
        public_endpoint.service_release = original

    testbase.assert_equal((unknown, failed, 'service-version="{}"'.format(SHELL_SERVICE_VERSION) in render_shell_html(path="/", bundle_names=["pyc-site-shell"])), ("", "", True))
    return


def test_the_account_menu_shows_the_release_under_sign_out(browser: Browser):
    """
    **Feature: release communication (DOC-13)**
    **Property: opening the account menu shows "Pychestrate <release>" as
    its last item, after Sign out; before it is opened the line is not
    visible.**
    """
    page = open_shell_page(browser, path="/", **DESKTOP)
    try:
        label = page.locator(".pyc-site-shell__service-version")
        hidden_before = label.is_visible()
        page.click(".pyc-site-shell__account-button")
        page.wait_for_timeout(150)
        order = page.evaluate(
            "() => Array.from(document.querySelectorAll('.pyc-site-shell__account-panel > *')).map(e => e.className.split(' ')[0])"
        )
        testbase.assert_equal(
            (hidden_before, label.is_visible(), label.inner_text(), order[-2:]),
            (False, True, "Pychestrate " + SHELL_SERVICE_VERSION,
             ["pyc-site-shell__logout-button", "pyc-site-shell__service-version"]),
        )
    finally:
        page.context.close()
    return


def test_the_account_menu_links_to_the_pages_the_service_documents_itself_with(browser: Browser):
    """
    **Feature: documentation links (DOC-20)**
    **Property: the account menu has "API reference" (/api/docs) and "Error
    types" (/errors) links between API tokens and Sign out, so the product
    points to documentation that exists.**
    """
    page = open_shell_page(browser, path="/", **DESKTOP)
    try:
        page.click(".pyc-site-shell__account-button")
        page.wait_for_timeout(150)
        panel = page.locator(".pyc-site-shell__account-panel")
        order = page.evaluate(
            "() => Array.from(document.querySelectorAll('.pyc-site-shell__account-panel > *')).map(e => e.textContent.trim().split('\\n')[0].trim())"
        )
        testbase.assert_equal(
            (panel.get_by_role("link", name="API reference").get_attribute("href"),
             panel.get_by_role("link", name="Error types").get_attribute("href"),
             order.index("API tokens") < order.index("API reference") < order.index("Error types") < order.index("Sign out")),
            ("/api/docs", "/errors", True),
        )
    finally:
        page.context.close()
    return
