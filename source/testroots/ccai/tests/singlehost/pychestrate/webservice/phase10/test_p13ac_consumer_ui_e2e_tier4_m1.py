"""
.. module:: test_p13ac_consumer_ui_e2e_tier4_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tier-4 end-to-end coverage of the consumer UI --
               concurrent multi-user sessions, CSRF rotation,
               session expiry, post-logout invalidation.

.. moduleauthor:: Code Craft AI LLC

The previous tiers cover anonymous (p13q), authenticated
happy-path (p13r), and RBAC permission gating (p13v). This
module fills in the session-lifecycle properties:

* **Concurrent multi-user sessions** -- admin + viewer both
  authenticate; each cookie jar drives its own dashboard
  request without cross-talk.
* **CSRF rotation on re-login** -- a second successful
  login for the same user issues a *different* CSRF token;
  a form POST signed with the previous CSRF must be rejected.
* **Session expiry** -- forcibly back-date an
  :class:`AuthSession` row's ``expires_at`` and confirm a
  follow-up dashboard request is treated as anonymous.
* **Post-logout cookie invalidation** -- after
  ``POST /logout`` closes the underlying
  :class:`AuthSession`, the SAME cookie can no longer
  authorize requests (the modern adapter's
  ``validate_token`` returns ``None`` because
  ``resolve_session`` raises ``SessionNotFoundError``).
* **Deactivation** -- after an admin deactivates a user, the
  cookie that user already holds stops authorizing requests.

Builds on the Tier-3 PR's harness (PR #163) plus the modern
auth adapter (PR p13aa) -- session_id is a real
:class:`AuthSession` row and ``expires_at`` is a real
column we can manipulate.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import secrets

from datetime import datetime, timedelta, timezone

from ccai import testbase

from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
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
    ensure_seeded_viewer,
    extract_csrf_token_from_cookies,
    login_as,
    login_via_post,
    logged_in_cookies,
)


# ===========================================================================
# Concurrent sessions
# ===========================================================================


def test_admin_and_viewer_can_hold_concurrent_sessions():
    """
    **Feature: consumer UI tier-4 T19.1**
    **Property: An admin and a viewer can be logged in
    simultaneously; each cookie jar drives its own projects
    dashboard request without cross-talk. Decoded payloads from
    the two cookies carry distinct ``user_id`` / ``session_token``
    values, proving the modern :class:`AuthSession` rows are
    independent.**
    """
    handle = ensure_app()
    admin = ensure_seeded_admin()
    viewer = ensure_seeded_viewer()

    admin_cookies = login_as(wsgi_app=handle.wsgi_app, user=admin)
    viewer_cookies = login_as(wsgi_app=handle.wsgi_app, user=viewer)

    admin_payload = decode_session_cookie(
        cookie_value=admin_cookies[cookie_session.COOKIE_NAME]
    )
    viewer_payload = decode_session_cookie(
        cookie_value=viewer_cookies[cookie_session.COOKIE_NAME]
    )
    testbase.assert_equal(
        admin_payload[auth_guard.SESSION_USER_ID_KEY] !=
        viewer_payload[auth_guard.SESSION_USER_ID_KEY],
        True,
    )
    testbase.assert_equal(
        admin_payload[auth_guard.SESSION_TOKEN_KEY] !=
        viewer_payload[auth_guard.SESSION_TOKEN_KEY],
        True,
    )

    # Each cookie reaches its own projects dashboard. (Not the
    # admin dashboard: the viewer holds no admin permission, so
    # every /admin/* page answers it with a 403.)
    admin_response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/projects",
        cookies=admin_cookies,
    )
    viewer_response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/projects",
        cookies=viewer_cookies,
    )
    testbase.assert_equal(admin_response.status_code, 200)
    testbase.assert_equal(viewer_response.status_code, 200)

    # And neither response leaks the OTHER user's username
    # into its own body.
    testbase.assert_equal(
        viewer.login in admin_response.text, False
    )
    testbase.assert_equal(
        admin.login in viewer_response.text, False
    )
    return


# ===========================================================================
# CSRF rotation across re-login
# ===========================================================================


def test_relogin_issues_fresh_csrf_token():
    """
    **Feature: consumer UI tier-4 T19.2**
    **Property: A second successful login for the same user
    rotates the CSRF token. The two cookies carry different
    ``csrf_token`` payloads. Independently meaningful: the
    auth adapter generates a fresh CSRF on every
    ``authenticate`` call rather than re-using one across
    sessions.**
    """
    handle = ensure_app()
    admin = ensure_seeded_admin()

    response_a, cookies_a = login_via_post(
        wsgi_app=handle.wsgi_app,
        login=admin.login,
        password=admin.password,
    )
    testbase.assert_equal(response_a.status_code, 303)
    payload_a = decode_session_cookie(
        cookie_value=cookies_a[cookie_session.COOKIE_NAME]
    )
    csrf_a = payload_a.get(csrf.SESSION_KEY, "")

    response_b, cookies_b = login_via_post(
        wsgi_app=handle.wsgi_app,
        login=admin.login,
        password=admin.password,
    )
    testbase.assert_equal(response_b.status_code, 303)
    payload_b = decode_session_cookie(
        cookie_value=cookies_b[cookie_session.COOKIE_NAME]
    )
    csrf_b = payload_b.get(csrf.SESSION_KEY, "")

    testbase.assert_equal(len(csrf_a) > 0, True)
    testbase.assert_equal(len(csrf_b) > 0, True)
    testbase.assert_equal(csrf_a != csrf_b, True)
    # The session_token also rotates -- a fresh AuthSession row
    # backs each login.
    testbase.assert_equal(
        payload_a.get(auth_guard.SESSION_TOKEN_KEY) !=
        payload_b.get(auth_guard.SESSION_TOKEN_KEY),
        True,
    )
    return


def test_post_with_stale_csrf_after_relogin_is_rejected():
    """
    **Feature: consumer UI tier-4 T19.3**
    **Property: A POST signed with a stale CSRF token (from
    cookie A) presented alongside cookie B (a fresh login)
    is rejected by the CSRF guard. The handler 302s back to
    the form's fallback URL rather than processing the
    submission.**
    """
    handle = ensure_app()
    admin = ensure_seeded_admin()

    # Login A, capture csrf_a.
    _resp_a, cookies_a = login_via_post(
        wsgi_app=handle.wsgi_app,
        login=admin.login,
        password=admin.password,
    )
    csrf_a = extract_csrf_token_from_cookies(cookies=cookies_a)

    # Login B (overwrites the cookie in a real browser; here we
    # capture the new jar separately).
    _resp_b, cookies_b = login_via_post(
        wsgi_app=handle.wsgi_app,
        login=admin.login,
        password=admin.password,
    )

    # POST a "create global variable" form with the STALE
    # csrf_a but the FRESH cookies_b. Mismatch.
    var_name = "tier4_stale_csrf_{}".format(secrets.token_hex(4))
    body = (
        "csrf_token={csrf}"
        "&name={name}"
        "&value=stale-csrf-test"
        "&var_type=string"
    ).format(csrf=csrf_a, name=var_name).encode("utf-8")

    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="POST",
        path="/admin/variables/create",
        body=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
        cookies=cookies_b,
    )
    is_redirect = response.status_code in (301, 302, 303, 307, 308)
    testbase.assert_equal(is_redirect, True)
    # The CSRF guard's fallback URL on a /variables/create
    # POST is the create form itself.
    location = response.header("Location") or ""
    testbase.assert_equal(
        location.endswith("/admin/variables/create"), True
    )
    return


# ===========================================================================
# Session expiry
# ===========================================================================


def _force_expire_auth_session(*, session_id: str) -> None:
    """
        Back-date an :class:`AuthSession` row's ``expires_at``
        to one minute ago so the next ``resolve_session`` call
        treats it as expired.
    """
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthSession,
    )
    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    db_session = factory()
    try:
        row = (
            db_session.query(AuthSession)
            .filter(AuthSession.session_id == session_id)
            .first()
        )
        if row is None:
            raise AssertionError(
                "AuthSession {} not found for back-dating".format(
                    session_id
                )
            )
        row.expires_at = datetime.now(timezone.utc) - timedelta(
            minutes=1
        )
        db_session.commit()
    finally:
        try:
            db_session.close()
        except Exception:
            pass
    return


def test_expired_auth_session_redirects_dashboard_to_login():
    """
    **Feature: consumer UI tier-4 T19.4**
    **Property: After back-dating the
    :class:`AuthSession` row's ``expires_at``, the modern
    :func:`session_service.resolve_session` raises
    ``SessionExpiredError``, the adapter's
    ``validate_token`` returns ``None``, and the dashboard
    handler clears the cookie + redirects to login.**
    """
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    payload = decode_session_cookie(
        cookie_value=cookies[cookie_session.COOKIE_NAME]
    )
    session_id = payload.get(auth_guard.SESSION_TOKEN_KEY, "")
    testbase.assert_equal(len(session_id) > 0, True)

    _force_expire_auth_session(session_id=session_id)

    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/admin/dashboard",
        cookies=cookies,
    )
    is_redirect = response.status_code in (301, 302, 303, 307, 308)
    testbase.assert_equal(is_redirect, True)
    location = response.header("Location") or ""
    # Per 1-authentication Requirement 5.3 the redirect carries
    # a ``?next=<original-path>`` query string -- match the path
    # head, not the trailing characters.
    location_path = location.split("?", 1)[0]
    testbase.assert_equal(
        location_path.endswith("/login"), True
    )
    return


# ===========================================================================
# Post-logout invalidation
# ===========================================================================


def test_post_logout_cookie_cannot_re_authorize():
    """
    **Feature: consumer UI tier-4 T19.5**
    **Property: After ``POST /logout`` closes the
    underlying :class:`AuthSession` row, presenting the
    SAME cookie (without re-authenticating) does not
    re-authorize the dashboard. The adapter's
    ``validate_token`` returns ``None`` because
    ``resolve_session`` raises
    ``SessionNotFoundError``; the dashboard 302s to login.**
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
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
        },
        cookies=cookies,
    )
    is_redirect = logout_response.status_code in (302, 303)
    testbase.assert_equal(is_redirect, True)

    # Replay the ORIGINAL cookie jar (NOT the one the logout
    # response handed back). That cookie's session_token now
    # references a closed AuthSession row; the next dashboard
    # request must redirect to login.
    response = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/admin/dashboard",
        cookies=cookies,
    )
    # The redirect carries ``?next=<original-path>`` per
    # 1-authentication Requirement 5.3; match the path head
    # rather than the trailing chars.
    location = response.header("Location") or ""
    location_path = location.split("?", 1)[0]
    is_redirect_to_login = (
        response.status_code in (301, 302, 303, 307, 308)
        and location_path.endswith("/login")
    )
    testbase.assert_equal(is_redirect_to_login, True)
    return


# ===========================================================================
# Deactivation ends access (ADM-03)
# ===========================================================================


def test_deactivating_a_user_signs_out_their_open_session():
    """
    **Feature: consumer UI tier-4 (ADM-03)**
    **Property: when an admin deactivates a user through
    ``POST /admin/users/{id}/deactivate``, the cookie that user is
    already holding stops working at once -- their next request is
    sent to the login page instead of being served.**
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        identity_admin,
    )

    handle = ensure_app()
    admin = ensure_seeded_admin()
    login_name = "e2e-leaver-{}".format(secrets.token_hex(4))
    password = "Leaver-Pass-9!Word"
    db_session = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY()
    try:
        user_id = identity_admin.create_identity_user(
            db_session=db_session,
            username=login_name,
            email="{}@example.invalid".format(login_name),
            password=password,
            display_name="E2E Leaver",
            firstname="",
            lastname="",
            role_names=[],
            actor_user_id=None,
        )
    finally:
        db_session.close()

    _login_response, leaver_cookies = login_via_post(
        wsgi_app=handle.wsgi_app, login=login_name, password=password,
    )
    before = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/projects",
        cookies=leaver_cookies,
    )
    testbase.assert_equal(before.status_code, 200)

    admin_cookies = login_as(wsgi_app=handle.wsgi_app, user=admin)
    csrf_token = extract_csrf_token_from_cookies(cookies=admin_cookies)
    drive_request(
        wsgi_app=handle.wsgi_app,
        method="POST",
        path="/admin/users/{}/deactivate".format(user_id),
        body="csrf_token={}".format(csrf_token).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        cookies=admin_cookies,
    )

    after = drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/projects",
        cookies=leaver_cookies,
    )
    location_path = (after.header("Location") or "").split("?", 1)[0]
    testbase.assert_equal(
        (after.status_code in (301, 302, 303, 307, 308), location_path.endswith("/login")),
        (True, True),
    )
    return
