"""
.. module:: test_p21f_admin_consolidation_in_shell
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the deployed shell-native admin
               surface (overview / feature-flags / extension-registry
               / system-health) renders inside the site shell with
               the admin bundle (PR p21f -- audit items 9-admin-ui +
               E-extension-registry-ui).

.. moduleauthor:: Automation Mojo LLC

Drives the new shell-native admin routes over real HTTP against
the deploy after a successful admin login. Asserts:

* ``GET /admin`` returns a 200 HTML shell document that mounts the
  ``<pyc-site-shell>`` Custom Element and imports the prebuilt
  ``pyc-admin-bundle.js`` -- the bundle replaces the shell ``<main>``
  with ``<pyc-admin-overview>`` client-side.
* ``GET /admin/extensions`` returns a 200 shell document with the
  admin bundle.
* ``GET /api/v1/system/health`` returns the aggregate
  system-health document the overview tile consumes.

Credentials follow the phase-11 contract --
``PYCHESTRATE_TEST_ADMIN_LOGIN`` + ``PYCHESTRATE_TEST_ADMIN_PASSWORD``
-- and the test skips when either env var is unset.
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
            "p21f admin-consolidation test needs admin credentials:",
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


def _login_client() -> httpx.Client:
    """
        Build an httpx client with a populated admin session cookie
        jar.

        :returns: An authenticated :class:`httpx.Client`.
    """
    login_name, password = _resolve_admin_credentials()
    client = httpx.Client(
        base_url=BASE_URL,
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    )
    client.get("/login")
    login_response = client.post(
        "/login",
        data={"username": login_name, "password": password},
    )
    testbase.assert_equal(login_response.status_code, 200)
    rtnval = client
    return rtnval


def test_admin_overview_renders_inside_site_shell():
    """
    **Feature: 9-admin-ui PR p21f**
    **Property: After a successful admin login, GET /admin returns
    a 200 HTML shell document that mounts ``<pyc-site-shell>`` and
    imports ``pyc-admin-bundle.js`` -- the bundle mounts the
    shell-native ``<pyc-admin-overview>`` view client-side.**
    """
    client = _login_client()
    try:
        response = client.get("/admin")
    finally:
        client.close()

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("text/html" in content_type)

    body = response.text
    testbase.assert_true("<pyc-site-shell" in body)
    testbase.assert_true(
        "/static/javascript/pyc-admin-bundle/index.js" in body
    )
    return


def test_admin_extensions_route_renders_inside_site_shell():
    """
    **Feature: E-extension-registry-ui PR p21f**
    **Property: GET /admin/extensions returns a 200 HTML shell
    document with the admin bundle -- the bundle mounts the
    shell-native ``<pyc-extension-registry>`` view client-side.**
    """
    client = _login_client()
    try:
        response = client.get("/admin/extensions")
    finally:
        client.close()

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("text/html" in content_type)

    body = response.text
    testbase.assert_true("<pyc-site-shell" in body)
    testbase.assert_true(
        "/static/javascript/pyc-admin-bundle/index.js" in body
    )
    return


def test_system_health_endpoint_returns_aggregate_document():
    """
    **Feature: 9-admin-ui PR p21f (system-health route)**
    **Property: GET /api/v1/system/health returns the aggregate
    ``{status, generated_at, subsystems}`` document the overview
    tile + ``<pyc-system-health>`` view consume.**
    """
    client = _login_client()
    try:
        response = client.get("/api/v1/system/health")
    finally:
        client.close()

    testbase.assert_equal(response.status_code, 200)
    body = response.json()
    testbase.assert_true("status" in body)
    testbase.assert_true("subsystems" in body)
    testbase.assert_true(len(body["subsystems"]) >= 1)
    return
