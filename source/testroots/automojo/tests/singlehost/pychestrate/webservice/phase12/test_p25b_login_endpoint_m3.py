"""
.. module:: test_p25b_login_endpoint_m3
    :synopsis: Tests for POST /api/v1/auth/login.

Boots a real :class:`PychestrateApplication` against a file-backed
SQLite engine, seeds an admin user via the same helpers
``scripts/bootstrapadmin.py`` uses, and exercises the new login
endpoint end-to-end.

Verifies:

* a valid (login_name, password) pair returns 200 with a Set-Cookie
  header that names ``pychestrate_session`` and includes the
  configured policy attributes (HttpOnly, Secure / SameSite when
  enabled, Max-Age);
* the cookie value resolves through
  :func:`session_service.resolve_session`;
* an invalid password returns 401;
* the login endpoint short-circuits the cookie and works against
  anonymous / unauthenticated requests (it cannot itself require
  auth, since the caller has none yet).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import tempfile

from datetime import datetime, timezone
from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.cookies import (
    SESSION_COOKIE_NAME,
)
from automojo.pychestrate.webservice.security.auth.local_flow import (
    reset_backoff_for_testing,
)
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    resolve_session,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


_LOGIN_NAME = "alice"
_LOGIN_PASSWORD = "AliceSecret!42"
_LOGIN_EMAIL = "alice@example.com"


def _build_app_with_seeded_admin() -> Tuple[PychestrateApplication, str, str]:
    """
        Boot a fresh app + seed an identity user with local
        credentials. Returns ``(app, db_path, user_id)``.
    """
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p25b-test-pepper"))
    # The local-flow backoff state is module-global; reset it so a
    # prior test's failed-login attempts don't lock the bucket.
    reset_backoff_for_testing()

    fd, db_path = tempfile.mkstemp(prefix="pych_p25b_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(db_path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )

    # Seed user + system-admin binding + local password using the
    # same helpers as scripts/bootstrapadmin.py.
    import importlib.util
    repo_root = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..", "..", "..", "..", "..", "..", "..", "..",
        ),
    )
    spec = importlib.util.spec_from_file_location(
        "scripts_bootstrapadmin",
        os.path.join(repo_root, "scripts", "bootstrapadmin.py"),
    )
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)

    db_session = factory()
    try:
        bootstrap._sync_role_catalog(db_session=db_session)
        user_id = bootstrap._ensure_user(
            db_session=db_session,
            login_name=_LOGIN_NAME,
            primary_email=_LOGIN_EMAIL,
            display_name="Alice",
            timezone_name="UTC",
        )
        bootstrap._ensure_admin_binding(
            db_session=db_session, user_id=user_id,
        )
        bootstrap._ensure_local_password(
            db_session=db_session,
            user_id=user_id,
            password=_LOGIN_PASSWORD,
        )
        db_session.commit()
    finally:
        db_session.close()

    return app, db_path, user_id


def test_login_with_valid_credentials_returns_set_cookie_and_session_resolves():
    """
    **Feature: P25b login endpoint (M3)**
    **Property: POST /api/v1/auth/login with a valid
    (login_name, password) pair returns 200 with a Set-Cookie header
    naming ``pychestrate_session``; the cookie value resolves through
    session_service.resolve_session to the seeded user.**
    """
    app, db_path, user_id = _build_app_with_seeded_admin()
    factory = app.dispatcher._dispatcher__router._routes if False else None  # placeholder for static analyzer
    try:
        request = Request(
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "login_name": _LOGIN_NAME,
                "password": _LOGIN_PASSWORD,
            }).encode("utf-8"),
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 200)

        # The response carries Set-Cookie with the canonical name.
        set_cookie_value = None
        for header_name, header_value in response.headers.items():
            if header_name.lower() == "set-cookie":
                set_cookie_value = header_value
                break
        testbase.assert_equal(set_cookie_value is not None, True)
        testbase.assert_equal(
            set_cookie_value.startswith(
                "{0}=".format(SESSION_COOKIE_NAME),
            ),
            True,
        )
        testbase.assert_equal("HttpOnly" in set_cookie_value, True)
        testbase.assert_equal("Max-Age=" in set_cookie_value, True)

        # The body carries a session_id and user_id.
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(body["user_id"], user_id)
        session_id = body["session_id"]
        testbase.assert_equal(len(session_id) > 0, True)

        # Build a fresh session via the app's session_factory and
        # confirm resolve_session sees the row.
        db_session = app.flow_runtime._session_factory()
        try:
            principal = resolve_session(
                db_session=db_session,
                session_id=session_id,
                now=datetime.now(timezone.utc),
            )
            testbase.assert_equal(principal.user_id, user_id)
        finally:
            db_session.close()
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_login_with_invalid_password_returns_401():
    """
    **Feature: P25b login endpoint (M3)**
    **Property: A wrong password returns 401 with the standard
    AuthenticationError detail and emits no Set-Cookie header.**
    """
    app, db_path, _user_id = _build_app_with_seeded_admin()
    try:
        request = Request(
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "login_name": _LOGIN_NAME,
                "password": "WrongPassword!",
            }).encode("utf-8"),
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 401)

        for header_name in response.headers.keys():
            testbase.assert_equal(header_name.lower() != "set-cookie", True)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_login_with_unknown_user_returns_401():
    """
    **Feature: P25b login endpoint (M3)**
    **Property: A login_name with no identity row returns 401.**
    """
    app, db_path, _user_id = _build_app_with_seeded_admin()
    try:
        request = Request(
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "login_name": "ghost",
                "password": "anything",
            }).encode("utf-8"),
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 401)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return


def test_login_with_missing_body_returns_400():
    """
    **Feature: P25b login endpoint (M3)**
    **Property: A login call with no body returns 400.**
    """
    app, db_path, _user_id = _build_app_with_seeded_admin()
    try:
        request = Request(
            method="POST",
            path="/api/v1/auth/login",
            headers={"Content-Type": "application/json"},
            body=b"",
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 400)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(db_path)
    return
