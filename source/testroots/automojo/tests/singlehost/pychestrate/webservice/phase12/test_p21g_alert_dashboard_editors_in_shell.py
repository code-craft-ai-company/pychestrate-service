"""
.. module:: test_p21g_alert_dashboard_editors_in_shell
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the metric-alert-rule editor and
               dashboard-layout editor surfaces render inside the
               unified site shell and import the pyc-metrics-bundle
               feature bundle (PR p21g -- alert + dashboard
               editors).

.. moduleauthor:: Automation Mojo LLC

Drives the new shell-served routes over real HTTP against the
deploy after a successful admin login. Asserts for each route:

* The response is HTML and status 200.
* The body contains the ``<pyc-site-shell>`` Custom Element open
  tag -- i.e. the page renders inside the shell.
* The body imports ``pyc-metrics-bundle.js`` -- the bundle that
  owns the alert-rules editor (``<pyc-alert-rules>``) and the
  dashboard-layout editor (``<pyc-dashboard-editor>``).

The two new routes are:

* ``/metric-alerts`` -- the alert-rule editor view.
* ``/dashboards/{dashboard_id}/edit`` -- the dashboard-layout
  editor view (a sub-path of the already-registered
  ``/dashboards`` bundle prefix).

Credentials follow the phase-11 contract --
``PYCHESTRATE_TEST_ADMIN_LOGIN`` + ``PYCHESTRATE_TEST_ADMIN_PASSWORD``
-- and the tests skip when either env var is unset.
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


def _resolve_admin_credentials() -> Tuple[str, str]:
    """
        Read admin credentials from the environment; skip the test
        when either var is unset/empty so CI runners that have not
        been wired with the deploy admin password report a clean
        SKIP rather than a failure.

        :returns: ``(login_name, password)``.

        :raises: :class:`SkipError` when either env var is unset.
    """
    login_name = os.environ.get(ENV_ADMIN_LOGIN, "")
    password = os.environ.get(ENV_ADMIN_PASSWORD, "")

    if len(login_name) == 0 or len(password) == 0:
        err_msg_lines = [
            "p21g editor-in-shell test needs admin credentials in env vars:",
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


# Number of login attempts before giving up. The deployed auth
# stack backs off per ``(login_name, source_ip)`` after recent
# failures; a short retry rides through the window without masking
# a real authentication failure.
LOGIN_MAX_ATTEMPTS: int = 4
LOGIN_RETRY_DELAY_SECONDS: float = 2.0


def _login_admin(*, client: httpx.Client, login_name: str, password: str) -> None:
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


def _assert_shell_route(*, route_path: str, bundle_name: str) -> None:
    """
        Log in as admin, fetch a shell-served route, and assert it
        renders inside ``<pyc-site-shell>`` and imports the
        supplied feature bundle.

        :param route_path: Shell route to fetch.
        :param bundle_name: Feature bundle base name expected in a
                            ``<script>`` tag.

        :returns: None.
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
        response = client.get(route_path)

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("text/html" in content_type)

    body = response.text
    testbase.assert_true("<pyc-site-shell" in body)
    bundle_src = "/static/javascript/dist/{}.js".format(bundle_name)
    testbase.assert_true(bundle_src in body)
    return


def test_metric_alerts_page_renders_inside_site_shell():
    """
    **Feature: site-shell + alert-dashboard-editors**
    **Property: After a successful admin login, GET /metric-alerts
    returns an HTML page that mounts the ``<pyc-site-shell>``
    Custom Element AND imports the ``pyc-metrics-bundle.js`` script
    so the ``<pyc-alert-rules>`` editor view mounts in the
    browser.**
    """
    _assert_shell_route(
        route_path="/metric-alerts",
        bundle_name="pyc-metrics-bundle",
    )
    return


def test_dashboard_editor_page_renders_inside_site_shell():
    """
    **Feature: site-shell + alert-dashboard-editors**
    **Property: After a successful admin login, GET
    /dashboards/{dashboard_id}/edit returns an HTML page that
    mounts the ``<pyc-site-shell>`` Custom Element AND imports the
    ``pyc-metrics-bundle.js`` script so the
    ``<pyc-dashboard-editor>`` layout-editor view mounts in the
    browser. The dashboard id is a placeholder -- the shell
    document is route-shape driven and serves the bundle for any
    ``/dashboards`` sub-path.**
    """
    _assert_shell_route(
        route_path="/dashboards/00000000-0000-0000-0000-000000000000/edit",
        bundle_name="pyc-metrics-bundle",
    )
    return
