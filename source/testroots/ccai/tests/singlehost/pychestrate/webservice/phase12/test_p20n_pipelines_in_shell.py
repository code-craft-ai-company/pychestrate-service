"""
.. module:: test_p20n_pipelines_in_shell
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the deployed /pipelines surface
               renders inside the unified site shell and imports
               the pipelines bundle (PR p20n -- pipelines UI).

.. moduleauthor:: Code Craft AI LLC

Drives ``GET /pipelines`` over real HTTP against the deploy after a
successful admin login. Asserts:

* The response is HTML and status 200.
* The body contains the ``<pyc-site-shell>`` Custom Element open
  tag -- i.e. the page renders inside the shell.
* The body imports the prebuilt pipelines bundle at
  ``/static/javascript/pyc-pipelines-bundle/index.js`` so the
  ``<pyc-pipelines-list>`` view mounts when the shell connects.
* The pipelines bundle itself is served as JavaScript by the
  static file surface.

Credentials follow the phase-11 contract --
``PYCHESTRATE_TEST_ADMIN_LOGIN`` + ``PYCHESTRATE_TEST_ADMIN_PASSWORD``
-- and the test skips when either env var is unset.
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

from ccai.testshared.login_form import extract_login_csrf_token
from ccai.testshared.skip_helper import skip_test
from ccai.testshared.test_config import BASE_URL


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
            "p20n pipelines-in-shell test needs admin credentials in env vars:",
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
        form_response = client.get("/login")
        csrf_token = extract_login_csrf_token(html=form_response.text)
        login_response = client.post(
            "/login",
            data={
                "username": login_name,
                "password": password,
                "csrf_token": csrf_token,
            },
        )
        last_status = login_response.status_code
        if last_status == 200:
            return
        attempt = attempt + 1
        if attempt < LOGIN_MAX_ATTEMPTS:
            time.sleep(LOGIN_RETRY_DELAY_SECONDS)

    testbase.assert_equal(last_status, 200)
    return


def test_pipelines_page_renders_inside_site_shell():
    """
    **Feature: site-shell + pipelines-ui**
    **Property: After a successful admin login, GET /pipelines
    returns an HTML page that mounts the ``<pyc-site-shell>``
    Custom Element AND imports the ``pyc-pipelines-bundle.js``
    script so the pipelines sidebar entry registers and the
    ``<pyc-pipelines-list>`` view mounts in the browser.**
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

        # Fetch the pipelines page with the cookie jar populated.
        response = client.get("/pipelines")

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("text/html" in content_type)

    body = response.text
    # Renders inside the shell.
    testbase.assert_true("<pyc-site-shell" in body)
    # The pipelines bundle <script> tag is present so the view
    # mounts and the sidebar registration runs on this navigation.
    testbase.assert_true(
        "/static/javascript/pyc-pipelines-bundle/index.js" in body
    )
    return


def test_pipelines_bundle_is_served_as_javascript():
    """
    **Feature: site-shell + pipelines-ui**
    **Property: The prebuilt pipelines bundle at
    ``/static/javascript/pyc-pipelines-bundle/index.js`` is reachable
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
            "/static/javascript/pyc-pipelines-bundle/index.js"
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
