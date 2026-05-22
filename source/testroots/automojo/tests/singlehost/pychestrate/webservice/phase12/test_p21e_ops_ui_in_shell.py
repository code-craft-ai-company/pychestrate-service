"""
.. module:: test_p21e_ops_ui_in_shell
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the deployed webhooks / guards /
               SLOs / release-channels surfaces render inside the
               unified site shell and import the right feature
               bundles (PR p21e -- ops UI-fill).

.. moduleauthor:: Automation Mojo LLC

Drives the new shell-served routes over real HTTP against the
deploy after a successful admin login. Asserts for each route:

* The response is HTML and status 200.
* The body contains the ``<pyc-site-shell>`` Custom Element open
  tag -- i.e. the page renders inside the shell.
* The body imports the prebuilt feature bundle that owns the
  route's view.

The four new routes + their owning bundles are:

* ``/blast-radius-guards`` -- ``pyc-infra-bundle`` (``<pyc-guards>``).
* ``/slos`` -- ``pyc-metrics-bundle`` (``<pyc-slos>``).
* ``/webhooks`` -- ``pyc-ops-bundle`` (``<pyc-webhooks>``).
* ``/release-channels`` -- ``pyc-ops-bundle``
  (``<pyc-release-channels>``).

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
            "p21e ops-ui-in-shell test needs admin credentials in env vars:",
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

        :param route_path: Shell route to fetch (e.g. ``/webhooks``).
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
    bundle_src = "/static/javascript/{}/index.js".format(bundle_name)
    testbase.assert_true(bundle_src in body)
    return


def _assert_bundle_served_as_javascript(*, bundle_name: str) -> None:
    """
        Assert a prebuilt feature bundle is reachable over the
        static-files surface with a JavaScript content type.

        :param bundle_name: Feature bundle base name.

        :returns: None.
    """
    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        response = client.get(
            "/static/javascript/{}/index.js".format(bundle_name)
        )

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("javascript" in content_type)
    return


def test_blast_radius_guards_page_renders_inside_site_shell():
    """
    **Feature: site-shell + ops-ui-fill**
    **Property: After a successful admin login, GET
    /blast-radius-guards returns an HTML page that mounts the
    ``<pyc-site-shell>`` Custom Element AND imports the
    ``pyc-infra-bundle.js`` script so the ``<pyc-guards>`` view
    mounts in the browser.**
    """
    _assert_shell_route(
        route_path="/blast-radius-guards",
        bundle_name="pyc-infra-bundle",
    )
    return


def test_slos_page_renders_inside_site_shell():
    """
    **Feature: site-shell + ops-ui-fill**
    **Property: After a successful admin login, GET /slos returns
    an HTML page that mounts the ``<pyc-site-shell>`` Custom
    Element AND imports the ``pyc-metrics-bundle.js`` script so the
    ``<pyc-slos>`` view mounts in the browser.**
    """
    _assert_shell_route(
        route_path="/slos",
        bundle_name="pyc-metrics-bundle",
    )
    return


def test_webhooks_page_renders_inside_site_shell():
    """
    **Feature: site-shell + ops-ui-fill**
    **Property: After a successful admin login, GET /webhooks
    returns an HTML page that mounts the ``<pyc-site-shell>``
    Custom Element AND imports the ``pyc-ops-bundle.js`` script so
    the ``<pyc-webhooks>`` view mounts in the browser.**
    """
    _assert_shell_route(
        route_path="/webhooks",
        bundle_name="pyc-ops-bundle",
    )
    return


def test_release_channels_page_renders_inside_site_shell():
    """
    **Feature: site-shell + ops-ui-fill**
    **Property: After a successful admin login, GET
    /release-channels returns an HTML page that mounts the
    ``<pyc-site-shell>`` Custom Element AND imports the
    ``pyc-ops-bundle.js`` script so the ``<pyc-release-channels>``
    view mounts in the browser.**
    """
    _assert_shell_route(
        route_path="/release-channels",
        bundle_name="pyc-ops-bundle",
    )
    return


def test_ops_bundle_is_served_as_javascript():
    """
    **Feature: site-shell + ops-ui-fill**
    **Property: The prebuilt ops bundle at
    ``/static/javascript/pyc-ops-bundle/index.js`` is reachable over
    the static-files surface and is served with a
    JavaScript-flavored Content-Type. No login required -- the
    bundle is a static asset.**
    """
    _assert_bundle_served_as_javascript(bundle_name="pyc-ops-bundle")
    return
