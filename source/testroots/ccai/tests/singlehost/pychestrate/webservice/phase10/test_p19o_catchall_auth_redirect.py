"""
.. module:: test_p19o_catchall_auth_redirect
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Unit tests for the site-shell catch-all auth
               redirect (p19o / 1-authentication Requirement 5).

.. moduleauthor:: Code Craft AI LLC

The catch-all handler that serves the site-shell document for
non-chromeless GETs must server-side redirect an unauthenticated
browser to ``/login?next=<original-path>`` rather than serving an
empty shell. These tests drive
:func:`catchall_route._serve_shell_or_pass` against a fake
request:

* An unauthenticated GET to ``/runs`` 303-redirects to
  ``/login?next=%2Fruns``.
* An unauthenticated GET to ``/runs?status=active`` carries the
  encoded query string in the ``next`` parameter.
* An authenticated GET to ``/runs`` (valid signed session cookie)
  serves the shell document with status 200.
* A non-shell path (``/api/v1/...``) still 404s without touching
  the auth check.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, List, Optional

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
    templating,
)
from ccai.pychestrate.webservice.webinterface.site_shell import (
    catchall_route,
)


_TEST_COOKIE_SECRET: bytes = b"p19o-catchall-test-cookie-secret-32b"


class _FakeCookies:
    def __init__(self, *, values: Optional[Dict[str, str]] = None) -> None:
        self._values: Dict[str, str] = values if values is not None else {}
        return

    def get(
            self, key: str, default: Optional[str] = None
        ) -> Optional[str]:
        rtnval = self._values.get(key, default)
        return rtnval


class _FakeRequest:
    def __init__(
            self,
            *,
            path: str,
            query_string: str = "",
            cookies: Optional[Dict[str, str]] = None
        ) -> None:
        self.path: str = path
        self.query_string: str = query_string
        self.cookies: _FakeCookies = _FakeCookies(values=cookies)
        return


class _StubTemplate:
    def __init__(self, *, name: str) -> None:
        self.name: str = name
        return

    def render(self, ctx: Dict[str, Any]) -> str:
        return "RENDERED:{}".format(self.name)


class _StubJinjaEnvironment:
    def __init__(self) -> None:
        self.template_lookups: List[str] = []
        self.globals: Dict[str, Any] = {}
        return

    def get_template(self, name: str) -> _StubTemplate:
        self.template_lookups.append(name)
        return _StubTemplate(name=name)


def _build_authenticated_cookie() -> Dict[str, str]:
    """
        Build a cookie jar carrying a valid signed UI session that
        names an authenticated user.

        :returns: Dict suitable for :class:`_FakeRequest` cookies.
    """
    payload: Dict[str, Any] = {
        "user_id": "user-p19o",
        "username": "p19o-admin",
        "session_token": "session-token-p19o",
    }
    signed = cookie_session.sign_session_payload(
        payload=payload, secret=_TEST_COOKIE_SECRET
    )
    rtnval = {cookie_session.COOKIE_NAME: signed}
    return rtnval


def test_unauthenticated_shell_path_redirects_to_login():
    """
    **Feature: site-shell + authentication**
    **Property: An unauthenticated GET to a protected shell route
    (``/runs``) 303-redirects to ``/login?next=%2Fruns`` instead
    of serving the shell document.**
    """
    previous_secret = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = _TEST_COOKIE_SECRET
    try:
        request = _FakeRequest(path="/runs")
        response = catchall_route._serve_shell_or_pass(request=request)
    finally:
        SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = previous_secret

    testbase.assert_equal(response.status_code, 303)
    location = response.headers.get("Location", "")
    testbase.assert_equal(location, "/login?next=%2Fruns")
    return


def test_unauthenticated_redirect_preserves_query_string():
    """
    **Feature: site-shell + authentication**
    **Property: The ``next`` parameter carries the original path
    AND query string, percent-encoded, so the post-login redirect
    lands the browser back on the exact requested target.**
    """
    previous_secret = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = _TEST_COOKIE_SECRET
    try:
        request = _FakeRequest(
            path="/runs", query_string="status=active"
        )
        response = catchall_route._serve_shell_or_pass(request=request)
    finally:
        SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = previous_secret

    testbase.assert_equal(response.status_code, 303)
    location = response.headers.get("Location", "")
    testbase.assert_equal(
        location, "/login?next=%2Fruns%3Fstatus%3Dactive"
    )
    return


def test_authenticated_shell_path_serves_shell_document():
    """
    **Feature: site-shell + authentication**
    **Property: An authenticated GET (valid signed session cookie)
    to a protected shell route serves the shell document with
    status 200 -- no redirect.**
    """
    previous_secret = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = _TEST_COOKIE_SECRET
    templating.set_default_environment(environment=_StubJinjaEnvironment())
    try:
        request = _FakeRequest(
            path="/runs", cookies=_build_authenticated_cookie()
        )
        response = catchall_route._serve_shell_or_pass(request=request)
    finally:
        SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = previous_secret
        templating.reset_default_environment_for_testing()

    testbase.assert_equal(response.status_code, 200)
    return


def test_non_shell_path_returns_404_without_redirect():
    """
    **Feature: site-shell**
    **Property: A non-shell path (``/api/v1/...``) is not a shell
    candidate and 404s -- the auth-redirect logic only applies to
    shell-candidate paths.**
    """
    request = _FakeRequest(path="/api/v1/runs")
    response = catchall_route._serve_shell_or_pass(request=request)

    testbase.assert_equal(response.status_code, 404)
    return


def test_is_request_authenticated_false_when_secret_unconfigured():
    """
    **Feature: site-shell + authentication**
    **Property: When the UI cookie secret is not configured the
    catch-all fails closed -- the request is treated as
    unauthenticated so a misconfigured deploy bounces to login
    rather than leaking the shell.**
    """
    previous_secret = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
    SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = None
    try:
        request = _FakeRequest(
            path="/runs", cookies=_build_authenticated_cookie()
        )
        is_authed = catchall_route._is_request_authenticated(
            request=request
        )
    finally:
        SITE_SHARED_GLOBALS.UI_COOKIE_SECRET = previous_secret

    testbase.assert_equal(is_authed, False)
    return
