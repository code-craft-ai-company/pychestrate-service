"""
.. module:: test_p19n_run_detail_in_shell
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the deployed /runs/{run_id} surface
               renders inside the unified site shell and imports the
               runs bundle (PR p19n -- run detail UI page).

.. moduleauthor:: Code Craft AI LLC

Drives ``GET /runs/{run_id}`` over real HTTP against the deploy
after a successful admin login. Asserts:

* The response is HTML and status 200 -- the run-detail route is
  not a shell-level 404; the shell catch-all serves the document
  and the JS-side router mounts ``<pyc-run-detail>``.
* The body contains the ``<pyc-site-shell>`` Custom Element open
  tag -- i.e. the page renders inside the shell.
* The body imports the prebuilt runs bundle at
  ``/static/javascript/pyc-runs-bundle/index.js`` so the
  ``<pyc-run-detail>`` view mounts when the shell connects.

No runs exist on the alpha, so the test asserts the shell + bundle
are served (not run content). Credentials follow the phase-11
contract -- ``PYCHESTRATE_TEST_ADMIN_LOGIN`` +
``PYCHESTRATE_TEST_ADMIN_PASSWORD`` -- and the test skips when
either env var is unset.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import time

from typing import Tuple

import httpx

from ccai import testbase

from ccai.testshared.skip_helper import skip_test
from ccai.testshared.test_config import BASE_URL


REQUEST_TIMEOUT_SECONDS: float = 10.0


ENV_ADMIN_LOGIN: str = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_ADMIN_PASSWORD: str = "PYCHESTRATE_TEST_ADMIN_PASSWORD"


# A syntactically valid UUID standing in for a run id. No run with
# this id exists on the alpha; the test only proves the route is
# shell-served, not that run content renders.
SAMPLE_RUN_ID: str = "12345678-1234-1234-1234-123456789abc"


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
            "p19n run-detail-in-shell test needs admin credentials in env vars:",
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
# failures (see ``security.auth.local_flow``); when the whole
# phase-11/12 suite fires several admin logins from one host in a
# few seconds the shared backoff window can briefly reject an
# otherwise-valid POST with a 401. A short retry rides through the
# window without masking a real authentication failure.
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


def test_run_detail_page_renders_inside_site_shell():
    """
    **Feature: site-shell + run-detail-ui**
    **Property: After a successful admin login, GET /runs/{run_id}
    returns an HTML page that mounts the ``<pyc-site-shell>``
    Custom Element AND imports the ``pyc-runs-bundle.js`` script so
    the ``<pyc-run-detail>`` view mounts in the browser. The route
    is shell-served, not a shell-level 404.**
    """
    login_name, password = _resolve_admin_credentials()

    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
        # Mint a session cookie (retries through the login backoff
        # window described on ``_login_admin``).
        _login_admin(
            client=client,
            login_name=login_name,
            password=password,
        )

        # Fetch the run-detail page with the cookie jar populated.
        response = client.get("/runs/" + SAMPLE_RUN_ID)

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("text/html" in content_type)

    body = response.text
    # Renders inside the shell -- the route is not a shell 404.
    testbase.assert_true("<pyc-site-shell" in body)
    # The runs bundle <script> tag is present so the detail view
    # mounts on this navigation.
    testbase.assert_true(
        "/static/javascript/pyc-runs-bundle/index.js" in body
    )
    return
