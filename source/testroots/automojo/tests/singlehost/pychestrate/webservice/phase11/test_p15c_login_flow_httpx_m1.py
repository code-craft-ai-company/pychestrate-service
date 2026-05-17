"""
.. module:: test_p15c_login_flow_httpx_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HTTP-level login-flow tests against the deployed
               pychestrate instance.

.. moduleauthor:: Automation Mojo LLC

Drives the consumer-UI login surface over real HTTP. No
browser. Uses ``httpx.Client`` with a cookie jar so the session
cookie minted on a successful POST is honored by the follow-up
dashboard fetch.

Credentials
-----------

The test suite reads admin credentials from two environment
variables; both must be set for these tests to run. When
either is unset the tests raise
``automojo.errors.exceptions.SkipError`` so the suite stays
green on CI runners that haven't been wired with the deploy's
admin password.

* :data:`ENV_ADMIN_LOGIN` -- the admin user's ``login_name``.
* :data:`ENV_ADMIN_PASSWORD` -- the admin user's plaintext
  password.

Example local invocation::

    export PYCHESTRATE_TEST_ADMIN_LOGIN=myron
    export PYCHESTRATE_TEST_ADMIN_PASSWORD='whatever-you-set'
    .venv/bin/testbase testing run \\
        --root source/testroots/automojo \\
        --includes=automojo.tests.singlehost.pychestrate.webservice.phase11 \\
        --output=./.output

Wire the same env vars as GitHub Actions secrets (e.g.
``PYCHESTRATE_TEST_ADMIN_LOGIN`` / ``..._PASSWORD``) and these
tests run in CI without code changes.
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


# Per-request timeout. Generous enough for a cold cookie-mint
# round trip through nginx, tight enough that a hung server
# fails fast rather than blocking the suite.
REQUEST_TIMEOUT_SECONDS: float = 10.0


# Test-credential env vars. Both must be set or the tests skip.
ENV_ADMIN_LOGIN: str = "PYCHESTRATE_TEST_ADMIN_LOGIN"
ENV_ADMIN_PASSWORD: str = "PYCHESTRATE_TEST_ADMIN_PASSWORD"


def _resolve_admin_credentials() -> Tuple[str, str]:
    """
        Read admin credentials from the environment. Raise
        :class:`SkipError` if either var is unset/empty so the
        test is reported as SKIPPED rather than failing on CI
        runners that haven't been wired with the secrets.

        :returns: ``(login_name, password)`` tuple.

        :raises: :class:`SkipError` when either env var is
                 unset.
    """
    login_name = os.environ.get(ENV_ADMIN_LOGIN, "")
    password = os.environ.get(ENV_ADMIN_PASSWORD, "")

    if len(login_name) == 0 or len(password) == 0:
        err_msg_lines = [
            "Login-flow tests need admin credentials in env vars:",
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


def test_login_post_with_valid_credentials_redirects_to_config():
    """
    **Feature: consumer-ui-login**
    **Property: POST /config/login with valid admin credentials
    returns a 303 redirect whose Location points under
    /config/.**
    """
    login_name, password = _resolve_admin_credentials()

    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        # GET the form first so any prep cookies are in the jar.
        client.get("/config/login")

        response = client.post(
            "/config/login",
            data={"username": login_name, "password": password},
        )

        testbase.assert_equal(response.status_code, 303)
        location = response.headers.get("location", "")
        testbase.assert_true(location.startswith("/config"))
    return


def test_authenticated_session_grants_dashboard_access():
    """
    **Feature: consumer-ui-login**
    **Property: After a successful POST /config/login, the
    cookie jar grants access to the post-login destination
    (200, not a login-form redirect).**
    """
    login_name, password = _resolve_admin_credentials()

    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
        client.get("/config/login")
        response = client.post(
            "/config/login",
            data={"username": login_name, "password": password},
        )

        testbase.assert_equal(response.status_code, 200)
        # Final URL after following the 303 should NOT be the
        # login page itself -- that would indicate an auth
        # failure that bounced us back.
        final_path = str(response.url.path)
        testbase.assert_true(final_path.startswith("/config"))
        testbase.assert_true(final_path != "/config/login")
    return


def test_login_post_with_wrong_password_does_not_authenticate():
    """
    **Feature: consumer-ui-login**
    **Property: POST /config/login with the right username but
    a wrong password does NOT issue a 303 redirect -- the
    response is a 4xx with the form re-rendered.**
    """
    login_name, _ = _resolve_admin_credentials()

    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        client.get("/config/login")
        response = client.post(
            "/config/login",
            data={
                "username": login_name,
                "password": "obviously-not-the-right-password",
            },
        )

        # Per ``config/routes.handle_login_submit``: bad creds
        # re-render the login form with status 401 (or 400 if
        # the form fails earlier validation). Either is a
        # rejection; neither is a 303.
        rejected_codes = (400, 401)
        testbase.assert_true(response.status_code in rejected_codes)
        # And no redirect Location header.
        location = response.headers.get("location", None)
        testbase.assert_true(location is None or len(location) == 0)
    return
