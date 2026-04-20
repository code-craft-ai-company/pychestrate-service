"""
.. module:: test_session_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-authentication session_service + cookie builder.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus
from automojo.pychestrate.webservice.security.auth import session_service
from automojo.pychestrate.webservice.security.auth.cookies import (
    SESSION_COOKIE_NAME,
    build_session_cookie,
)
from automojo.pychestrate.webservice.security.auth.exceptions import (
    SessionExpiredError,
    SessionNotFoundError,
)
from automojo.pychestrate.webservice.security.auth.models import AuthProviderKind
from automojo.pychestrate.webservice.security.auth.session_service import RequestFingerprint

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def _insert_identity_user(session) -> str:
    user_id = new_uuid()
    user = IdentityUser(
        user_id=user_id,
        login_name="zed",
        primary_email="zed@example.com",
        display_name="Zed",
        status=UserStatus.ACTIVE,
        provisioning_source="local",
        external_id=None,
        timezone="UTC",
    )
    session.add(user)
    session.commit()
    return user_id


def test_build_session_cookie_defaults_http_only():
    """
    **Feature: 1-authentication**
    **Property: build_session_cookie always sets HttpOnly and reflects the
    supplied policy values.**
    """
    spec = build_session_cookie(
        session_id="abc",
        max_age_seconds=1800,
        domain="pychestrate.local",
        same_site="Lax",
        secure=True,
        path="/",
    )
    testbase.assert_equal(spec.name, SESSION_COOKIE_NAME)
    testbase.assert_equal(spec.value, "abc")
    testbase.assert_equal(spec.http_only, True)
    testbase.assert_equal(spec.secure, True)
    testbase.assert_equal(spec.same_site, "Lax")
    testbase.assert_equal(spec.domain, "pychestrate.local")
    testbase.assert_equal(spec.path, "/")
    testbase.assert_equal(spec.max_age_seconds, 1800)
    return


def test_open_session_and_resolve_round_trip():
    """
    **Feature: 1-authentication**
    **Property: open_session persists a row; resolve_session returns a
    principal bound to the same user_id.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_identity_user(session)

    fingerprint = RequestFingerprint(
        ip_fingerprint="ip-hash",
        user_agent_fingerprint="ua-hash",
    )
    opened = session_service.open_session(
        db_session=session,
        user_id=user_id,
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
        mfa_method_name=None,
        access_token_payload=None,
        refresh_token_payload=None,
        request_fingerprint=fingerprint,
        idle_timeout_seconds=1800,
        max_lifetime_seconds=3600,
    )

    principal = session_service.resolve_session(
        db_session=session,
        session_id=opened.session_id,
        now=datetime.now(timezone.utc),
    )

    testbase.assert_equal(principal.user_id, user_id)
    testbase.assert_equal(principal.provider_kind, AuthProviderKind.LOCAL)
    testbase.assert_equal(principal.provider_name, "local")
    return


def test_resolve_unknown_session_raises_not_found():
    """
    **Feature: 1-authentication**
    **Property: resolve_session on an unknown session id raises
    SessionNotFoundError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        session_service.resolve_session(
            db_session=session,
            session_id="00000000-0000-0000-0000-000000000000",
            now=datetime.now(timezone.utc),
        )
    except SessionNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_resolve_expired_session_raises_expired():
    """
    **Feature: 1-authentication**
    **Property: resolve_session at a time past expires_at raises
    SessionExpiredError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_identity_user(session)
    opened = session_service.open_session(
        db_session=session,
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
        max_lifetime_seconds=60,
    )

    future = datetime.now(timezone.utc) + timedelta(hours=2)
    raised = False
    try:
        session_service.resolve_session(
            db_session=session,
            session_id=opened.session_id,
            now=future,
        )
    except SessionExpiredError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_close_session_publishes_event():
    """
    **Feature: 1-authentication**
    **Property: close_session publishes entity.session.closed.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_identity_user(session)
    opened = session_service.open_session(
        db_session=session,
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

    received = []
    from automojo.pychestrate.webservice.messaging.event_bus import subscribe
    subscribe(
        topic="entity.session.closed",
        subscriber=lambda evt: received.append(evt),
    )

    # Capture the session id before the row is deleted so later assertions
    # don't trigger an ORM refresh of a missing row.
    opened_session_id = str(opened.session_id)

    session_service.close_session(
        db_session=session,
        session_id=opened_session_id,
    )

    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["session_id"], opened_session_id)
    return
