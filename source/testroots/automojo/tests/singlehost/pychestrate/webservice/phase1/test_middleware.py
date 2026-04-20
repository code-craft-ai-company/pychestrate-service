"""
.. module:: test_middleware
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the Phase-1 request-scoped middleware.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone

from flask import Flask, g, jsonify
from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus
from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from automojo.pychestrate.webservice.middleware import (
    PHASE1_URL_PREFIXES,
    install_phase1_middleware,
)
from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from automojo.pychestrate.webservice.security.auth import session_service
from automojo.pychestrate.webservice.security.auth.cookies import SESSION_COOKIE_NAME
from automojo.pychestrate.webservice.security.auth.models import AuthProviderKind
from automojo.pychestrate.webservice.security.auth.session_service import RequestFingerprint

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
    session_for,
)


def _build_app_with_middleware(*, engine) -> Flask:
    """
        Build a minimal Flask app wired to the Phase-1 middleware and an
        in-memory SQLite engine.

        :param engine: SQLAlchemy engine bound to the Phase-1 metadata.

        :returns: A configured Flask app with two test routes.
    """
    session_factory = sessionmaker(bind=engine)
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = session_factory

    app = Flask("phase1-test")
    install_phase1_middleware(app=app)

    @app.route("/1/identity/users/probe", methods=["GET"])
    def _probe_identity():
        has_session = getattr(g, "db_session", None) is not None
        actor = getattr(g, "actor_user_id", None)
        rtnval = jsonify({
            "has_session": has_session,
            "actor_user_id": actor,
        })
        return rtnval

    @app.route("/public/probe", methods=["GET"])
    def _probe_public():
        has_session = getattr(g, "db_session", None) is not None
        rtnval = jsonify({"has_session": has_session})
        return rtnval

    @app.route("/1/audit/raises", methods=["GET"])
    def _probe_raises():
        raise RuntimeError("intentional test failure")

    return app


def test_install_is_idempotent():
    """
    **Feature: 1-phase1-middleware**
    **Property: install_phase1_middleware registers hooks once per app.**
    """
    reset_phase1_runtime()
    engine, _ = build_in_memory_session()
    session_factory = sessionmaker(bind=engine)
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = session_factory

    app = Flask("phase1-idempotency")
    install_phase1_middleware(app=app)
    install_phase1_middleware(app=app)

    testbase.assert_equal(getattr(app, "_pychestrate_phase1_middleware_installed"), True)
    return


def test_phase1_request_attaches_db_session():
    """
    **Feature: 1-phase1-middleware**
    **Property: A request on a Phase-1 prefix gets g.db_session attached.**
    """
    reset_phase1_runtime()
    engine, _ = build_in_memory_session()
    app = _build_app_with_middleware(engine=engine)

    client = app.test_client()
    response = client.get("/1/identity/users/probe")

    testbase.assert_equal(response.status_code, 200)
    body = response.get_json()
    testbase.assert_equal(body["has_session"], True)
    testbase.assert_equal(body["actor_user_id"], None)
    return


def test_public_request_does_not_attach_session():
    """
    **Feature: 1-phase1-middleware**
    **Property: A request outside Phase-1 prefixes has no g.db_session.**
    """
    reset_phase1_runtime()
    engine, _ = build_in_memory_session()
    app = _build_app_with_middleware(engine=engine)

    client = app.test_client()
    response = client.get("/public/probe")

    testbase.assert_equal(response.status_code, 200)
    body = response.get_json()
    testbase.assert_equal(body["has_session"], False)
    return


def test_resolves_principal_from_valid_cookie():
    """
    **Feature: 1-phase1-middleware + 1-authentication**
    **Property: A valid session cookie resolves to g.actor_user_id.**
    """
    reset_phase1_runtime()
    engine, bootstrap_session = build_in_memory_session()

    user_id = new_uuid()
    bootstrap_session.add(IdentityUser(
        user_id=user_id,
        login_name="principal-user",
        primary_email="principal@example.com",
        display_name="Principal",
        status=UserStatus.ACTIVE,
        provisioning_source="local",
        external_id=None,
        timezone="UTC",
    ))
    bootstrap_session.commit()

    opened = session_service.open_session(
        db_session=bootstrap_session,
        user_id=user_id,
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
        mfa_method_name=None,
        access_token_payload=None,
        refresh_token_payload=None,
        request_fingerprint=RequestFingerprint(
            ip_fingerprint="ip", user_agent_fingerprint="ua",
        ),
        idle_timeout_seconds=1800,
        max_lifetime_seconds=3600,
    )
    session_id = str(opened.session_id)
    bootstrap_session.close()

    app = _build_app_with_middleware(engine=engine)
    client = app.test_client()
    client.set_cookie(SESSION_COOKIE_NAME, session_id, domain="localhost")

    response = client.get("/1/identity/users/probe")

    testbase.assert_equal(response.status_code, 200)
    body = response.get_json()
    testbase.assert_equal(body["has_session"], True)
    testbase.assert_equal(body["actor_user_id"], user_id)
    return


def test_unknown_cookie_leaves_actor_none():
    """
    **Feature: 1-phase1-middleware**
    **Property: An unknown session cookie leaves actor_user_id as None
    but the session is still attached.**
    """
    reset_phase1_runtime()
    engine, _ = build_in_memory_session()
    app = _build_app_with_middleware(engine=engine)

    client = app.test_client()
    client.set_cookie(
        SESSION_COOKIE_NAME,
        "00000000-0000-0000-0000-000000000000",
        domain="localhost",
    )

    response = client.get("/1/identity/users/probe")

    testbase.assert_equal(response.status_code, 200)
    body = response.get_json()
    testbase.assert_equal(body["has_session"], True)
    testbase.assert_equal(body["actor_user_id"], None)
    return


def test_teardown_rolls_back_on_exception():
    """
    **Feature: 1-phase1-middleware**
    **Property: An exception inside the request triggers session rollback
    so transient ORM changes never persist.**
    """
    reset_phase1_runtime()
    engine, _ = build_in_memory_session()
    app = _build_app_with_middleware(engine=engine)

    sessions_opened = []
    sessions_rolled = []
    sessions_closed = []

    captured_factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY

    def _tracking_factory():
        session = captured_factory()
        sessions_opened.append(session)
        original_rollback = session.rollback
        original_close = session.close

        def _tracked_rollback():
            sessions_rolled.append(session)
            return original_rollback()

        def _tracked_close():
            sessions_closed.append(session)
            return original_close()

        session.rollback = _tracked_rollback
        session.close = _tracked_close
        return session

    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = _tracking_factory
    try:
        client = app.test_client()
        response = client.get("/1/audit/raises")

        testbase.assert_equal(response.status_code, 500)
        testbase.assert_equal(len(sessions_opened), 1)
        testbase.assert_equal(len(sessions_rolled), 1)
        testbase.assert_equal(len(sessions_closed), 1)
    finally:
        SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = captured_factory
    return


def test_phase1_url_prefixes_cover_all_controllers():
    """
    **Feature: 1-phase1-middleware**
    **Property: The prefix list covers the paths every spec-shaped
    controller publishes under the v1 API.**
    """
    expected = [
        "/1/identity/",
        "/1/auth/",
        "/1/rbac/",
        "/1/secrets",
        "/1/audit",
        "/1/flags",
    ]
    for prefix in expected:
        testbase.assert_equal(prefix in PHASE1_URL_PREFIXES, True)
    return
