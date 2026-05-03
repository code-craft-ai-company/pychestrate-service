"""
.. module:: test_p11b_authentication_m2
    :synopsis: Tests for P11b — 1-authentication M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import List, Mapping

from automojo import testbase

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.security.auth import (
    register_builtin_extensions as auth_register,
)
from automojo.pychestrate.webservice.security.auth.events import AuthEventTopics
from automojo.pychestrate.webservice.security.auth.exceptions import (
    MfaChallengeExpiredError,
    MfaChallengeRejectedError,
    MfaChallengeUnknownError,
    MfaEnrollmentNotFoundError,
    MfaEnrollmentNotVerifiedError,
    MfaMethodUnknownError,
)
from automojo.pychestrate.webservice.security.auth.factories.totp_mfa import (
    TOTP_DIGITS,
    TOTP_PERIOD_SECONDS,
    TotpMfaMethod,
    _compute_totp,
)
from automojo.pychestrate.webservice.security.auth.mfa_service import (
    confirm_enrollment,
    enroll_method,
    initiate_challenge,
    list_enrollments_for_user,
    remove_enrollment,
    reset_for_testing as reset_mfa_for_testing,
    verify_challenge,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthMfaEnrollment,
    AuthProviderKind,
    AuthSession,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    RequestFingerprint,
    install_user_management_revocation_callback,
    open_session,
    revoke_sessions_for_user,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


ACTOR_UUID = "00000000-0000-4000-8000-000000500001"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    user_service.reset_for_testing()
    reset_mfa_for_testing()
    auth_register()
    return


def _make_user(*, session, login: str = "alice"):
    return user_service.create_user(
        db_session=session,
        login_name=login,
        primary_email="{}@x.com".format(login),
        display_name=login.upper(),
        timezone="UTC",
        provisioning_source="local",
        external_id=None,
        actor_user_id=ACTOR_UUID,
    )


def _open_session(*, db_session, user_id):
    rtnval = open_session(
        db_session=db_session,
        user_id=user_id,
        provider_kind=AuthProviderKind.LOCAL,
        provider_name="local",
        idle_timeout_seconds=1800,
        max_lifetime_seconds=3600,
        request_fingerprint=RequestFingerprint(
            ip_fingerprint="ip-x", user_agent_fingerprint="ua-x",
        ),
        access_token_payload=None,
        refresh_token_payload=None,
        mfa_method_name=None,
    )
    return rtnval


def _current_totp(*, secret_bytes: bytes) -> str:
    epoch = int(datetime.now(tz=timezone.utc).timestamp())
    step = epoch // TOTP_PERIOD_SECONDS
    rtnval = _compute_totp(secret_bytes=secret_bytes, step=step)
    return rtnval


# -------------------------------------
# Session revocation
# -------------------------------------

def test_revoke_sessions_for_user_drops_rows_and_emits():
    """
    **Feature: 1-authentication (M2)**
    **Property: revoke_sessions_for_user deletes every active
    AuthSession for a user and emits a single SESSIONS_REVOKED
    event carrying the count.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.SESSIONS_REVOKED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session)
    s_a = _open_session(db_session=session, user_id=str(user.user_id))
    s_b = _open_session(db_session=session, user_id=str(user.user_id))

    revoked = revoke_sessions_for_user(
        db_session=session, user_id=str(user.user_id),
    )
    testbase.assert_equal(revoked, 2)
    remaining = (
        session.query(AuthSession)
        .filter(AuthSession.user_id == user.user_id)
        .all()
    )
    testbase.assert_equal(len(remaining), 0)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["count"], 2)
    return


def test_revoke_sessions_for_user_no_op_returns_zero():
    """
    **Feature: 1-authentication (M2)**
    **Property: revoke_sessions_for_user with no active rows
    returns 0 and emits nothing.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.SESSIONS_REVOKED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session)
    revoked = revoke_sessions_for_user(
        db_session=session, user_id=str(user.user_id),
    )
    testbase.assert_equal(revoked, 0)
    testbase.assert_equal(len(received), 0)
    return


def test_install_user_management_revocation_wires_deactivate_path():
    """
    **Feature: 1-authentication (M2)**
    **Property: installing the user-management revocation
    callback drops the user's sessions when deactivate_user
    runs.**
    """
    _prepare_runtime()
    engine, session = build_in_memory_session()

    from sqlalchemy.orm import sessionmaker
    factory = sessionmaker(bind=engine)

    install_user_management_revocation_callback(session_factory=factory)

    user = _make_user(session=session, login="bob")
    _open_session(db_session=session, user_id=str(user.user_id))
    user_service.deactivate_user(
        db_session=session, user_id=str(user.user_id),
    )
    fresh = factory()
    try:
        remaining = (
            fresh.query(AuthSession)
            .filter(AuthSession.user_id == user.user_id)
            .all()
        )
        testbase.assert_equal(len(remaining), 0)
    finally:
        fresh.close()
    return


# -------------------------------------
# TOTP primitive
# -------------------------------------

def test_totp_provisioning_uri_carries_secret_and_metadata():
    """
    **Feature: 1-authentication (M2)**
    **Property: provisioning_uri encodes the base32 secret +
    digits/period under otpauth://totp.**
    """
    _prepare_runtime()
    secret = b"\x01" * 20
    uri = TotpMfaMethod.provisioning_uri(
        secret_bytes=secret, account_name="alice@example.com",
        issuer="Pychestrate",
    )
    testbase.assert_equal(uri.startswith("otpauth://totp/"), True)
    testbase.assert_equal("digits=" + str(TOTP_DIGITS) in uri, True)
    testbase.assert_equal(
        "period=" + str(TOTP_PERIOD_SECONDS) in uri, True,
    )
    return


def test_totp_compute_is_deterministic_per_step():
    """
    **Feature: 1-authentication (M2)**
    **Property: _compute_totp produces identical 6-digit codes
    for identical (secret, step) inputs.**
    """
    _prepare_runtime()
    secret = b"\x02" * 20
    a = _compute_totp(secret_bytes=secret, step=12345)
    b = _compute_totp(secret_bytes=secret, step=12345)
    testbase.assert_equal(a, b)
    testbase.assert_equal(len(a), TOTP_DIGITS)
    return


# -------------------------------------
# Enrollment + confirmation
# -------------------------------------

def test_enroll_method_emits_and_returns_provisioning_uri():
    """
    **Feature: 1-authentication (M2)**
    **Property: enroll_method('totp') returns a provisioning
    URI, persists an unverified row, and emits
    MFA_ENROLLMENT_CREATED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.MFA_ENROLLMENT_CREATED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session)
    bootstrap = enroll_method(
        db_session=session,
        user_id=str(user.user_id),
        method_name="totp",
        account_name="alice@example.com",
    )
    testbase.assert_equal(bootstrap.method_name, "totp")
    testbase.assert_equal(
        bootstrap.provisioning_uri.startswith("otpauth://totp/"), True,
    )
    testbase.assert_equal(len(received), 1)

    row = (
        session.query(AuthMfaEnrollment)
        .filter(AuthMfaEnrollment.user_id == user.user_id)
        .first()
    )
    testbase.assert_equal(row.verified_at, None)
    return


def test_enroll_method_unknown_method_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: enrolling an unregistered method raises
    MfaMethodUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    user = _make_user(session=session)
    raised = False
    try:
        enroll_method(
            db_session=session, user_id=str(user.user_id),
            method_name="webauthn",
            account_name="alice@example.com",
        )
    except MfaMethodUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_enroll_method_replaces_unverified_row():
    """
    **Feature: 1-authentication (M2)**
    **Property: re-enrolling before verifying drops the
    pending row and seats a fresh secret.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    user = _make_user(session=session)
    first = enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    second = enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    testbase.assert_equal(first.enrollment_id != second.enrollment_id, True)
    testbase.assert_equal(
        first.secret_payload != second.secret_payload, True,
    )
    rows = (
        session.query(AuthMfaEnrollment)
        .filter(AuthMfaEnrollment.user_id == user.user_id)
        .all()
    )
    testbase.assert_equal(len(rows), 1)
    return


def test_enroll_method_rejects_when_already_verified():
    """
    **Feature: 1-authentication (M2)**
    **Property: re-enrolling after a verified handshake
    raises SemanticError so callers must explicitly remove
    the existing enrollment first.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    user = _make_user(session=session)
    bootstrap = enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    code = _current_totp(secret_bytes=bootstrap.secret_payload)
    confirm_enrollment(
        db_session=session,
        enrollment_id=bootstrap.enrollment_id,
        response_fields={"code": code},
    )
    raised = False
    try:
        enroll_method(
            db_session=session, user_id=str(user.user_id),
            method_name="totp", account_name="alice@example.com",
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_confirm_enrollment_with_correct_code_stamps_verified_at():
    """
    **Feature: 1-authentication (M2)**
    **Property: confirm_enrollment with the current TOTP code
    stamps verified_at and emits MFA_ENROLLMENT_VERIFIED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.MFA_ENROLLMENT_VERIFIED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session)
    bootstrap = enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    code = _current_totp(secret_bytes=bootstrap.secret_payload)
    view = confirm_enrollment(
        db_session=session,
        enrollment_id=bootstrap.enrollment_id,
        response_fields={"code": code},
    )
    testbase.assert_equal(view.verified, True)
    testbase.assert_equal(len(received), 1)
    return


def test_confirm_enrollment_with_bad_code_raises_and_emits_rejection():
    """
    **Feature: 1-authentication (M2)**
    **Property: confirm_enrollment with a wrong code raises
    MfaChallengeRejectedError and emits MFA_CHALLENGE_REJECTED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.MFA_CHALLENGE_REJECTED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session)
    bootstrap = enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    raised = False
    try:
        confirm_enrollment(
            db_session=session,
            enrollment_id=bootstrap.enrollment_id,
            response_fields={"code": "000000"},
        )
    except MfaChallengeRejectedError:
        raised = True
    testbase.assert_equal(raised, True)
    testbase.assert_equal(len(received), 1)
    return


# -------------------------------------
# initiate / verify challenge
# -------------------------------------

def test_initiate_challenge_requires_verified_enrollment():
    """
    **Feature: 1-authentication (M2)**
    **Property: initiate_challenge against an unverified
    enrollment raises MfaEnrollmentNotVerifiedError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    user = _make_user(session=session)
    enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    raised = False
    try:
        initiate_challenge(
            db_session=session, user_id=str(user.user_id),
            method_name="totp",
        )
    except MfaEnrollmentNotVerifiedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_initiate_challenge_returns_active_challenge():
    """
    **Feature: 1-authentication (M2)**
    **Property: initiate_challenge against a verified
    enrollment returns a challenge bundle and emits
    MFA_CHALLENGE_ISSUED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.MFA_CHALLENGE_ISSUED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session)
    bootstrap = enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    code = _current_totp(secret_bytes=bootstrap.secret_payload)
    confirm_enrollment(
        db_session=session,
        enrollment_id=bootstrap.enrollment_id,
        response_fields={"code": code},
    )
    challenge = initiate_challenge(
        db_session=session, user_id=str(user.user_id),
        method_name="totp",
    )
    testbase.assert_equal(challenge.method_name, "totp")
    testbase.assert_equal(challenge.user_id, str(user.user_id))
    testbase.assert_equal(len(received), 1)
    return


def test_verify_challenge_accepts_current_code():
    """
    **Feature: 1-authentication (M2)**
    **Property: verify_challenge with the current code
    returns accepted=True and emits MFA_CHALLENGE_VERIFIED;
    the challenge is one-shot consumed.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.MFA_CHALLENGE_VERIFIED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session)
    bootstrap = enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    code = _current_totp(secret_bytes=bootstrap.secret_payload)
    confirm_enrollment(
        db_session=session,
        enrollment_id=bootstrap.enrollment_id,
        response_fields={"code": code},
    )
    challenge = initiate_challenge(
        db_session=session, user_id=str(user.user_id),
        method_name="totp",
    )
    code = _current_totp(secret_bytes=bootstrap.secret_payload)
    outcome = verify_challenge(
        db_session=session,
        challenge_id=challenge.challenge_id,
        response_fields={"code": code},
    )
    testbase.assert_equal(outcome.accepted, True)
    testbase.assert_equal(len(received), 1)
    # Re-using the same challenge id raises unknown.
    raised = False
    try:
        verify_challenge(
            db_session=session,
            challenge_id=challenge.challenge_id,
            response_fields={"code": code},
        )
    except MfaChallengeUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_verify_challenge_unknown_id_raises():
    """
    **Feature: 1-authentication (M2)**
    **Property: verify_challenge against an unknown challenge
    id raises MfaChallengeUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        verify_challenge(
            db_session=session,
            challenge_id="not-real",
            response_fields={"code": "000000"},
        )
    except MfaChallengeUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_verify_challenge_with_bad_code_raises_and_emits_rejection():
    """
    **Feature: 1-authentication (M2)**
    **Property: verify_challenge with a wrong code raises
    MfaChallengeRejectedError and emits MFA_CHALLENGE_REJECTED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.MFA_CHALLENGE_REJECTED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session)
    bootstrap = enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    code = _current_totp(secret_bytes=bootstrap.secret_payload)
    confirm_enrollment(
        db_session=session,
        enrollment_id=bootstrap.enrollment_id,
        response_fields={"code": code},
    )
    challenge = initiate_challenge(
        db_session=session, user_id=str(user.user_id),
        method_name="totp",
    )
    raised = False
    try:
        verify_challenge(
            db_session=session,
            challenge_id=challenge.challenge_id,
            response_fields={"code": "000001"},
        )
    except MfaChallengeRejectedError:
        raised = True
    testbase.assert_equal(raised, True)
    testbase.assert_equal(len(received), 1)
    return


def test_remove_enrollment_idempotent_and_emits():
    """
    **Feature: 1-authentication (M2)**
    **Property: remove_enrollment drops the row + emits on
    first call; second call is a no-op.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=AuthEventTopics.MFA_ENROLLMENT_REMOVED,
        subscriber=lambda e: received.append(e),
    )
    user = _make_user(session=session)
    enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    first = remove_enrollment(
        db_session=session, user_id=str(user.user_id),
        method_name="totp",
    )
    second = remove_enrollment(
        db_session=session, user_id=str(user.user_id),
        method_name="totp",
    )
    testbase.assert_equal(first, True)
    testbase.assert_equal(second, False)
    testbase.assert_equal(len(received), 1)
    return


def test_list_enrollments_for_user_returns_methods():
    """
    **Feature: 1-authentication (M2)**
    **Property: list_enrollments_for_user surfaces every
    method enrolled for the user with verified flags.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    user = _make_user(session=session)
    enroll_method(
        db_session=session, user_id=str(user.user_id),
        method_name="totp", account_name="alice@example.com",
    )
    enrollments = list_enrollments_for_user(
        db_session=session, user_id=str(user.user_id),
    )
    testbase.assert_equal(len(enrollments), 1)
    testbase.assert_equal(enrollments[0].method_name, "totp")
    testbase.assert_equal(enrollments[0].verified, False)
    return


def test_register_builtin_extensions_seeds_totp():
    """
    **Feature: 1-authentication (M2)**
    **Property: register_builtin_extensions registers
    TotpMfaMethod under the MFAMethodExtension resource base.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    auth_register()
    from automojo.pychestrate.webservice.extensions.registry import (
        list_resource_extensions,
    )
    from automojo.pychestrate.webservice.security.auth.factories.mfa_method import (
        MFAMethodExtension,
    )
    impls = list_resource_extensions(base_class=MFAMethodExtension)
    testbase.assert_equal(TotpMfaMethod in impls, True)
    return
