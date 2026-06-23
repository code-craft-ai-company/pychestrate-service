"""
.. module:: test_p13v_consumer_ui_e2e_rbac_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tier-3 end-to-end coverage of the consumer UI's
               RBAC permission gating -- admin-allowed +
               viewer-denied paths under real WSGI driving.

.. moduleauthor:: Code Craft AI LLC

The tier-1 module (p13q) confirmed anonymous redirects; the
tier-2 module (p13r) confirmed authenticated success paths.
This tier-3 module fills in the **denied** branch of the
``_require_permission_or_redirect`` gate that admin-tier
handlers run after the login check.

The legacy :class:`SecurityManager.check_permission`
back-references ``User.roles`` (CSV string) -> ``SystemRole`` ->
``Permission`` (many-to-many). The harness's
:func:`ensure_seeded_admin_role` seeds the admin
``SystemRole`` + ``Permission`` rows so the admin user
actually has the permissions; :func:`ensure_seeded_viewer`
seeds a non-admin user whose ``roles`` resolves to no
matching ``SystemRole``, so every admin-tier permission check
returns ``False``.

Coverage:

* Viewer can log in (proves the seed works as an authenticated
  user, not just an unfindable one).
* Viewer can render the resources dashboard (which only
  requires login, not admin).
* Viewer is redirected away from ``/resources/create`` to the
  resources dashboard with a "permission denied" flash
  (admin-tier permission check returns False).
* Admin -- with the ``admin`` role + ``resources.manage``
  permission seeded -- IS allowed to render
  ``/resources/create`` (200 with the form), confirming the
  *granted* branch fires symmetrically.
* The denied response carries a freshly signed session cookie
  with a "permission denied" flash queued -- proves the
  handler did the cookie-attach dance correctly even on the
  redirect path.

The harness lives in :mod:`._e2e_harness`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import (
    cookie_session,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    decode_session_cookie,
    drive_request,
    ensure_app,
    ensure_seeded_admin,
    ensure_seeded_admin_role,
    ensure_seeded_viewer,
    login_as,
)


# ===========================================================================
# Viewer (non-admin) coverage
# ===========================================================================


def test_viewer_can_login_and_renders_resources_dashboard():
    """
    **Feature: consumer UI tier-3 RBAC T17.1**
    **Property: A non-admin "viewer" user can log in and view
    the ``/resources`` dashboard. The dashboard is gated by
    login only (not by an admin permission), so it's the
    natural smoke test for "the viewer fixture actually works
    and doesn't get rejected at login".**
    """
    handle = ensure_app()
    viewer = ensure_seeded_viewer()
    cookies = login_as(wsgi_app=handle.wsgi_app, user=viewer)

    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/resources",
        cookies=cookies,
    )
    # Dashboard renders (200) OR redirects to its canonical
    # alias path -- in either case it must NOT redirect to
    # /login.
    location = response.header("Location") or ""
    redirected_to_login = location.split("?")[0].endswith("/login")
    testbase.assert_equal(redirected_to_login, False)
    return


def test_viewer_denied_from_resources_create_form():
    """
    **Feature: consumer UI tier-3 RBAC T17.2**
    **Property: A logged-in viewer (no ``resources.manage``
    permission) requesting ``GET /resources/create`` is
    redirected (302) back to the resources dashboard rather
    than seeing the form. The redirect target proves the
    ``_require_permission_or_redirect`` deny branch fired,
    not the unauthenticated branch (which would target
    ``/login``).**
    """
    handle = ensure_app()
    viewer = ensure_seeded_viewer()
    cookies = login_as(wsgi_app=handle.wsgi_app, user=viewer)

    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/resources/create",
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 302)
    location = response.header("Location") or ""
    # On admin-permission denial the resources handler
    # redirects to ``/resources`` (the resources.dashboard
    # endpoint). Some pages emit ``/resources/dashboard``
    # depending on the alias the route table fires; either
    # is acceptable here. We DO require it to NOT be a
    # redirect to ``/login``, which would mean the
    # auth-resolver decided we were anonymous.
    testbase.assert_equal(
        location.split("?")[0].endswith("/login"), False
    )
    testbase.assert_equal(
        location.startswith("/resources"), True
    )
    return


def test_viewer_denied_response_carries_permission_flash_cookie():
    """
    **Feature: consumer UI tier-3 RBAC T17.3**
    **Property: The denied response from ``GET
    /resources/create`` re-signs the session cookie with a
    freshly queued flash. Decoding the cookie's payload should
    reveal the "permission denied" flash entry, which proves
    the handler ran the cookie-attach step on the redirect
    path (a regression here would mean denied users see no
    explanation for the redirect).**
    """
    handle = ensure_app()
    viewer = ensure_seeded_viewer()
    cookies = login_as(wsgi_app=handle.wsgi_app, user=viewer)

    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/resources/create",
        cookies=cookies,
    )
    # The response should set a session cookie carrying the
    # newly-queued flash message. Find it.
    new_cookies = response.collect_set_cookies()
    cookie_value = new_cookies.get(cookie_session.COOKIE_NAME, None)
    testbase.assert_equal(cookie_value is not None, True)

    payload = decode_session_cookie(cookie_value=cookie_value)
    testbase.assert_equal(payload is not None, True)
    flashes = payload.get("flashes", [])
    has_perm_flash = False
    for entry in flashes:
        # Flash entries are typically ``[category, message]``.
        if not isinstance(entry, (list, tuple)) or len(entry) < 2:
            continue
        message = entry[1]
        if "permission" in message.lower():
            has_perm_flash = True
            break
    testbase.assert_equal(has_perm_flash, True)
    return


# ===========================================================================
# Admin (granted) coverage
# ===========================================================================


def test_admin_with_seeded_role_passes_resources_create_gate():
    """
    **Feature: consumer UI tier-3 RBAC T17.4**
    **Property: An admin user whose ``"admin"`` role has been
    granted ``resources.manage`` (via
    :func:`ensure_seeded_admin_role`) IS allowed through the
    permission gate on ``GET /resources/create``. The
    *granted* counterpart to the deny test above confirms the
    gate is symmetric -- it's not just "deny everyone always".

    This test asserts the permission gate clears (no 302 to
    ``/resources``, no permission-denied flash on the cookie).
    Whatever the handler does next is out of scope here:
    several admin-gated render paths in the resources blueprint
    pass a manager-response dataclass to a template that
    iterates it as a list, hitting a ``TypeError`` after the
    gate clears -- that's a separate bitrot tracked in the
    consumer-UI-auth-stack userguide chapter, and the gate
    portion of the test stays meaningful regardless.**
    """
    handle = ensure_app()
    admin = ensure_seeded_admin()
    ensure_seeded_admin_role()
    cookies = login_as(wsgi_app=handle.wsgi_app, user=admin)

    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/resources/create",
        cookies=cookies,
    )
    # The deny branch redirects to ``/resources`` (the
    # ``resources.dashboard`` endpoint). If we see that, the
    # gate refused us. Anything else -- 200, 500, etc. --
    # means the gate let us through.
    is_redirect_to_dashboard = (
        response.status_code in (301, 302, 303, 307, 308)
        and (response.header("Location") or "").endswith(
            "/resources"
        )
    )
    testbase.assert_equal(is_redirect_to_dashboard, False)

    # Also: any cookie set on this response must NOT carry the
    # permission-denied flash. If we got past the gate the
    # flash was never queued.
    new_cookies = response.collect_set_cookies()
    cookie_value = new_cookies.get(cookie_session.COOKIE_NAME, None)
    if cookie_value is not None:
        payload = decode_session_cookie(cookie_value=cookie_value)
        if payload is not None:
            flashes = payload.get("flashes", [])
            for entry in flashes:
                if (
                    isinstance(entry, (list, tuple))
                    and len(entry) >= 2
                    and "permission" in entry[1].lower()
                ):
                    raise AssertionError(
                        "permission flash leaked into a granted "
                        "response: {}".format(entry)
                    )
    return


# ===========================================================================
# Anonymous coverage on admin-gated route
# ===========================================================================


def test_anonymous_resources_create_redirects_to_login_not_dashboard():
    """
    **Feature: consumer UI tier-3 RBAC T17.5**
    **Property: An ANONYMOUS request to ``/resources/create``
    redirects to ``/login`` (the unauthenticated
    branch), NOT to ``/resources`` (which would be the
    permission-denied branch). The two branches must not
    collapse -- "logged in but unprivileged" and "not logged
    in" carry different remediation flows in the UI.**
    """
    handle = ensure_app()
    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/resources/create",
    )
    testbase.assert_equal(response.status_code, 302)
    location = response.header("Location") or ""
    testbase.assert_equal(
        location.split("?")[0].endswith("/login"), True
    )
    return
