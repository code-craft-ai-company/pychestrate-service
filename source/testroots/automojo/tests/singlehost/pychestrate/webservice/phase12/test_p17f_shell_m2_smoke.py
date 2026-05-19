"""
.. module:: test_p17f_shell_m2_smoke
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-12 smoke -- the deployed site-shell bundle
               carries the M2 features (palette dialog + degraded
               banner + session toast modules).

.. moduleauthor:: Automation Mojo LLC

Drives a real HTTP round trip after a successful admin login.
Asserts:

* ``GET /admin/dashboard`` renders inside the unified shell
  (same contract as ``test_p17e_admin_in_shell``).
* The shell bundle served at
  ``/static/javascript/dist/pyc-site-shell.js`` contains the M2
  module markers -- the palette dialog class name and the
  degraded-banner class name. The bundle is unminified per the
  build script, so a substring grep is the minimal sanity check
  that M2 actually shipped to the alpha host.

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


SHELL_BUNDLE_PATH: str = "/static/javascript/dist/pyc-site-shell.js"


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
            "p17f M2 smoke needs admin credentials in env vars:",
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


def test_shell_bundle_carries_m2_palette_module():
    """
    **Feature: site-shell M2**
    **Property: The deployed shell bundle includes the M2 palette
    dialog module markers AND the degraded-banner module markers,
    proving that the M2 feature surface shipped to the alpha
    host.**
    """
    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=False,
        ) as client:
        response = client.get(SHELL_BUNDLE_PATH)

    testbase.assert_equal(response.status_code, 200)
    body = response.text
    # Palette dialog module markers -- the class name and the
    # "Command Palette" aria label both appear in the unminified
    # source.
    testbase.assert_true("PaletteDialog" in body)
    testbase.assert_true("Command Palette" in body)
    # Degraded banner marker.
    testbase.assert_true("pyc-site-shell__degraded-banner" in body)
    # Session-expired toast marker.
    testbase.assert_true("pyc-site-shell__session-toast" in body)
    return


def test_admin_dashboard_still_renders_inside_shell_with_m2_bundle():
    """
    **Feature: site-shell M2 (regression coverage)**
    **Property: After upgrading to the M2 bundle, the admin
    dashboard continues to mount inside the unified shell -- the
    same contract guarded by ``test_p17e_admin_in_shell``, re-run
    here so a M2 regression that breaks shell mount is caught by
    the M2 baseline rather than only by the M1 baseline.**
    """
    login_name, password = _resolve_admin_credentials()

    with httpx.Client(
            base_url=BASE_URL,
            timeout=REQUEST_TIMEOUT_SECONDS,
            follow_redirects=True,
        ) as client:
        client.get("/login")
        login_response = client.post(
            "/login",
            data={"username": login_name, "password": password},
        )
        testbase.assert_equal(login_response.status_code, 200)
        response = client.get("/admin/dashboard")

    testbase.assert_equal(response.status_code, 200)
    content_type = response.headers.get("content-type", "")
    testbase.assert_true("text/html" in content_type)
    body = response.text
    testbase.assert_true("<pyc-site-shell" in body)
    testbase.assert_true(SHELL_BUNDLE_PATH in body)
    return
