"""
.. module:: test_p17e_admin_in_shell
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the deployed /admin/* surface
               renders inside the unified site shell and imports
               the admin sidebar bundle (PR p17e / PR4 of the
               unified-login refactor).

.. moduleauthor:: Automation Mojo LLC

Drives ``GET /admin/dashboard`` over real HTTP against the deploy
after a successful admin login. Asserts:

* The response is HTML and status 200.
* The body contains the ``<pyc-site-shell>`` Custom Element open
  tag -- i.e. the page renders inside the shell, NOT as the
  legacy standalone admin HTML.
* The body imports the prebuilt admin bundle at
  ``/static/javascript/pyc-admin-bundle/index.js`` so the admin
  sidebar group registers when the shell mounts in the browser.
* The admin bundle itself is served as JavaScript by the static
  file surface.

Credentials follow the phase-11 contract -- ``PYCHESTRATE_TEST_ADMIN_LOGIN``
+ ``PYCHESTRATE_TEST_ADMIN_PASSWORD`` -- and the test skips when
either env var is unset.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

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
            "p17e visibility test needs admin credentials in env vars:",
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


def test_admin_dashboard_renders_inside_site_shell():
    """
    **Feature: site-shell + admin-ui**
    **Property: After a successful admin login, GET /admin/dashboard
    returns an HTML page that mounts the ``<pyc-site-shell>`` Custom
    Element AND imports the ``pyc-admin-bundle.js`` script so the
    admin sidebar group registers in the browser.**
    """
    login_name, password = _resolve_admin_credentials()

    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
        # Mint a session cookie.
        client.get("/login")
        login_response = client.post(
            "/login",
            data={"username": login_name, "password": password},
        )
        testbase.assert_equal(login_response.status_code, 200)

        # Fetch the admin dashboard with the cookie jar populated.
        response = client.get("/admin/dashboard")

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("text/html" in content_type)

    body = response.text
    # Renders inside the shell, not the old standalone admin HTML.
    testbase.assert_true("<pyc-site-shell" in body)
    # The admin bundle <script> tag is present so the sidebar
    # registration runs on this navigation.
    testbase.assert_true(
        "/static/javascript/pyc-admin-bundle/index.js" in body
    )
    return


def test_admin_bundle_is_served_as_javascript():
    """
    **Feature: site-shell + admin-ui**
    **Property: The prebuilt admin bundle at
    ``/static/javascript/pyc-admin-bundle/index.js`` is reachable
    over the static-files surface and is served with a
    JavaScript-flavored Content-Type. No login required -- the
    bundle is a static asset.**
    """
    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        response = client.get(
            "/static/javascript/pyc-admin-bundle/index.js"
        )

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    js_content_types = ("javascript",)
    matched = False
    for token in js_content_types:
        if token in content_type:
            matched = True
            break
    testbase.assert_true(matched)
    return
