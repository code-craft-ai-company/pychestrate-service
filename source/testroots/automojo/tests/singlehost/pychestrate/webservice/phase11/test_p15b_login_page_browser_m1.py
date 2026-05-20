"""
.. module:: test_p15b_login_page_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Playwright browser-driven smoke for the consumer
               UI login page against a deployed pychestrate
               instance.

.. moduleauthor:: Automation Mojo LLC

Validates the end-to-end browser pipeline: real Chromium opens
the page, parses HTML, runs JS, exposes element queries. These
tests are slower than the ``test_p15a_*`` httpx checks (~1
second per test once the session-scoped browser is warm) but
catch regressions HTTP-level tests cannot -- e.g. a CSS asset
returning a 404, a JS error blocking page render, a missing
``<title>``.

The ``browser`` parameter is originated at SESSION scope by
:mod:`phase11.__init__`. Each test takes a fresh
``BrowserContext`` so cookies + storage are isolated per test.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from playwright.sync_api import Browser

from automojo import testbase

from automojo.testshared.test_config import BASE_URL


# Page-level navigation timeout. Higher than the httpx timeout
# because browser navigation includes JS / asset fetches and
# the consumer UI ships a few stylesheets.
NAVIGATION_TIMEOUT_MS: int = 15_000


def test_login_page_renders_with_login_in_title(browser: Browser):
    """
    **Feature: consumer-ui-login**
    **Property: GET /login rendered in a real browser
    produces a page whose ``<title>`` contains "Login" --
    validates the template inheritance chain end-to-end.**
    """
    context = browser.new_context()
    try:
        page = context.new_page()
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

        response = page.goto(BASE_URL + "/login")
        page_title = page.title()

        testbase.assert_true(response is not None)
        testbase.assert_equal(response.status, 200)
        testbase.assert_true("Login" in page_title)
    finally:
        context.close()
    return


def test_login_page_has_username_password_inputs(browser: Browser):
    """
    **Feature: consumer-ui-login**
    **Property: The login page renders ``input`` fields named
    ``username`` and ``password`` -- the actual form fields the
    POST handler reads.**
    """
    context = browser.new_context()
    try:
        page = context.new_page()
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

        page.goto(BASE_URL + "/login")
        username_count = page.locator("input[name='username']").count()
        password_count = page.locator("input[name='password']").count()

        testbase.assert_equal(username_count, 1)
        testbase.assert_equal(password_count, 1)
    finally:
        context.close()
    return


def test_root_url_does_not_redirect_to_setup_unlock(browser: Browser):
    """
    **Feature: initial-setup-wizard + 1-authentication Req 5**
    **Property: After wizard completion, navigating to / in a
    real browser as an anonymous user lands on the login page
    rather than the /setup/unlock wizard surface. The site-shell
    catch-all 303-redirects the unauthenticated request to
    /login?next=%2F per 1-authentication Requirement 5; the
    point of this test is that no setup-wizard surface
    resurfaces.**
    """
    context = browser.new_context()
    try:
        page = context.new_page()
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

        page.goto(BASE_URL + "/")
        landed_url = page.url

        testbase.assert_true("/login" in landed_url)
        testbase.assert_true("/setup/unlock" not in landed_url)
    finally:
        context.close()
    return
