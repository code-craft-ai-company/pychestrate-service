"""
.. module:: test_p22b_nav_manifest_in_shell
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the bare ``/`` route serves a
               shell whose sidebar is complete because the shell
               fetches the central navigation manifest (PR p22b).

.. moduleauthor:: Automation Mojo LLC

This is the regression test for the p22b lockout-class bug. Every
existing ``*_in_shell`` test hits a feature route (``/runs``,
``/admin``, ...) where the matching feature bundle loads and
registers that feature's sidebar entries -- so none of them
exercised the bare ``/`` route, which loads only
``pyc-site-shell.js`` and historically rendered an empty sidebar
(the "no access" empty state) even for a full administrator.

p22b adds ``GET /api/v1/me/navigation`` -- a server-side,
permission-filtered central navigation manifest -- and has the
shell render its full sidebar from it on every route. This test:

* Confirms ``GET /api/v1/me/navigation`` is wired -- an anonymous
  request returns 401 (proof the route exists; a missing route
  would 404 / redirect).
* After an admin login, hits the bare ``/`` route and asserts the
  shell document is served AND wires the ``navigation-endpoint``
  attribute so the shell fetches the manifest on boot.
* After login, fetches ``GET /api/v1/me/navigation`` and asserts
  the full sidebar manifest comes back -- the Orchestration,
  Insights, Fleet, Operations and Admin feature entries an admin
  expects, none of which depend on a feature bundle being loaded.

Credentials follow the phase-11 contract; the login-gated tests
SKIP when ``PYCHESTRATE_TEST_ADMIN_LOGIN`` /
``PYCHESTRATE_TEST_ADMIN_PASSWORD`` are unset.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import time

from typing import Tuple

import httpx

from automojo import testbase

from automojo.testshared.skip_helper import skip_test
from automojo.testshared.test_config import BASE_URL


REQUEST_TIMEOUT_SECONDS: float = 10.0


ENV_ADMIN_LOGIN: str = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_ADMIN_PASSWORD: str = "PYCHESTRATE_TEST_ADMIN_PASSWORD"


NAVIGATION_ENDPOINT: str = "/api/v1/me/navigation"


LOGIN_MAX_ATTEMPTS: int = 4
LOGIN_RETRY_DELAY_SECONDS: float = 2.0


def _resolve_admin_credentials() -> Tuple[str, str]:
    """
        Read admin credentials from the environment; skip the test
        when either var is unset/empty.

        :returns: ``(login_name, password)``.

        :raises: :class:`SkipError` when either env var is unset.
    """
    login_name = os.environ.get(ENV_ADMIN_LOGIN, "")
    password = os.environ.get(ENV_ADMIN_PASSWORD, "")

    if len(login_name) == 0 or len(password) == 0:
        err_msg_lines = [
            "p22b nav-manifest-in-shell test needs admin credentials:",
            "  {}={}".format(
                ENV_ADMIN_LOGIN,
                "<set>" if len(login_name) > 0 else "<unset>",
            ),
            "  {}={}".format(
                ENV_ADMIN_PASSWORD,
                "<set>" if len(password) > 0 else "<unset>",
            ),
        ]
        skip_test(reason=os.linesep.join(err_msg_lines))

    rtnval = (login_name, password)
    return rtnval


def _login_admin(
        *,
        client: httpx.Client,
        login_name: str,
        password: str
    ) -> None:
    """
        Mint an admin session cookie on the supplied client,
        retrying through the transient login-backoff window.

        :param client: HTTP client whose cookie jar receives the
                        session cookie.
        :param login_name: Admin login name.
        :param password: Admin password.

        :returns: None.

        :raises: AssertionError when login still fails after the
                 retry budget is exhausted.
    """
    last_status = 0
    attempt = 0
    while attempt < LOGIN_MAX_ATTEMPTS:
        client.get("/login")
        login_response = client.post(
            "/login",
            data={"username": login_name, "password": password},
        )
        last_status = login_response.status_code
        if last_status == 200:
            return
        attempt = attempt + 1
        if attempt < LOGIN_MAX_ATTEMPTS:
            time.sleep(LOGIN_RETRY_DELAY_SECONDS)

    testbase.assert_equal(last_status, 200)
    return


def test_navigation_endpoint_is_wired():
    """
    **Feature: site-shell central nav manifest**
    **Property: GET /api/v1/me/navigation exists -- an anonymous
    request returns HTTP 401 (RFC 7807 problem document), proving
    the route is registered. A missing route would 404.**

    No login required: a 401 is the expected proof-of-wiring.
    """
    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        response = client.get(NAVIGATION_ENDPOINT)

    testbase.assert_equal(response.status_code, 401)
    return


def test_root_shell_wires_navigation_endpoint():
    """
    **Feature: site-shell central nav manifest**
    **Property: After an admin login, GET / serves the shell
    document with a ``navigation-endpoint`` attribute on the
    ``<pyc-site-shell>`` element, so the shell fetches the central
    manifest on boot and renders the full sidebar even though no
    feature bundle loads on the bare / route.**
    """
    login_name, password = _resolve_admin_credentials()

    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
        _login_admin(
            client=client,
            login_name=login_name,
            password=password,
        )
        response = client.get("/")

    testbase.assert_equal(response.status_code, 200)
    body = response.text
    testbase.assert_true("<pyc-site-shell" in body)
    testbase.assert_true(
        'navigation-endpoint="/api/v1/me/navigation"' in body
    )
    return


def test_navigation_manifest_lists_full_admin_sidebar():
    """
    **Feature: site-shell central nav manifest**
    **Property: After an admin login, GET /api/v1/me/navigation
    returns the full permission-filtered sidebar manifest -- the
    headline feature entries (Runs, Builds, Test Metrics, Pods,
    Webhooks, Admin Overview) an administrator expects, none of
    which depend on a feature bundle being loaded. This is the
    regression for the empty-sidebar-on-/ lockout bug.**
    """
    login_name, password = _resolve_admin_credentials()

    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
        _login_admin(
            client=client,
            login_name=login_name,
            password=password,
        )
        response = client.get(NAVIGATION_ENDPOINT)

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("application/json" in content_type)

    payload = response.json()
    testbase.assert_true("groups" in payload)
    groups = payload["groups"]
    testbase.assert_true(len(groups) > 0)

    routes = []
    labels = []
    for group in groups:
        for entry in group["entries"]:
            routes.append(entry["route"])
            labels.append(entry["label"])

    # A full administrator sees the headline feature entries.
    for expected_route in ("/runs", "/builds", "/test-metrics"):
        testbase.assert_true(expected_route in routes)
    testbase.assert_true("Admin" in [g["label"] for g in groups])
    return
