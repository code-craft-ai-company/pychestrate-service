"""
.. module:: test_p31i_adm_permission_denied_page_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A refused admin page answers the shared 403 page naming
               the missing permission (audit ADM-21).

.. moduleauthor:: Code Craft AI LLC

The enrollment token, UI profile and RPA job type pages redirected a
refused user to the dashboard with a flash, the other admin pages
answered a 403 that did not say which permission was missing, and the
admin overview's tiles said "unavailable" for a 403. These tests sign
in as a user with no roles and read what the pages say.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import os

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_DIRECTORIES

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    app,
    get,
    post_form,
    unique_name,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    login_via_post,
)


_PASSWORD: str = "Granite-Harbor-47!"

_ADMIN_BUNDLE_DIR = os.path.join(
    SITE_DIRECTORIES.DIR_STATIC, "javascript", "pyc-admin-bundle"
)

_NO_ROLE_COOKIES = {}


def _no_role_cookies():
    """
        Sign in as a user who holds no role (created once per run).
    """
    if len(_NO_ROLE_COOKIES) == 0:
        login_name = unique_name(prefix="norole")
        response = post_form(
            path="/admin/users/create",
            fields={"username": login_name, "email": "{}@example.com".format(login_name),
                    "password": _PASSWORD, "display_name": "No Role"},
            cookies=admin_cookies(),
        )
        testbase.assert_equal(response.status_code, 303)
        login_response, cookies = login_via_post(wsgi_app=app(), login=login_name, password=_PASSWORD)
        testbase.assert_equal(login_response.status_code, 303)
        _NO_ROLE_COOKIES.update(cookies)
    rtnval = dict(_NO_ROLE_COOKIES)
    return rtnval


def _refused(*, path: str):
    response = get(path=path, cookies=_no_role_cookies())
    rtnval = (response.status_code, html.unescape(response.text))
    return rtnval


def test_enrollment_tokens_refuse_with_a_403_naming_the_permission():
    """
    **Feature: permission-denied page (ADM-21)**
    **Property: a user without system:resources.manage gets the 403
    page naming that permission, not a redirect to the dashboard.**
    """
    status, text = _refused(path="/admin/enrollment-tokens")
    testbase.assert_equal(status, 403)
    testbase.assert_true('"system:resources.manage" permission' in text, text[-1500:])
    return


def test_ui_profile_refuses_with_a_403_naming_the_permission():
    """
    **Feature: permission-denied page (ADM-21)**
    **Property: a user without system:ui.profile.manage gets the 403
    page naming that permission.**
    """
    status, text = _refused(path="/admin/ui-profile")
    testbase.assert_equal(status, 403)
    testbase.assert_true('"system:ui.profile.manage" permission' in text, text[-1500:])
    return


def test_rpa_job_types_refuse_with_a_403_naming_the_read_permission():
    """
    **Feature: permission-denied page (ADM-21)**
    **Property: the RPA job type list refuses a user without
    system:rpa.read with the 403 page naming it.**
    """
    status, text = _refused(path="/admin/rpa-job-types")
    testbase.assert_equal(status, 403)
    testbase.assert_true('"system:rpa.read" permission' in text, text[-1500:])
    return


def test_the_403_page_says_what_the_permission_covers_and_who_grants_it():
    """
    **Feature: permission-denied page (ADM-21)**
    **Property: the 403 page quotes the permission's catalog
    description and the built-in roles that grant it.**
    """
    status, text = _refused(path="/admin/users")
    testbase.assert_equal(status, 403)
    testbase.assert_true('"system:users.read" permission' in text, text[-1500:])
    testbase.assert_true("It covers:" in text, "description missing")
    testbase.assert_true("system-admin" in text, "granting roles missing")
    return


def test_the_admin_overview_tiles_name_the_missing_permission():
    """
    **Feature: permission-denied page (ADM-21)**
    **Property: the admin overview's tiles report a 403 through the
    shared message that names the permission instead of saying
    "unavailable".**
    """
    with open(os.path.join(_ADMIN_BUNDLE_DIR, "admin-overview-view.js"), encoding="utf-8") as handle:
        source = handle.read()
    testbase.assert_equal("registry unavailable" in source, False)
    testbase.assert_equal("health unavailable" in source, False)
    testbase.assert_true("read_required_permission(response)" in source, "403 permission not read")
    return


def test_the_served_admin_bundle_is_rebuilt_from_the_source():
    """
    **Feature: permission-denied page (ADM-21)**
    **Property: the committed admin bundle the browser loads carries
    the permission-naming messages.**
    """
    with open(os.path.join(_ADMIN_BUNDLE_DIR, "index.js"), encoding="utf-8") as handle:
        built = handle.read()
    testbase.assert_equal("Extension registry unavailable." in built, False)
    testbase.assert_true("async function read_required_permission" in built, "bundle not rebuilt")
    return
