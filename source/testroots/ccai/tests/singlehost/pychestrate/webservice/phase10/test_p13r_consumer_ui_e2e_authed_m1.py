"""
.. module:: test_p13r_consumer_ui_e2e_authed_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tier-2 end-to-end tests for the consumer UI --
               login flow, authenticated dashboard render, and a
               full CRUD round-trip.

.. moduleauthor:: Code Craft AI LLC

PR p13q (#154) shipped Tier-1 E2E coverage: anonymous paths
returning 200 / 302 / 404 cleanly under real WSGI driving. This
module extends that coverage to the authenticated half of the
surface:

* Login POST happy path -- seed an admin user, POST credentials,
  verify a 303 redirect with a signed session cookie carrying
  user_id + session_token + csrf_token.
* Login POST bad creds -- POST with the wrong password, verify
  401 + generic flash.
* Login POST unknown username -- same 401 + same generic flash
  (no info leak).
* Authenticated dashboard render -- log in, GET /config with the
  cookie, verify the dashboard HTML.
* Logout -- POST /logout, verify the cookie clears and
  the next dashboard hit redirects to login.
* CRUD round-trip on global variables -- log in, render the
  create form (capture CSRF), POST a new variable, verify the
  list page now contains it.

The harness (bootstrap singleton, WSGI driver, SQLite-compat
shims, admin-seed helpers, login helpers) lives in
:mod:`._e2e_harness`; this module imports the public names and
focuses on the assertions.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import secrets

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    cookie_session,
    csrf,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    decode_session_cookie,
    drive_request,
    ensure_app,
    ensure_seeded_admin,
    extract_csrf_token_from_cookies,
    logged_in_cookies,
    login_via_post,
)


# ===========================================================================
# Login POST
# ===========================================================================


def test_login_post_happy_path_redirects_to_safe_target():
    """
    **Feature: consumer UI e2e tier-2 T15.1 (p17b)**
    **Property: POST /login with valid credentials
    returns 303 to a same-origin path and sets a session cookie
    whose decoded payload carries the user_id, the session_token,
    and a CSRF token. With no ``next`` param the same-origin
    fallback is ``/`` per 1-authentication Requirement 5.4.**
    """
    handle = ensure_app()
    admin = ensure_seeded_admin()
    response, cookies = login_via_post(
        wsgi_app=handle.wsgi_app,
        login=admin.login,
        password=admin.password,
    )
    testbase.assert_equal(response.status_code, 303)
    location = response.header("Location")
    testbase.assert_equal(
        location is not None
        and location.startswith("/")
        and not location.startswith("//"),
        True,
    )
    testbase.assert_equal(
        cookie_session.COOKIE_NAME in cookies, True
    )
    payload = decode_session_cookie(
        cookie_value=cookies[cookie_session.COOKIE_NAME]
    )
    testbase.assert_equal(payload is None, False)
    testbase.assert_equal(
        payload.get(auth_guard.SESSION_USER_ID_KEY), admin.user_id
    )
    has_session_token = (
        payload.get(auth_guard.SESSION_TOKEN_KEY) is not None
        and len(payload.get(auth_guard.SESSION_TOKEN_KEY)) > 0
    )
    has_csrf_token = (
        payload.get(csrf.SESSION_KEY) is not None
        and len(payload.get(csrf.SESSION_KEY)) > 0
    )
    testbase.assert_equal(has_session_token, True)
    testbase.assert_equal(has_csrf_token, True)
    return


def test_login_post_bad_credentials_renders_login_with_401():
    """
    **Feature: consumer UI e2e tier-2 T15.2**
    **Property: POST /login with the right username but
    the wrong password re-renders the login form with status
    401 and a generic "Invalid username or password" flash --
    the response must NOT leak that the username exists.**
    """
    handle = ensure_app()
    admin = ensure_seeded_admin()
    response, cookies = login_via_post(
        wsgi_app=handle.wsgi_app,
        login=admin.login,
        password="wrong-password-{}".format(secrets.token_hex(4)),
    )
    testbase.assert_equal(response.status_code, 401)
    body = response.text
    has_form = "<form" in body
    testbase.assert_equal(has_form, True)
    has_invalid_message = "Invalid username or password" in body
    testbase.assert_equal(has_invalid_message, True)
    # The body must NOT carry user_id; an unauthenticated session
    # cookie may still be set (for the flash + CSRF) but its
    # payload must not include a SESSION_USER_ID_KEY.
    if cookie_session.COOKIE_NAME in cookies:
        payload = decode_session_cookie(
            cookie_value=cookies[cookie_session.COOKIE_NAME]
        )
        if payload is not None:
            testbase.assert_equal(
                payload.get(auth_guard.SESSION_USER_ID_KEY), None
            )
    return


def test_login_post_with_unknown_username_returns_401_no_leak():
    """
    **Feature: consumer UI e2e tier-2 T15.3**
    **Property: POST /login with a username that does
    not exist returns the same 401 + same generic flash as a
    bad password -- timing channel aside, the surface text
    must not differ.**
    """
    handle = ensure_app()
    response, _cookies = login_via_post(
        wsgi_app=handle.wsgi_app,
        login="no-such-user-{}".format(secrets.token_hex(4)),
        password="any-password",
    )
    testbase.assert_equal(response.status_code, 401)
    has_invalid_message = (
        "Invalid username or password" in response.text
    )
    testbase.assert_equal(has_invalid_message, True)
    return


# ===========================================================================
# Authenticated dashboard render
# ===========================================================================


def test_authenticated_dashboard_renders_for_logged_in_user():
    """
    **Feature: consumer UI e2e tier-2 T15.4**
    **Property: After a successful login POST, GET /config with
    the captured cookies renders the dashboard (200) without
    redirecting back to the login page.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)

    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/admin",
        cookies=cookies,
    )
    # The dashboard handler may return a 200 directly OR redirect
    # via 302/303 to /admin/dashboard depending on which alias
    # the route table fires. Either way we must NOT see a
    # redirect to /login.
    location = response.header("Location") or ""
    redirected_to_login = location.split("?")[0].endswith("/login")
    testbase.assert_equal(redirected_to_login, False)

    # Follow any internal redirect to /admin/dashboard.
    if response.status_code in (301, 302, 303, 307, 308):
        target = response.header("Location") or "/admin/dashboard"
        if target.startswith("http"):
            from urllib.parse import urlparse
            parsed = urlparse(target)
            target = parsed.path
        response = drive_request(
            wsgi_app=handle.wsgi_app,
            method="GET",
            path=target,
            cookies=cookies,
        )

    testbase.assert_equal(response.status_code, 200)
    body = response.text
    has_html_doctype = (
        "<!DOCTYPE html" in body or "<html" in body
    )
    testbase.assert_equal(has_html_doctype, True)
    has_login_form = (
        '<form' in body
        and 'name="username"' in body
        and 'name="password"' in body
    )
    testbase.assert_equal(has_login_form, False)
    return


# ===========================================================================
# Logout
# ===========================================================================


def test_logout_clears_session_and_subsequent_dashboard_redirects():
    """
    **Feature: consumer UI e2e tier-2 T15.5**
    **Property: POST /logout clears the session cookie
    (or returns one without ``user_id``) and a follow-up GET
    /config 302s back to /login.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    payload = decode_session_cookie(
        cookie_value=cookies[cookie_session.COOKIE_NAME]
    )
    csrf_token = payload.get(csrf.SESSION_KEY, "")
    body = "csrf_token={}".format(csrf_token).encode("utf-8")

    logout_response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="POST",
        path="/logout",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        cookies=cookies,
    )
    is_redirect = logout_response.status_code in (302, 303)
    testbase.assert_equal(is_redirect, True)
    location = logout_response.header("Location") or ""
    redirected_to_login = location.split("?")[0].endswith("/login")
    testbase.assert_equal(redirected_to_login, True)

    new_cookies = logout_response.collect_set_cookies()
    refreshed_jar = dict(cookies)
    for name, value in new_cookies.items():
        refreshed_jar[name] = value

    next_response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/admin",
        cookies=refreshed_jar,
    )
    is_redirect_after_logout = next_response.status_code in (
        301, 302, 303, 307, 308
    )
    testbase.assert_equal(is_redirect_after_logout, True)
    testbase.assert_equal(
        (next_response.header("Location") or "").split("?")[0].endswith(
            "/login"
        ),
        True,
    )
    return


# ===========================================================================
# CRUD round-trip: global variable
# ===========================================================================


def test_crud_roundtrip_create_and_list_global_variable():
    """
    **Feature: consumer UI e2e tier-2 T15.6**
    **Property: A logged-in user can hit
    GET /admin/variables/create, POST a new variable with the
    captured CSRF token, follow the redirect to
    /admin/variables, and see the new variable's name in the
    list HTML. Exercises the full
    cookie-based-session + CSRF-validated-POST + jinja-list-
    rendering loop end-to-end.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    csrf_token = extract_csrf_token_from_cookies(cookies=cookies)
    testbase.assert_equal(
        csrf_token is not None and len(csrf_token) > 0, True
    )

    create_form = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/admin/variables/create",
        cookies=cookies,
    )
    testbase.assert_equal(create_form.status_code, 200)

    var_name = "e2e_var_{}".format(secrets.token_hex(4))
    body = (
        "csrf_token={csrf}"
        "&name={name}"
        "&value=hello-e2e"
        "&var_type=string"
        "&description=created+by+e2e+test"
    ).format(csrf=csrf_token, name=var_name).encode("utf-8")

    create_response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="POST",
        path="/admin/variables/create",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        cookies=cookies,
    )
    is_redirect = create_response.status_code in (302, 303)
    testbase.assert_equal(is_redirect, True)
    target = create_response.header("Location") or ""
    landed_at_list = target.endswith("/admin/variables")
    testbase.assert_equal(landed_at_list, True)

    list_response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/admin/variables",
        cookies=cookies,
    )
    testbase.assert_equal(list_response.status_code, 200)
    has_new_variable = var_name in list_response.text
    testbase.assert_equal(has_new_variable, True)
    return
