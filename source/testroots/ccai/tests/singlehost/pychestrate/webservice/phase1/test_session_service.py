"""
.. module:: test_session_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 1-authentication session_service + cookie builder.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.identity.users.models import IdentityUser, UserStatus
from ccai.pychestrate.webservice.security.auth import session_service
from ccai.pychestrate.webservice.security.auth.cookies import (
    SESSION_COOKIE_NAME,
    build_session_cookie,
)
from ccai.pychestrate.webservice.security.auth.exceptions import (
    SessionExpiredError,
    SessionNotFoundError,
)
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import RequestFingerprint

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
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
    from ccai.pychestrate.webservice.messaging.event_bus import subscribe
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


# ---------------------------------------------------------------------------
# Account status (ADM-03: deactivation must end access)
# ---------------------------------------------------------------------------


def _insert_named_identity_user(session, *, login_name: str) -> str:
    user_id = new_uuid()
    user = IdentityUser(
        user_id=user_id,
        login_name=login_name,
        primary_email="{}@example.com".format(login_name),
        display_name=login_name.title(),
        status=UserStatus.ACTIVE,
        provisioning_source="local",
        external_id=None,
        timezone="UTC",
    )
    session.add(user)
    session.commit()
    return user_id


def _open_session_for(session, *, user_id: str):
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
    return opened


def _set_user_status(session, *, user_id: str, status: UserStatus) -> None:
    user = (
        session.query(IdentityUser)
        .filter(IdentityUser.user_id == user_id)
        .one()
    )
    user.status = status
    session.commit()
    return


def _open_session_ids(session, *, user_id: str):
    from ccai.pychestrate.webservice.security.auth.models import AuthSession
    rows = (
        session.query(AuthSession.session_id)
        .filter(AuthSession.user_id == user_id)
        .all()
    )
    rtnval = sorted(str(row[0]) for row in rows)
    return rtnval


def test_resolve_session_refuses_deactivated_account():
    """
    **Feature: 1-authentication (ADM-03)**
    **Property: once the account behind a session is deactivated,
    resolve_session raises SessionExpiredError for that session even
    though it has not reached its idle or lifetime limit.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_identity_user(session)
    opened = _open_session_for(session, user_id=user_id)
    session_id = str(opened.session_id)
    _set_user_status(session, user_id=user_id, status=UserStatus.DEACTIVATED)

    raised = False
    try:
        session_service.resolve_session(
            db_session=session,
            session_id=session_id,
            now=datetime.now(timezone.utc),
        )
    except SessionExpiredError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_resolve_session_refuses_pending_account():
    """
    **Feature: 1-authentication (ADM-03)**
    **Property: only ACTIVE accounts may use a session; a session
    whose account is PENDING is refused with SessionExpiredError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_identity_user(session)
    opened = _open_session_for(session, user_id=user_id)
    session_id = str(opened.session_id)
    _set_user_status(session, user_id=user_id, status=UserStatus.PENDING)

    raised = False
    try:
        session_service.resolve_session(
            db_session=session,
            session_id=session_id,
            now=datetime.now(timezone.utc),
        )
    except SessionExpiredError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_resolve_session_refuses_session_without_identity_row():
    """
    **Feature: 1-authentication (ADM-03)**
    **Property: a session whose identity row no longer exists is
    refused (fail closed) rather than resolved to a principal.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_identity_user(session)
    opened = _open_session_for(session, user_id=user_id)
    session_id = str(opened.session_id)
    session.query(IdentityUser).filter(IdentityUser.user_id == user_id).delete()
    session.commit()

    raised = False
    try:
        session_service.resolve_session(
            db_session=session,
            session_id=session_id,
            now=datetime.now(timezone.utc),
        )
    except SessionExpiredError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_close_sessions_for_user_closes_only_that_users_sessions():
    """
    **Feature: 1-authentication (ADM-03)**
    **Property: close_sessions_for_user deletes every session of the
    named user, returns how many it closed, and leaves other users'
    sessions open.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    target_id = _insert_named_identity_user(session, login_name="target")
    other_id = _insert_named_identity_user(session, login_name="other")
    _open_session_for(session, user_id=target_id)
    _open_session_for(session, user_id=target_id)
    other_session = _open_session_for(session, user_id=other_id)
    other_session_id = str(other_session.session_id)

    closed = session_service.close_sessions_for_user(
        db_session=session,
        user_id=target_id,
        reason="user_deactivated",
    )
    session.commit()

    testbase.assert_equal(closed, 2)
    testbase.assert_equal(_open_session_ids(session, user_id=target_id), [])
    testbase.assert_equal(
        _open_session_ids(session, user_id=other_id), [other_session_id]
    )
    return


def test_close_sessions_for_user_publishes_closed_event_with_reason():
    """
    **Feature: 1-authentication (ADM-03)**
    **Property: after the caller commits, one entity.session.closed
    event is published per closed session, carrying the reason.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_identity_user(session)
    _open_session_for(session, user_id=user_id)

    received = []
    from ccai.pychestrate.webservice.messaging.event_bus import subscribe
    subscribe(
        topic="entity.session.closed",
        subscriber=lambda evt: received.append(evt),
    )

    session_service.close_sessions_for_user(
        db_session=session,
        user_id=user_id,
        reason="user_deactivated",
    )
    session.commit()

    testbase.assert_equal(
        [evt.payload["reason"] for evt in received], ["user_deactivated"]
    )
    return
