"""
.. module:: test_p17d_shell_document_renders
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the deployed pychestrate root
               serves the unified site-shell document.

.. moduleauthor:: Automation Mojo LLC

Logs in against the deploy, hits ``GET /``, and asserts that:

* The response is HTML.
* The response body contains the ``<pyc-site-shell>`` Custom
  Element open tag.
* The response body references the prebuilt shell bundle at
  ``/static/javascript/dist/pyc-site-shell.js``.

That's enough to confirm PR3's mount path works end-to-end (the
catch-all handler runs, the Jinja template renders, the static
file path is correctly emitted). Sidebar / palette / metrics
behavior arrives with M2/M3.

Since p19o landed the 1-authentication Requirement 5 catch-all
auth redirect, ``GET /`` for an anonymous browser 303-redirects
to ``/login``; the shell document only renders for an
authenticated session, so this test signs in first.
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
            "p17d shell test needs admin credentials in env vars:",
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


def test_root_path_serves_site_shell_document():
    """
    **Feature: site-shell**
    **Property: After a successful login, GET / on a deployed
    pychestrate instance returns an HTML document that mounts
    the ``<pyc-site-shell>`` Custom Element and imports the
    prebuilt ``/static/javascript/dist/pyc-site-shell.js``
    bundle. An anonymous GET / would 303-redirect to /login
    per 1-authentication Requirement 5.**
    """
    login_name, password = _resolve_admin_credentials()

    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        client.get("/login")
        login_response = client.post(
            "/login",
            data={"username": login_name, "password": password},
        )
        testbase.assert_equal(login_response.status_code, 303)

        response = client.get("/")

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("text/html" in content_type)

    body = response.text
    testbase.assert_true("<pyc-site-shell" in body)
    testbase.assert_true(
        "/static/javascript/dist/pyc-site-shell.js" in body
    )
    return


def test_anonymous_root_path_redirects_to_login():
    """
    **Feature: site-shell + 1-authentication Requirement 5**
    **Property: An anonymous GET / (no session cookie) on a
    deployed pychestrate instance 303-redirects to
    ``/login?next=%2F`` instead of serving the shell document.**
    """
    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        response = client.get("/")

    testbase.assert_equal(response.status_code, 303)
    location = response.headers.get("location", "")
    testbase.assert_true(location.endswith("/login?next=%2F"))
    return


def test_shell_bundle_is_served_as_javascript():
    """
    **Feature: site-shell**
    **Property: The prebuilt shell bundle at
    ``/static/javascript/dist/pyc-site-shell.js`` is reachable
    over the static-files surface and is served with a
    JavaScript-flavored Content-Type.**
    """
    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        response = client.get("/static/javascript/dist/pyc-site-shell.js")

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    # mimetypes resolves ".js" to either "application/javascript"
    # or "text/javascript" depending on platform; accept either.
    js_content_types = ("javascript",)
    matched = False
    for token in js_content_types:
        if token in content_type:
            matched = True
            break
    testbase.assert_true(matched)
    return
