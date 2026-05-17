"""
.. module:: test_p15d_login_flow_browser_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Playwright browser-driven login flow tests
               against the deployed pychestrate instance.

.. moduleauthor:: Automation Mojo LLC

Fills the login form in a real Chromium browser and asserts
that submission navigates to a post-login destination. The
counterpart to ``test_p15c_*`` httpx tests -- the browser
variant adds coverage of:

* Form submission via DOM events (click on the submit button),
  catching regressions where the form's ``method`` or
  ``action`` attributes are wrong.
* Cookie + redirect handling at the browser layer.
* The actual rendered post-login page (URL bar level), which
  the httpx variant cannot validate.

Credentials are read from the same env vars as p15c
(:data:`ENV_ADMIN_LOGIN` / :data:`ENV_ADMIN_PASSWORD`); tests
skip cleanly when either is unset.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Tuple

from playwright.sync_api import Browser

from automojo import testbase

from automojo.testshared.skip_helper import skip_test
from automojo.testshared.test_config import BASE_URL


# Navigation timeout. Higher than the httpx timeout because
# browser navigation includes JS + stylesheets + auto-waiting
# for actionable elements.
NAVIGATION_TIMEOUT_MS: int = 15_000


# Same env vars p15c uses -- they intentionally share a
# credential source so a single ``export`` covers both files.
ENV_ADMIN_LOGIN: str = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_ADMIN_PASSWORD: str = "PYCHESTRATE_TEST_ADMIN_PASSWORD"


def _resolve_admin_credentials() -> Tuple[str, str]:
    """
        Read admin credentials from the environment. Raise
        :class:`SkipError` when either var is unset/empty so
        the test is reported as SKIPPED on CI runners that
        haven't been wired with the secrets.

        :returns: ``(login_name, password)`` tuple.

        :raises: :class:`SkipError` when either env var is
                 unset.
    """
    login_name = os.environ.get(ENV_ADMIN_LOGIN, "")
    password = os.environ.get(ENV_ADMIN_PASSWORD, "")

    if len(login_name) == 0 or len(password) == 0:
        err_msg_lines = [
            "Browser login tests need admin credentials in env vars:",
            "  {}".format(ENV_ADMIN_LOGIN),
            "  {}".format(ENV_ADMIN_PASSWORD),
        ]
        skip_test(reason=os.linesep.join(err_msg_lines))

    rtnval = (login_name, password)
    return rtnval


def test_login_form_submission_lands_on_post_login_page(browser: Browser):
    """
    **Feature: consumer-ui-login**
    **Property: Filling the login form with valid admin
    credentials and clicking submit in a real browser navigates
    to a /config/* URL that is NOT /config/login -- proves the
    form action + DOM submit handler + redirect chain work
    end-to-end.**
    """
    login_name, password = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = context.new_page()
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

        page.goto(BASE_URL + "/config/login")
        page.fill("input[name='username']", login_name)
        page.fill("input[name='password']", password)
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        landed_url = page.url
        testbase.assert_true(landed_url.startswith(BASE_URL + "/config"))
        testbase.assert_true("/config/login" not in landed_url)
    finally:
        context.close()
    return


def test_login_form_with_wrong_password_stays_on_login_page(
        browser: Browser,
    ):
    """
    **Feature: consumer-ui-login**
    **Property: Submitting the login form with a wrong password
    leaves the browser ON /config/login (no navigation away)
    and the URL bar reflects the failure.**
    """
    login_name, _ = _resolve_admin_credentials()

    context = browser.new_context()
    try:
        page = context.new_page()
        page.set_default_navigation_timeout(NAVIGATION_TIMEOUT_MS)

        page.goto(BASE_URL + "/config/login")
        page.fill("input[name='username']", login_name)
        page.fill(
            "input[name='password']",
            "obviously-not-the-right-password",
        )
        page.click("button[type='submit']")
        page.wait_for_load_state("networkidle")

        landed_url = page.url
        testbase.assert_true("/config/login" in landed_url)
    finally:
        context.close()
    return
