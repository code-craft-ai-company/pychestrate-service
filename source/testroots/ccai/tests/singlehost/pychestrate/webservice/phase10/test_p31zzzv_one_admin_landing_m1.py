"""
.. module:: test_p31zzzv_one_admin_landing_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: /admin is the one administration landing page (XC-18).

.. moduleauthor:: Code Craft AI LLC

Administration had two landing pages that did the same job with different
content and styling: ``/admin`` ("Administration", the bundle's overview) and
``/admin/dashboard`` ("Dashboard", six server-rendered cards), with
``/admin/overview`` a third address for the first. ``/admin`` is now the only
landing page (it carries a way in to each administration area, see
``phase13.test_p31zzzv_admin_overview_shortcuts_m1``), and the other two
addresses redirect to it so an old bookmark still works. These tests drive the
whole application.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)


RETIRED_LANDING_PATHS = ("/admin/dashboard", "/admin/overview")


def test_the_older_landing_addresses_send_an_administrator_to_admin():
    """
    **Feature: one admin landing page (XC-18)**
    **Property: an administrator who opens /admin/dashboard or
    /admin/overview is redirected permanently to /admin.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)

    outcomes = {}
    for path in RETIRED_LANDING_PATHS:
        response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path=path, cookies=cookies)
        outcomes[path] = (response.status_code, (response.header("Location") or "").split("?")[0])

    testbase.assert_equal(outcomes, {path: (301, "/admin") for path in RETIRED_LANDING_PATHS})
    return


def test_an_anonymous_visitor_meets_the_sign_in_page_first():
    """
    **Feature: one admin landing page (XC-18)**
    **Property: the redirect does not give a signed-out visitor a way round
    the sign-in: /admin/dashboard sends them to /login, not to /admin.**
    """
    handle = ensure_app()

    outcomes = {}
    for path in RETIRED_LANDING_PATHS:
        response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path=path, cookies={})
        outcomes[path] = (response.status_code in (302, 303), (response.header("Location") or "").split("?")[0].endswith("/login"))

    testbase.assert_equal(outcomes, {path: (True, True) for path in RETIRED_LANDING_PATHS})
    return


def test_admin_mounts_the_overview_and_no_longer_offers_the_dashboard():
    """
    **Feature: one admin landing page (XC-18)**
    **Property: GET /admin renders the overview's mount point inside the
    shell, and neither it nor the page's no-script text points at the retired
    dashboard.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)

    response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/admin", cookies=cookies)

    body = response.text
    testbase.assert_equal(
        (response.status_code, 'data-role="bundle-mount"' in body, "/admin/dashboard" in body, "Configuration Panel" in body),
        (200, True, False, False),
    )
    return


def test_a_cancel_link_that_led_to_the_dashboard_leads_to_admin():
    """
    **Feature: one admin landing page (XC-18)**
    **Property: the UI Profile page's Cancel link, which pointed at the
    dashboard, points at /admin (a link to a redirect would cost a request
    and leave the address bar wrong for a moment).**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)

    response = drive_request(wsgi_app=handle.wsgi_app, method="GET", path="/admin/ui-profile", cookies=cookies)

    body = response.text
    testbase.assert_equal(
        (response.status_code, 'href="/admin" class="btn btn-secondary">Cancel</a>' in body, "/admin/dashboard" in body),
        (200, True, False),
    )
    return
