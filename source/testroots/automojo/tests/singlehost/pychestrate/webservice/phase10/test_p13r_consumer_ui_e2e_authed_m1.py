"""
.. module:: test_p13r_consumer_ui_e2e_authed_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tier-2 end-to-end tests for the consumer UI --
               login flow, authenticated dashboard render, and a
               full CRUD round-trip.

.. moduleauthor:: Automation Mojo LLC

PR p13q (#154) shipped Tier-1 E2E coverage: anonymous paths
returning 200 / 302 / 404 cleanly under real WSGI driving. This
module extends that coverage to the authenticated half of the
surface:

* Login POST happy path -- seed an admin user, POST credentials,
  verify a 303 redirect with a signed session cookie.
* Login POST bad creds -- POST with the wrong password, verify
  the form re-renders (status 401) without leaking that the
  user exists.
* Authenticated dashboard render -- log in, GET /config with
  the cookie, verify the dashboard HTML and that the session
  cookie carries a CSRF token.
* Logout -- POST /config/logout, verify the cookie is cleared
  and the next dashboard hit redirects to login.
* CRUD round-trip on global variables -- log in, render the
  create form (capture CSRF), POST a new variable, verify the
  list page now contains it.

The harness is shared with p13q via direct imports of
``_ensure_app`` / ``_drive_request`` / ``_WsgiResponse`` -- the
runtime + persona singletons are process-global so two test
modules cannot bootstrap independently.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import secrets
import uuid

from typing import Any, Dict, List, Optional, Tuple

from automojo import testbase

from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from automojo.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    cookie_session,
    csrf,
)
from automojo.tests.singlehost.pychestrate.webservice.phase10.test_p13q_consumer_ui_e2e_smoke_m1 import (
    _TEST_UI_COOKIE_SECRET,
    _WsgiResponse,
    _drive_request,
    _ensure_app,
)


# ---------------------------------------------------------------------------
# Seed helpers (DB-backed)
# ---------------------------------------------------------------------------


_E2E_ADMIN_LOGIN: str = "e2e-admin"
_E2E_ADMIN_PASSWORD: str = "e2e-admin-secret-1!"
_E2E_ADMIN_EMAIL: str = "e2e-admin@example.invalid"


def _patch_utc_now_for_sqlite_tz_compat() -> None:
    """
        SQLAlchemy's :class:`DateTime(timezone=True)` columns
        round-trip through SQLite as naive datetimes (SQLite has
        no native tz support). The legacy
        :meth:`SecurityManager.validate_token` compares
        ``session.expires_at`` (naive on read-back) against
        ``utc_now()`` (timezone-aware) and raises
        ``TypeError: can't compare offset-naive and offset-aware
        datetimes``. The handler swallows the exception and
        treats the session as invalid.

        Monkey-patch :func:`utc_now` on the security_manager and
        defaults modules to return naive UTC so all comparisons
        agree. Idempotent. Production (Postgres) is unaffected
        because it preserves tzinfo.
    """
    from datetime import datetime, timezone  # noqa: E402
    from automojo.pychestrate.core import defaults as _defaults  # noqa: E402
    from automojo.pychestrate.core.managers import (  # noqa: E402
        security_manager as _sm,
    )

    def naive_utc_now() -> datetime:
        rtnval = datetime.now(timezone.utc).replace(tzinfo=None)
        return rtnval

    if getattr(_defaults.utc_now, "__name__", "") != "naive_utc_now":
        _defaults.utc_now = naive_utc_now
    if getattr(_sm.utc_now, "__name__", "") != "naive_utc_now":
        _sm.utc_now = naive_utc_now
    return


def _patch_legacy_pk_columns_for_sqlite() -> None:
    """
        SQLite only autoincrements ``INTEGER PRIMARY KEY`` columns
        (the type ``INTEGER`` exactly, in-line with the PRIMARY
        KEY declaration). Many legacy models declare their
        primary keys as ``BigInteger autoincrement=True``, which
        SQLAlchemy emits as ``BIGINT NOT NULL, PRIMARY KEY (...)``
        -- SQLite treats this as a non-rowid alias, so INSERTs
        without an explicit ``id`` raise an ``IntegrityError``.

        Walk every table on both metadata trees and rewrite any
        single-column ``BigInteger`` primary key to plain
        ``Integer`` plus the SQLite ``autoincrement`` table
        option, *before* any ``create_all`` runs. Idempotent
        across calls.

        Production schema management (Postgres + alembic) is
        unaffected -- this patch only mutates the in-process
        :class:`Column` objects loaded for tests.
    """
    import sqlalchemy as sa  # noqa: E402

    from automojo.pychestrate.core.orm import (  # noqa: E402
        PychestrateModelBase,
    )
    from automojo.pychestrate.webservice.persistence.schema import (  # noqa: E402
        PychestratePhase1Base,
    )

    metadatas = (
        PychestrateModelBase.metadata,
        PychestratePhase1Base.metadata,
    )
    for metadata in metadatas:
        for table in metadata.tables.values():
            pk_cols = list(table.primary_key.columns)
            if len(pk_cols) != 1:
                continue
            pk = pk_cols[0]
            if not pk.autoincrement:
                continue
            current_type = pk.type
            if type(current_type) is sa.Integer:
                continue
            if not isinstance(current_type, sa.BigInteger):
                continue
            pk.type = sa.Integer()
            table.dialect_options["sqlite"]["autoincrement"] = True
    return


def _ensure_shared_in_memory_db_pool() -> None:
    """
        ``sqlite:///:memory:`` defaults to ``NullPool``, which
        gives every checkout a fresh connection -- and in SQLite
        each connection has its own in-memory database. The
        runtime bootstrap therefore publishes an engine whose
        sessions cannot see each other's commits, so a row
        seeded by the test harness is invisible to the request
        handler that opens its own session.

        Swap the published engine for one that uses
        :class:`sqlalchemy.pool.StaticPool` so every checkout
        shares the single in-memory connection, and re-create
        every metadata's tables on the new engine. Idempotent --
        only swaps when the existing engine is the ``:memory:``
        flavor with the wrong pool class.
    """
    import sqlalchemy as sa  # noqa: E402
    from sqlalchemy.pool import StaticPool  # noqa: E402
    from sqlalchemy.orm import sessionmaker  # noqa: E402

    from automojo.pychestrate.webservice.persistence.schema import (  # noqa: E402
        PychestratePhase1Base,
    )
    from automojo.pychestrate.core.orm import (  # noqa: E402
        PychestrateModelBase,
    )

    engine = SITE_SHARED_GLOBALS.DATABASE_ENGINE
    if engine is None:
        return
    pool_cls_name = type(engine.pool).__name__
    if pool_cls_name == "StaticPool":
        return
    if "memory" not in str(engine.url):
        return

    # Patch BigInteger PKs to Integer BEFORE creating tables so
    # the legacy models autoincrement on SQLite.
    _patch_legacy_pk_columns_for_sqlite()
    # Make ``utc_now`` return naive datetimes so SQLite's
    # tzinfo-stripped read-back values stay comparable.
    _patch_utc_now_for_sqlite_tz_compat()

    new_engine = sa.create_engine(
        str(engine.url),
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Re-create both metadata trees on the new engine -- the
    # original engine's bootstrap-created tables are inaccessible
    # because each NullPool checkout was a fresh in-memory DB.
    PychestratePhase1Base.metadata.create_all(new_engine)
    PychestrateModelBase.metadata.create_all(new_engine)

    new_factory = sessionmaker(bind=new_engine, expire_on_commit=False)
    SITE_SHARED_GLOBALS.DATABASE_ENGINE = new_engine
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = new_factory
    return


class _SeededAdmin:
    """
        Bookkeeping handle for the seeded admin user.
    """

    def __init__(
            self, *, user_id: str, login: str, password: str
        ) -> None:
        self.user_id: str = user_id
        self.login: str = login
        self.password: str = password
        return


_SEEDED_ADMIN: Optional[_SeededAdmin] = None


def _ensure_seeded_admin() -> _SeededAdmin:
    """
        Module-level singleton: seed an admin user record + the
        matching :class:`PasswordHistory` row once, return the
        cached handle on subsequent calls. Idempotent across
        tests.
    """
    global _SEEDED_ADMIN
    if _SEEDED_ADMIN is not None:
        return _SEEDED_ADMIN

    _ensure_app()  # Bootstrap the runtime if not already.
    _ensure_shared_in_memory_db_pool()

    from werkzeug.security import generate_password_hash  # noqa: E402
    from automojo.pychestrate.core.orm import (  # noqa: E402
        PasswordHistory,
        User,
    )

    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    db_session = factory()
    try:
        existing = (
            db_session.query(User)
            .filter(User.login == _E2E_ADMIN_LOGIN)
            .first()
        )
        if existing is not None:
            _SEEDED_ADMIN = _SeededAdmin(
                user_id=str(existing.id),
                login=_E2E_ADMIN_LOGIN,
                password=_E2E_ADMIN_PASSWORD,
            )
            return _SEEDED_ADMIN

        user = User(
            id=uuid.uuid4(),
            first_name="E2E",
            last_name="Admin",
            display_name="E2E Admin",
            email=_E2E_ADMIN_EMAIL,
            login=_E2E_ADMIN_LOGIN,
            ownertag="e2e",
            status="active",
            roles="admin",
            authtype="internal",
        )
        db_session.add(user)
        db_session.flush()

        password_hash = generate_password_hash(_E2E_ADMIN_PASSWORD)
        history = PasswordHistory(
            user_id=user.id,
            password_hash=password_hash,
        )
        db_session.add(history)
        db_session.commit()

        _SEEDED_ADMIN = _SeededAdmin(
            user_id=str(user.id),
            login=_E2E_ADMIN_LOGIN,
            password=_E2E_ADMIN_PASSWORD,
        )
        return _SEEDED_ADMIN
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Cookie + CSRF helpers
# ---------------------------------------------------------------------------


def _decode_session_cookie(*, cookie_value: str) -> Dict[str, Any]:
    """
        Verify a session cookie's HMAC and return the decoded
        payload. Tests use this to extract the ``csrf_token`` /
        ``session_token`` an authenticated session carries.
    """
    rtnval = cookie_session.verify_session_payload(
        cookie_value=cookie_value,
        secret=_TEST_UI_COOKIE_SECRET,
    )
    return rtnval


def _login_via_post(
        *, wsgi_app: Any, login: str, password: str
    ) -> Tuple[_WsgiResponse, Dict[str, str]]:
    """
        Drive a login POST and return the response plus the
        cookie jar (the session cookie value). Callers reuse the
        cookies on subsequent authenticated requests.

        :returns: ``(response, cookies)`` -- ``cookies`` is empty
                  on failure.
    """
    body = (
        "username={username}&password={password}".format(
            username=login, password=password
        )
    ).encode("utf-8")
    response = _drive_request(
        wsgi_app=wsgi_app,
        method="POST",
        path="/config/login",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    cookies = response.collect_set_cookies()
    return (response, cookies)


def _logged_in_cookies(*, wsgi_app: Any) -> Dict[str, str]:
    """
        Convenience: seed the admin user, POST login, return the
        cookie jar suitable for follow-up authenticated requests.
        Raises if the login response is not 303.
    """
    admin = _ensure_seeded_admin()
    response, cookies = _login_via_post(
        wsgi_app=wsgi_app, login=admin.login, password=admin.password
    )
    if response.status_code != 303:
        raise AssertionError(
            "expected login POST to 303 -- got {} ({})".format(
                response.status_code, response.text[:120]
            )
        )
    return cookies


# ===========================================================================
# Login POST
# ===========================================================================


def test_login_post_happy_path_redirects_to_dashboard():
    """
    **Feature: consumer UI e2e tier-2 T15.1**
    **Property: POST /config/login with valid credentials
    returns 303 to /config/dashboard and sets a session cookie
    whose decoded payload carries the user_id, the session_token,
    and a CSRF token.**
    """
    handle = _ensure_app()
    admin = _ensure_seeded_admin()
    response, cookies = _login_via_post(
        wsgi_app=handle.wsgi_app,
        login=admin.login,
        password=admin.password,
    )
    testbase.assert_equal(response.status_code, 303)
    location = response.header("Location")
    testbase.assert_equal(
        location is not None
        and location.endswith("/config/dashboard"),
        True,
    )
    testbase.assert_equal(
        cookie_session.COOKIE_NAME in cookies, True
    )
    payload = _decode_session_cookie(
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
    **Property: POST /config/login with the right username but
    the wrong password re-renders the login form with status
    401 and a generic "Invalid username or password" flash --
    the response must NOT leak that the username exists.**
    """
    handle = _ensure_app()
    admin = _ensure_seeded_admin()
    response, cookies = _login_via_post(
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
        payload = _decode_session_cookie(
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
    **Property: POST /config/login with a username that does
    not exist returns the same 401 + same generic flash as a
    bad password -- timing channel aside, the surface text
    must not differ.**
    """
    handle = _ensure_app()
    response, _cookies = _login_via_post(
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
    handle = _ensure_app()
    cookies = _logged_in_cookies(wsgi_app=handle.wsgi_app)

    response = _drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/config",
        cookies=cookies,
    )
    # The dashboard handler may return a 200 directly OR redirect
    # via 302/303 to /config/dashboard depending on which alias
    # the route table fires. Either way we must NOT see a
    # redirect to /config/login.
    location = response.header("Location") or ""
    redirected_to_login = location.endswith("/config/login")
    testbase.assert_equal(redirected_to_login, False)

    # Follow any internal redirect to /config/dashboard.
    if response.status_code in (301, 302, 303, 307, 308):
        target = response.header("Location") or "/config/dashboard"
        # Strip leading scheme/host if present
        if target.startswith("http"):
            from urllib.parse import urlparse
            parsed = urlparse(target)
            target = parsed.path
        response = _drive_request(
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
    # The dashboard page should NOT contain the login form -- if
    # it does, the auth resolver decided we were anonymous.
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
    **Property: POST /config/logout clears the session cookie
    (or returns one without ``user_id``) and a follow-up GET
    /config 302s back to /config/login.**
    """
    handle = _ensure_app()
    cookies = _logged_in_cookies(wsgi_app=handle.wsgi_app)
    # Find the CSRF token to send with the logout POST.
    payload = _decode_session_cookie(
        cookie_value=cookies[cookie_session.COOKIE_NAME]
    )
    csrf_token = payload.get(csrf.SESSION_KEY, "")
    body = "csrf_token={}".format(csrf_token).encode("utf-8")

    logout_response = _drive_request(
        wsgi_app=handle.wsgi_app,
        method="POST",
        path="/config/logout",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        cookies=cookies,
    )
    # The logout handler redirects to the login page on success.
    is_redirect = logout_response.status_code in (302, 303)
    testbase.assert_equal(is_redirect, True)
    location = logout_response.header("Location") or ""
    redirected_to_login = location.endswith("/config/login")
    testbase.assert_equal(redirected_to_login, True)

    # Update the cookie jar with whatever the logout response set
    # (may be a cleared / empty cookie, may be unchanged).
    new_cookies = logout_response.collect_set_cookies()
    refreshed_jar = dict(cookies)
    for name, value in new_cookies.items():
        refreshed_jar[name] = value

    # Subsequent dashboard request: must redirect to login.
    next_response = _drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/config",
        cookies=refreshed_jar,
    )
    is_redirect_after_logout = next_response.status_code in (
        301, 302, 303, 307, 308
    )
    testbase.assert_equal(is_redirect_after_logout, True)
    testbase.assert_equal(
        (next_response.header("Location") or "").endswith(
            "/config/login"
        ),
        True,
    )
    return


# ===========================================================================
# CRUD round-trip: global variable
# ===========================================================================


def _extract_csrf_token_from_cookies(
        *, cookies: Dict[str, str]
    ) -> Optional[str]:
    cookie_value = cookies.get(cookie_session.COOKIE_NAME, None)
    if cookie_value is None:
        return None
    payload = _decode_session_cookie(cookie_value=cookie_value)
    if payload is None:
        return None
    rtnval = payload.get(csrf.SESSION_KEY, None)
    return rtnval


def test_crud_roundtrip_create_and_list_global_variable():
    """
    **Feature: consumer UI e2e tier-2 T15.6**
    **Property: A logged-in user can hit
    GET /config/variables/create, POST a new variable with the
    captured CSRF token, follow the redirect to
    /config/variables, and see the new variable's name in the
    list HTML. Exercises the full
    cookie-based-session + CSRF-validated-POST + jinja-list-
    rendering loop end-to-end.**
    """
    handle = _ensure_app()
    cookies = _logged_in_cookies(wsgi_app=handle.wsgi_app)
    csrf_token = _extract_csrf_token_from_cookies(cookies=cookies)
    testbase.assert_equal(
        csrf_token is not None and len(csrf_token) > 0, True
    )

    # GET the create form first to keep the session warm and to
    # mirror what a real browser does.
    create_form = _drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/config/variables/create",
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

    create_response = _drive_request(
        wsgi_app=handle.wsgi_app,
        method="POST",
        path="/config/variables/create",
        body=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        cookies=cookies,
    )
    is_redirect = create_response.status_code in (302, 303)
    testbase.assert_equal(is_redirect, True)
    target = create_response.header("Location") or ""
    landed_at_list = target.endswith("/config/variables")
    testbase.assert_equal(landed_at_list, True)

    # Now drive the list page and verify the new variable's name
    # appears in the HTML body.
    list_response = _drive_request(
        wsgi_app=handle.wsgi_app,
        method="GET",
        path="/config/variables",
        cookies=cookies,
    )
    testbase.assert_equal(list_response.status_code, 200)
    has_new_variable = var_name in list_response.text
    testbase.assert_equal(has_new_variable, True)
    return
