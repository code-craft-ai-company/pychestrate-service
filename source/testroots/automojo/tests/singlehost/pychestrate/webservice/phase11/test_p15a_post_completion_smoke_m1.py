"""
.. module:: test_p15a_post_completion_smoke_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HTTP-level smoke tests against a deployed
               pychestrate instance whose initial-setup wizard
               has already completed.

.. moduleauthor:: Automation Mojo LLC

These run against the live alpha deploy at
``${PYCHESTRATE_TEST_BASE_URL}`` (default
``http://tc-app-server/``). No browser, no credentials -- pure
HTTP smoke verifying that:

* The setup wizard is permanently disabled after completion
  (one-way contract at the dispatcher layer).
* The consumer UI login page is reachable and renders.
* The gate middleware is a no-op after completion (root URL
  no longer redirects).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import httpx

from automojo import testbase

from automojo.testshared.test_config import BASE_URL


# Default per-request timeout for the smoke checks. Generous
# enough to cover a cold cache fetch through nginx, tight enough
# that a hung server fails fast.
REQUEST_TIMEOUT_SECONDS: float = 10.0


def _get(*, path: str, follow_redirects: bool = False) -> httpx.Response:
    """
        Issue a synchronous GET against ``BASE_URL + path`` with
        the test-wide timeout.

        :param path: Path component starting with ``/``.
        :param follow_redirects: Whether httpx should chase the
                                 ``Location`` header on 3xx.

        :returns: The :class:`httpx.Response` from the server.
    """
    url = BASE_URL + path
    response = httpx.get(
        url,
        follow_redirects=follow_redirects,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    rtnval = response
    return rtnval


def test_root_url_redirects_to_login_not_setup_after_completion():
    """
    **Feature: initial-setup-wizard + 1-authentication Req 5**
    **Property: After the wizard has been completed, an
    unauthenticated GET / 303-redirects to the login page --
    NOT to a setup-wizard surface. The setup-gate middleware is
    a no-op forever past completion; the site-shell catch-all
    then bounces the anonymous request to /login?next=%2F per
    1-authentication Requirement 5 instead of serving an empty
    shell.**
    """
    response = _get(path="/", follow_redirects=False)
    testbase.assert_equal(response.status_code, 303)
    location = response.headers.get("location", "")
    testbase.assert_true(location.endswith("/login?next=%2F"))
    testbase.assert_true("/setup" not in location)
    return


def test_unlock_page_returns_404_after_wizard_completion():
    """
    **Feature: initial-setup-wizard**
    **Property: GET /setup/unlock returns 404 once the wizard
    has completed. The wizard is one-way disabled at the
    dispatcher layer.**
    """
    response = _get(path="/setup/unlock", follow_redirects=False)
    testbase.assert_equal(response.status_code, 404)
    return


def test_admin_page_returns_404_after_wizard_completion():
    """
    **Feature: initial-setup-wizard**
    **Property: GET /setup/admin returns 404 after completion
    -- both wizard endpoints are disabled together so a
    bookmarked /setup/admin cannot resurface.**
    """
    response = _get(path="/setup/admin", follow_redirects=False)
    testbase.assert_equal(response.status_code, 404)
    return


def test_login_page_returns_200():
    """
    **Feature: consumer-ui-login**
    **Property: GET /login renders the login form HTML
    with a 200 status -- the consumer UI surface is reachable
    after the wizard completes.**
    """
    response = _get(path="/login", follow_redirects=False)
    testbase.assert_equal(response.status_code, 200)
    return


def test_login_page_html_mentions_login():
    """
    **Feature: consumer-ui-login**
    **Property: The /login response body is HTML that
    contains the word "login" (case-insensitive) -- guards
    against an empty 200 or a wrong-page response.**
    """
    response = _get(path="/login", follow_redirects=False)
    body_lower = response.text.lower()
    testbase.assert_true("login" in body_lower)
    return


def test_login_page_advertises_html_content_type():
    """
    **Feature: consumer-ui-login**
    **Property: /login returns ``text/html`` so browsers
    render the page rather than offering a download.**
    """
    response = _get(path="/login", follow_redirects=False)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true(content_type.startswith("text/html"))
    return
