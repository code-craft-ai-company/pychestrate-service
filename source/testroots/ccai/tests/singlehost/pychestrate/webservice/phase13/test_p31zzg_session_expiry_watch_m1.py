"""
.. module:: test_p31zzg_session_expiry_watch_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Any 401 from the site's API shows the "session expired" notice (XC-12).

.. moduleauthor:: Code Craft AI LLC

Only some bundle views turned a 401 into the shell's session-expired notice;
creating a secret after the session ended said "Failed to create the secret.
Try again." One wrapper on ``fetch``, installed by the shell, now announces
``pyc-session-401`` for any 401 from this site's own ``/api/``, whichever view
made the request, and returns the response unchanged. The requests are made
from a real page, with the API answering 401, 200 and 404.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict

from playwright.sync_api import Browser

from ccai import testbase

from ccai.testshared.factories.browsers.playwright_browser import (
    create_playwright_browser,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._shell_browser_harness import (
    open_shell_page,
)


testbase.originate.parameter(
    create_playwright_browser,
    identifier="browser",
)


DESKTOP: Dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}

TOAST = ".pyc-site-shell__session-toast"


def _answer(page: Any, path: str, status: int) -> None:
    page.context.route(
        "**" + path,
        lambda route: route.fulfill(status=status, headers={"Content-Type": "application/json"}, body='{"detail": "x"}'),
    )
    return


def test_a_401_from_any_api_call_shows_the_notice_and_the_caller_still_gets_the_response(browser: Browser):
    """
    **Feature: session expiry (XC-12)**
    **Property: a POST the page makes to /api/v1/secrets that is answered
    401 puts the "Sign in" toast on screen, the caller sees status 401 and can
    read the body, and the toast's link returns to this page after sign-in.**
    """
    page = open_shell_page(browser, path="/pods", **DESKTOP)
    try:
        _answer(page, "/api/v1/secrets", 401)
        before = page.locator(TOAST).count()
        result = page.evaluate(
            """async () => {
                const response = await fetch('/api/v1/secrets', {method: 'POST', body: '{}'});
                return {status: response.status, body: await response.text()};
            }"""
        )
        page.wait_for_selector(TOAST, timeout=5000)
        href = page.locator(TOAST + " a").first.get_attribute("href")
    finally:
        page.context.close()

    testbase.assert_equal(
        (before, result["status"], "detail" in result["body"], href),
        (0, 401, True, "/login?next=%2Fpods"),
    )
    return


def test_other_statuses_and_other_sites_do_not_show_it(browser: Browser):
    """
    **Feature: session expiry (XC-12)**
    **Property: a 200 and a 404 from the API, and a 401 from a path that is
    not under /api/, leave the page without the toast.**
    """
    page = open_shell_page(browser, path="/pods", **DESKTOP)
    try:
        _answer(page, "/api/v1/ok-thing", 200)
        _answer(page, "/api/v1/missing-thing", 404)
        _answer(page, "/other/denied", 401)
        page.evaluate(
            """async () => {
                await fetch('/api/v1/ok-thing');
                await fetch('/api/v1/missing-thing');
                await fetch('/other/denied');
            }"""
        )
        page.wait_for_timeout(500)
        count = page.locator(TOAST).count()
    finally:
        page.context.close()

    testbase.assert_equal(count, 0)
    return


def test_the_wrapper_is_installed_once_and_repeated_401s_share_one_toast(browser: Browser):
    """
    **Feature: session expiry (XC-12)**
    **Property: three 401s in a row leave exactly one toast, and the shell
    does not wrap fetch a second time.**
    """
    page = open_shell_page(browser, path="/pods", **DESKTOP)
    try:
        _answer(page, "/api/v1/things", 401)
        page.evaluate("async () => { for (let i = 0; i < 3; i++) { await fetch('/api/v1/things'); } }")
        page.wait_for_selector(TOAST, timeout=5000)
        page.wait_for_timeout(300)
        count = page.locator(TOAST).count()
        wrapped_once = page.evaluate("window.fetch.__pycSessionWatch === true && window.fetch.name === 'watched'")
    finally:
        page.context.close()

    testbase.assert_equal((count, wrapped_once), (1, True))
    return
