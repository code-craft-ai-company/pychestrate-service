"""
.. module:: test_session_idle_timeout
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Idle-timeout enforcement and last_seen_at refresh tests for
               session_service.resolve_session.

.. moduleauthor:: Code Craft AI LLC

Closes the gap identified in the REST-auth-hardening audit (hole #6).

:func:`resolve_session` previously never checked ``idle_timeout_seconds``
or updated ``last_seen_at``. It now:

1. Raises :class:`SessionExpiredError` when
   ``last_seen_at + idle_timeout_seconds <= now``.
2. Updates ``last_seen_at`` to ``now`` on a successful resolution so that
   sustained activity refreshes the idle window.
3. Continues to honour the absolute ``expires_at`` check independently.

Tests:

* Session past its idle window raises SessionExpiredError.
* Session within its idle window resolves successfully.
* last_seen_at is updated to ``now`` on successful resolution.
* Absolute expiry still fires even when the session would be within
  its idle window.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.identity.users.models import (
    IdentityUser,
    UserStatus,
)
from ccai.pychestrate.webservice.security.auth import session_service
from ccai.pychestrate.webservice.security.auth.exceptions import (
    SessionExpiredError,
)
from ccai.pychestrate.webservice.security.auth.models import AuthProviderKind
from ccai.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_user(*, db_session: object) -> str:
    """
        Insert a minimal IdentityUser row and return its user_id string.

        :param db_session: Active SQLAlchemy session.

        :returns: user_id string.
    """
    user_id = new_uuid()
    user = IdentityUser(
        user_id=user_id,
        login_name="idle-test-user",
        primary_email="idle@example.com",
        display_name="Idle Test User",
        status=UserStatus.ACTIVE,
        provisioning_source="local",
        external_id=None,
        timezone="UTC",
    )
    db_session.add(user)
    db_session.commit()
    rtnval = user_id
    return rtnval


def _open(
        *,
        db_session: object,
        user_id: str,
        idle_timeout_seconds: int = 1800,
        max_lifetime_seconds: int = 86400
    ) -> object:
    """
        Open a session and return the persisted :class:`AuthSession`.

        :param db_session: Active SQLAlchemy session.
        :param user_id: User to open the session for.
        :param idle_timeout_seconds: Idle timeout for the session.
        :param max_lifetime_seconds: Absolute ceiling for the session.

        :returns: The new :class:`AuthSession` ORM row.
    """
    fingerprint = RequestFingerprint(
        ip_fingerprint="ip-hash",
        user_agent_fingerprint="ua-hash",
    )
    rtnval = session_service.open_session(
        db_session=db_session,
        user_id=user_id,
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
        mfa_method_name=None,
        access_token_payload=None,
        refresh_token_payload=None,
        request_fingerprint=fingerprint,
        idle_timeout_seconds=idle_timeout_seconds,
        max_lifetime_seconds=max_lifetime_seconds,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_resolve_raises_expired_when_idle_window_elapsed():
    """
    **Feature: rest-auth-hardening hole #6**
    **Property: resolve_session raises SessionExpiredError when
    last_seen_at + idle_timeout_seconds <= now. A session whose
    user has been idle beyond the configured window must be treated
    as expired.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_user(db_session=session)
    opened = _open(
        db_session=session,
        user_id=user_id,
        idle_timeout_seconds=300,
        max_lifetime_seconds=86400,
    )

    # Advance time past the idle window.
    future = datetime.now(timezone.utc) + timedelta(seconds=400)

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


def test_resolve_succeeds_when_within_idle_window():
    """
    **Feature: rest-auth-hardening hole #6**
    **Property: resolve_session succeeds (returns AuthPrincipal) when
    ``now`` is before ``last_seen_at + idle_timeout_seconds``.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_user(db_session=session)
    opened = _open(
        db_session=session,
        user_id=user_id,
        idle_timeout_seconds=1800,
        max_lifetime_seconds=86400,
    )

    # Advance just 60 s — well inside the 1800 s idle window.
    slightly_later = datetime.now(timezone.utc) + timedelta(seconds=60)

    principal = session_service.resolve_session(
        db_session=session,
        session_id=opened.session_id,
        now=slightly_later,
    )

    testbase.assert_equal(principal.user_id, user_id)
    return


def test_resolve_updates_last_seen_at_on_success():
    """
    **Feature: rest-auth-hardening hole #6**
    **Property: A successful resolve_session call updates
    ``last_seen_at`` to ``now`` so the next request extends the
    idle window from the most-recent activity, not from session
    open.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_user(db_session=session)
    opened = _open(
        db_session=session,
        user_id=user_id,
        idle_timeout_seconds=1800,
        max_lifetime_seconds=86400,
    )

    session_id = opened.session_id
    resolve_time = datetime.now(timezone.utc) + timedelta(seconds=60)

    session_service.resolve_session(
        db_session=session,
        session_id=session_id,
        now=resolve_time,
    )

    # Reload the row and compare last_seen_at.
    from ccai.pychestrate.webservice.security.auth.models import AuthSession
    reloaded = (
        session.query(AuthSession)
        .filter(AuthSession.session_id == session_id)
        .first()
    )
    last_seen = reloaded.last_seen_at
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)

    # Allow up to 2-second skew for clock granularity in test execution.
    delta = abs((last_seen - resolve_time).total_seconds())
    testbase.assert_equal(delta < 2.0, True)
    return


def test_idle_refresh_extends_window_for_next_call():
    """
    **Feature: rest-auth-hardening hole #6**
    **Property: After resolve_session updates last_seen_at, a
    subsequent call at ``first_resolve + idle_timeout - 1`` succeeds
    (the window has been refreshed), whereas a call at
    ``open_time + idle_timeout`` would have failed without the
    refresh.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_user(db_session=session)
    opened = _open(
        db_session=session,
        user_id=user_id,
        idle_timeout_seconds=300,
        max_lifetime_seconds=86400,
    )

    session_id = opened.session_id

    # First resolve at t+200 s (within window).  last_seen_at becomes t+200.
    first_resolve = datetime.now(timezone.utc) + timedelta(seconds=200)
    session_service.resolve_session(
        db_session=session,
        session_id=session_id,
        now=first_resolve,
    )

    # Second resolve at t+490 s.
    # Without the refresh: last_seen_at is still t+0, window closed at t+300.
    # With the refresh: last_seen_at is t+200, window closes at t+500.
    # t+490 < t+500 → should succeed.
    second_resolve = datetime.now(timezone.utc) + timedelta(seconds=490)

    raised = False
    try:
        principal = session_service.resolve_session(
            db_session=session,
            session_id=session_id,
            now=second_resolve,
        )
        testbase.assert_equal(principal.user_id, user_id)
    except SessionExpiredError:
        raised = True

    testbase.assert_equal(raised, False)
    return


def test_absolute_expiry_fires_even_within_idle_window():
    """
    **Feature: rest-auth-hardening hole #6**
    **Property: The absolute ``expires_at`` check is still
    enforced independently of the idle window. A session resolved
    well within its idle window is still rejected when
    ``now >= expires_at``.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    user_id = _insert_user(db_session=session)
    opened = _open(
        db_session=session,
        user_id=user_id,
        idle_timeout_seconds=86400,   # very long idle window
        max_lifetime_seconds=60,      # short absolute ceiling
    )

    # t+120 is past the 60 s absolute ceiling even though it is within the
    # (unreachable) 86400 s idle window.
    future = datetime.now(timezone.utc) + timedelta(seconds=120)

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
