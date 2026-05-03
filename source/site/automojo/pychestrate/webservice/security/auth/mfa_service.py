"""
.. module:: security.auth.mfa_service
    :synopsis: M2 MFA enrollment + challenge + verify orchestration.

The service owns:

* :func:`enroll_method` — bootstrap a per-(user, method)
  enrollment row, generate the secret material via the
  method extension, and return the caller-visible
  enrollment payload (provisioning URI for TOTP, etc.).
* :func:`confirm_enrollment` — verify the enroll-time
  proof-of-knowledge code and stamp ``verified_at``.
* :func:`initiate_challenge` — issue a fresh challenge
  bundle and stash it in the in-process active-challenge
  store.
* :func:`verify_challenge` — consume a challenge by id,
  delegate to the method's
  :meth:`MFAMethodExtension.verify_response`, and emit a
  challenge-verified or challenge-rejected event.
* :func:`remove_enrollment` — drop the row + emit
  :data:`AuthEventTopics.MFA_ENROLLMENT_REMOVED`.
* :func:`list_enrollments_for_user` — read helper for the
  REST surface that shows a user's enrolled methods.

The active-challenge store is process-local and ephemeral
because challenges live no more than 5 minutes; the M3
hardening pass adds a Redis-backed store for multi-pod
deployments.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import threading

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Mapping, Optional, Type

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_resource_extensions,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.security.auth.events import AuthEventTopics
from automojo.pychestrate.webservice.security.auth.exceptions import (
    MfaChallengeExpiredError,
    MfaChallengeRejectedError,
    MfaChallengeUnknownError,
    MfaEnrollmentNotFoundError,
    MfaEnrollmentNotVerifiedError,
    MfaMethodUnknownError,
)
from automojo.pychestrate.webservice.security.auth.factories.mfa_method import (
    MFAMethodExtension,
    MfaChallenge,
    MfaEnrollmentRecord,
    MfaResponse,
    MfaVerifyOutcome,
)
from automojo.pychestrate.webservice.security.auth.factories.totp_mfa import (
    TotpMfaMethod,
)
from automojo.pychestrate.webservice.security.auth.models import (
    AuthMfaEnrollment,
)


CHALLENGE_TTL = timedelta(minutes=5)


@dataclass(frozen=True)
class EnrollmentBootstrap:
    """
        Caller-facing enrollment bootstrap payload.

        :param enrollment_id: New enrollment row id.
        :param method_name: Method that produced this row.
        :param secret_payload: Bytes the user installs in their
                               authenticator (TOTP shared
                               secret).
        :param provisioning_uri: ``otpauth://`` URI for QR
                                 rendering when the method
                                 supports it; ``None``
                                 otherwise.
        :param payload: Per-method metadata (digits, period).
    """
    enrollment_id: str
    method_name: str
    secret_payload: bytes
    provisioning_uri: Optional[str]
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class EnrollmentView:
    """
        Caller-facing view of a persisted enrollment row.
    """
    enrollment_id: str
    user_id: str
    method_name: str
    verified: bool
    last_used_at: Optional[datetime]


_LOCK = threading.RLock()
_ACTIVE_CHALLENGES: Dict[str, MfaChallenge] = {}


def reset_for_testing() -> None:
    """
        Drop the in-process active-challenge store. Tests use
        this to keep state from leaking across cases.
    """
    with _LOCK:
        _ACTIVE_CHALLENGES.clear()
    return


def enroll_method(
        *,
        db_session: DbSession,
        user_id: str,
        method_name: str,
        account_name: str,
        actor_user_id: Optional[str] = None
    ) -> EnrollmentBootstrap:
    """
        Create an enrollment row + generate the secret bytes.

        :raises: MfaMethodUnknownError when no method extension
                 with ``method_name`` is registered;
                 SemanticError when the user already has an
                 enrolled-and-verified row for this method.
    """
    method_cls = _resolve_method(method_name=method_name)

    existing = (
        db_session.query(AuthMfaEnrollment)
        .filter(AuthMfaEnrollment.user_id == user_id)
        .filter(AuthMfaEnrollment.method_name == method_name)
        .first()
    )
    if existing is not None and existing.verified_at is not None:
        err_lines = ["User already has a verified enrollment for this method."]
        err_lines.append("USER_ID: {}".format(user_id))
        err_lines.append("METHOD: {}".format(method_name))
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None

    if existing is not None:
        # Replace the prior unverified row so the bootstrap
        # gives the user a fresh code.
        db_session.delete(existing)
        db_session.flush()

    if method_name == TotpMfaMethod.method_name:
        secret_bytes = TotpMfaMethod.generate_secret_bytes()
    else:
        # Other reference methods can override this entry point
        # in M3; for M1 we ship only TOTP so empty bytes are
        # acceptable here.
        secret_bytes = b""

    row = AuthMfaEnrollment(
        enrollment_id=new_uuid(),
        user_id=user_id,
        method_name=method_name,
        secret_ref=_encode_secret_payload(secret_bytes=secret_bytes),
        verified_at=None,
        last_used_at=None,
    )
    db_session.add(row)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AuthEventTopics.MFA_ENROLLMENT_CREATED,
            payload={
                "user_id": user_id,
                "method_name": method_name,
                "enrollment_id": str(row.enrollment_id),
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    provisioning_uri: Optional[str] = None
    if method_name == TotpMfaMethod.method_name:
        provisioning_uri = TotpMfaMethod.provisioning_uri(
            secret_bytes=secret_bytes,
            account_name=account_name,
        )

    rtnval = EnrollmentBootstrap(
        enrollment_id=str(row.enrollment_id),
        method_name=method_name,
        secret_payload=secret_bytes,
        provisioning_uri=provisioning_uri,
        payload=method_cls.enroll_payload(),
    )
    return rtnval


def confirm_enrollment(
        *,
        db_session: DbSession,
        enrollment_id: str,
        response_fields: Mapping[str, Any]
    ) -> EnrollmentView:
    """
        Verify the proof-of-knowledge code submitted at
        enrollment time. Stamps ``verified_at`` on success
        and emits :data:`AuthEventTopics.MFA_ENROLLMENT_VERIFIED`.

        :raises: MfaEnrollmentNotFoundError on miss;
                 MfaChallengeRejectedError on bad code.
    """
    row = (
        db_session.query(AuthMfaEnrollment)
        .filter(AuthMfaEnrollment.enrollment_id == enrollment_id)
        .first()
    )
    if row is None:
        err_lines = ["MFA enrollment row not found."]
        err_lines.append("ENROLLMENT_ID: {}".format(enrollment_id))
        err_msg = os.linesep.join(err_lines)
        raise MfaEnrollmentNotFoundError(err_msg) from None
    method_cls = _resolve_method(method_name=row.method_name)
    enrollment_record = _row_to_enrollment_record(row=row)
    now = utc_now()
    challenge = method_cls.initiate_challenge(
        enrollment=enrollment_record,
        issued_at=now,
        expires_at=now + CHALLENGE_TTL,
        challenge_id=new_uuid(),
    )
    outcome = method_cls.verify_response(
        enrollment=enrollment_record,
        challenge=challenge,
        response=MfaResponse(fields=response_fields),
        now=now,
    )
    if outcome.accepted is False:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=AuthEventTopics.MFA_CHALLENGE_REJECTED,
                payload={
                    "user_id": str(row.user_id),
                    "method_name": row.method_name,
                    "phase": "enroll",
                    "reason": outcome.reason or "code_invalid",
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        err_lines = ["MFA enrollment proof-of-knowledge rejected."]
        err_lines.append("ENROLLMENT_ID: {}".format(enrollment_id))
        err_lines.append("REASON: {}".format(outcome.reason))
        err_msg = os.linesep.join(err_lines)
        raise MfaChallengeRejectedError(err_msg) from None

    row.verified_at = now
    row.last_used_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AuthEventTopics.MFA_ENROLLMENT_VERIFIED,
            payload={
                "user_id": str(row.user_id),
                "method_name": row.method_name,
                "enrollment_id": str(row.enrollment_id),
                "verified_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _row_to_view(row=row)
    return rtnval


def initiate_challenge(
        *,
        db_session: DbSession,
        user_id: str,
        method_name: str
    ) -> MfaChallenge:
    """
        Issue a challenge and store it in the in-process
        active-challenge store keyed by ``challenge_id``.

        :raises: MfaEnrollmentNotFoundError when the
                 (user, method) row is missing;
                 MfaEnrollmentNotVerifiedError when the
                 enrollment has not yet been confirmed.
    """
    row = _require_enrollment(
        db_session=db_session, user_id=user_id, method_name=method_name,
    )
    if row.verified_at is None:
        err_lines = ["MFA enrollment has not been verified."]
        err_lines.append("USER_ID: {}".format(user_id))
        err_lines.append("METHOD: {}".format(method_name))
        err_msg = os.linesep.join(err_lines)
        raise MfaEnrollmentNotVerifiedError(err_msg) from None
    method_cls = _resolve_method(method_name=method_name)
    enrollment_record = _row_to_enrollment_record(row=row)
    now = utc_now()
    challenge = method_cls.initiate_challenge(
        enrollment=enrollment_record,
        issued_at=now,
        expires_at=now + CHALLENGE_TTL,
        challenge_id=new_uuid(),
    )
    with _LOCK:
        _ACTIVE_CHALLENGES[challenge.challenge_id] = challenge
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AuthEventTopics.MFA_CHALLENGE_ISSUED,
            payload={
                "user_id": user_id,
                "method_name": method_name,
                "challenge_id": challenge.challenge_id,
                "issued_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return challenge


def verify_challenge(
        *,
        db_session: DbSession,
        challenge_id: str,
        response_fields: Mapping[str, Any]
    ) -> MfaVerifyOutcome:
    """
        Consume a challenge from the active-challenge store,
        delegate to the method's
        :meth:`MFAMethodExtension.verify_response`, and emit
        the matching audit event.

        :raises: MfaChallengeUnknownError, MfaChallengeExpiredError,
                 MfaChallengeRejectedError.
    """
    with _LOCK:
        challenge = _ACTIVE_CHALLENGES.pop(challenge_id, None)
    if challenge is None:
        err_lines = ["MFA challenge id not recognized."]
        err_lines.append("CHALLENGE_ID: {}".format(challenge_id))
        err_msg = os.linesep.join(err_lines)
        raise MfaChallengeUnknownError(err_msg) from None
    now = utc_now()
    expires = _aware(value=challenge.expires_at)
    if now > expires:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=AuthEventTopics.MFA_CHALLENGE_REJECTED,
                payload={
                    "user_id": challenge.user_id,
                    "method_name": challenge.method_name,
                    "phase": "verify",
                    "reason": "expired",
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        err_lines = ["MFA challenge has expired."]
        err_lines.append("CHALLENGE_ID: {}".format(challenge_id))
        err_msg = os.linesep.join(err_lines)
        raise MfaChallengeExpiredError(err_msg) from None

    row = _require_enrollment(
        db_session=db_session,
        user_id=challenge.user_id,
        method_name=challenge.method_name,
    )
    method_cls = _resolve_method(method_name=challenge.method_name)
    enrollment_record = _row_to_enrollment_record(row=row)
    outcome = method_cls.verify_response(
        enrollment=enrollment_record,
        challenge=challenge,
        response=MfaResponse(fields=response_fields),
        now=now,
    )
    if outcome.accepted is False:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=AuthEventTopics.MFA_CHALLENGE_REJECTED,
                payload={
                    "user_id": challenge.user_id,
                    "method_name": challenge.method_name,
                    "phase": "verify",
                    "reason": outcome.reason or "code_invalid",
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        err_lines = ["MFA challenge response rejected."]
        err_lines.append("CHALLENGE_ID: {}".format(challenge_id))
        err_lines.append("REASON: {}".format(outcome.reason))
        err_msg = os.linesep.join(err_lines)
        raise MfaChallengeRejectedError(err_msg) from None

    row.last_used_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AuthEventTopics.MFA_CHALLENGE_VERIFIED,
            payload={
                "user_id": challenge.user_id,
                "method_name": challenge.method_name,
                "challenge_id": challenge_id,
                "verified_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return outcome


def remove_enrollment(
        *,
        db_session: DbSession,
        user_id: str,
        method_name: str,
        actor_user_id: Optional[str] = None
    ) -> bool:
    """
        Drop the enrollment row. Idempotent — returns ``False``
        when no row was found. Emits
        :data:`AuthEventTopics.MFA_ENROLLMENT_REMOVED` only on
        the successful first transition.
    """
    row = (
        db_session.query(AuthMfaEnrollment)
        .filter(AuthMfaEnrollment.user_id == user_id)
        .filter(AuthMfaEnrollment.method_name == method_name)
        .first()
    )
    if row is None:
        return False
    enrollment_id = str(row.enrollment_id)
    db_session.delete(row)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=AuthEventTopics.MFA_ENROLLMENT_REMOVED,
            payload={
                "user_id": user_id,
                "method_name": method_name,
                "enrollment_id": enrollment_id,
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return True


def list_enrollments_for_user(
        *,
        db_session: DbSession,
        user_id: str
    ) -> List[EnrollmentView]:
    """
        Return every enrollment row a user owns.
    """
    rows = (
        db_session.query(AuthMfaEnrollment)
        .filter(AuthMfaEnrollment.user_id == user_id)
        .order_by(AuthMfaEnrollment.method_name.asc())
        .all()
    )
    rtnval = [_row_to_view(row=r) for r in rows]
    return rtnval


def _resolve_method(*, method_name: str) -> Type[MFAMethodExtension]:
    candidates = list_resource_extensions(base_class=MFAMethodExtension)
    for cls in candidates:
        if cls.method_name == method_name:
            return cls
    err_lines = ["No registered MFA method extension for the supplied name."]
    err_lines.append("METHOD: {!r}".format(method_name))
    err_msg = os.linesep.join(err_lines)
    raise MfaMethodUnknownError(err_msg) from None


def _require_enrollment(
        *,
        db_session: DbSession,
        user_id: str,
        method_name: str
    ) -> AuthMfaEnrollment:
    row = (
        db_session.query(AuthMfaEnrollment)
        .filter(AuthMfaEnrollment.user_id == user_id)
        .filter(AuthMfaEnrollment.method_name == method_name)
        .first()
    )
    if row is None:
        err_lines = ["MFA enrollment row not found."]
        err_lines.append("USER_ID: {}".format(user_id))
        err_lines.append("METHOD: {}".format(method_name))
        err_msg = os.linesep.join(err_lines)
        raise MfaEnrollmentNotFoundError(err_msg) from None
    return row


def _row_to_enrollment_record(
        *, row: AuthMfaEnrollment
    ) -> MfaEnrollmentRecord:
    rtnval = MfaEnrollmentRecord(
        enrollment_id=str(row.enrollment_id),
        user_id=str(row.user_id),
        method_name=row.method_name,
        secret_payload=_decode_secret_payload(secret_ref=row.secret_ref),
        verified_at=row.verified_at,
    )
    return rtnval


def _row_to_view(*, row: AuthMfaEnrollment) -> EnrollmentView:
    rtnval = EnrollmentView(
        enrollment_id=str(row.enrollment_id),
        user_id=str(row.user_id),
        method_name=row.method_name,
        verified=row.verified_at is not None,
        last_used_at=row.last_used_at,
    )
    return rtnval


def _encode_secret_payload(*, secret_bytes: bytes) -> str:
    """
        Encode raw secret bytes for the ``secret_ref`` text
        column. M2 stores them as base32 in-line; M3 hardening
        pivots the column into the secrets vault and stores
        only the lookup key.
    """
    import base64
    rtnval = base64.b32encode(secret_bytes).decode("ascii")
    return rtnval


def _decode_secret_payload(*, secret_ref: str) -> bytes:
    """
        Decode the ``secret_ref`` column back into raw bytes.
    """
    import base64
    if secret_ref is None or len(secret_ref) == 0:
        return b""
    padding = "=" * (-len(secret_ref) % 8)
    rtnval = base64.b32decode(secret_ref + padding)
    return rtnval


def _aware(*, value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
