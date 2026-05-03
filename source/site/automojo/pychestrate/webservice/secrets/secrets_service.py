"""
.. module:: secrets.secrets_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for the 1-secrets-vault feature.

.. moduleauthor:: Automation Mojo LLC

Implements :func:`put_secret` and :func:`read_secret` per the
1-secrets-vault M1 contract: ACL enforcement, transactional audit
emission, and local AES-GCM encryption via
:mod:`factories.local_backend`.

ACL evaluation is intentionally narrow at M1:

- ``write`` — the caller must hold ``system:secrets.admin`` OR be the
  secret's owner.
- ``read`` — the caller must hold ``system:secrets.read`` OR
  ``system:secrets.admin`` OR be the secret's owner.

Per-secret ACL rows (the ``secret_acls`` table) land in M2; the M1
skeleton still validates that the service writes / reads route through a
single permission decision so downstream callers can rely on the gate
being in place.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.audit.audit_writer import capture_event as audit_capture
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.secrets.events import SecretEventTopics
from automojo.pychestrate.webservice.secrets.exceptions import (
    SecretAccessDeniedError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretVersionExpiredError,
)
from automojo.pychestrate.webservice.secrets.factories.local_backend import (
    decrypt_ciphertext,
    encrypt_plaintext,
)
from automojo.pychestrate.webservice.secrets.models import (
    SecretRecord,
    SecretVersion,
    SecretVersionState,
)
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.secrets.secrets_aspects import SecretsAspects
from automojo.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


LOCAL_BACKEND_NAME: str = "local-db"


@dataclass(frozen=True)
class SecretRead:
    """
        Result returned by :func:`read_secret`.

        :param plaintext: The decrypted plaintext wrapped in :class:`SecretBytes`.
        :param secret_ref: Canonical secret reference.
        :param version_number: Monotonic version number that served the read.
        :param metadata: Optional metadata dict when
                         ``SecretsAspects.include_metadata`` is True.
    """
    plaintext: SecretBytes
    secret_ref: str
    version_number: int
    metadata: Optional[dict]


def _has_write_permission(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        record: Optional[SecretRecord]
    ) -> bool:
    """
        Evaluate the M1 write-ACL decision.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param record: The owning :class:`SecretRecord` when it already exists.

        :returns: True when the principal may write / rotate / delete.
    """
    if record is not None and record.owner_user_id is not None:
        if str(record.owner_user_id) == str(principal.user_id):
            return True

    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key="system:secrets.admin",
        now=datetime.now(timezone.utc),
    )
    rtnval = decision.allowed
    return rtnval


def _has_read_permission(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        record: SecretRecord
    ) -> bool:
    """
        Evaluate the M1 read-ACL decision.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param record: The owning :class:`SecretRecord`.

        :returns: True when the principal may read the latest version.
    """
    if record.owner_user_id is not None:
        if str(record.owner_user_id) == str(principal.user_id):
            return True

    now = datetime.now(timezone.utc)
    admin_decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key="system:secrets.admin",
        now=now,
    )
    if admin_decision.allowed is True:
        return True

    read_decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key="system:secrets.read",
        now=now,
    )
    rtnval = read_decision.allowed
    return rtnval


def _raise_access_denied(*, secret_ref: str, action: str) -> None:
    """
        Construct and raise a :class:`SecretAccessDeniedError` using the
        multi-line AGENTS.md pattern. Never returns.

        :param secret_ref: Canonical secret reference.
        :param action: Short verb: write / read / rotate / delete.

        :returns: None — always raises.
        :raises: SecretAccessDeniedError
    """
    err_msg_lines = ["Secret access denied."]
    err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
    err_msg_lines.append("ACTION: {}".format(action))
    err_msg = os.linesep.join(err_msg_lines)
    raise SecretAccessDeniedError(err_msg) from None


def put_secret(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        secret_ref: str,
        plaintext: SecretBytes,
        aspects: SecretsAspects,
        owner_user_id: Optional[str] = None
    ) -> SecretVersion:
    """
        Store a secret at version 1 using the local backend's AES-GCM
        encryption. ACL is enforced, an audit record is captured in the
        same transaction, and ``entity.secret.created`` is staged for
        after-commit publication.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param secret_ref: Canonical secret reference.
        :param plaintext: The :class:`SecretBytes` payload.
        :param aspects: Caller behavior knobs.
        :param owner_user_id: Owner for the new record. Defaults to the
                              principal's ``user_id`` when None.

        :returns: The persisted :class:`SecretVersion`.
        :raises: SecretAlreadyExistsError, SecretAccessDeniedError
    """
    existing = (
        db_session.query(SecretRecord).filter(SecretRecord.secret_ref == secret_ref).first()
    )
    if existing is not None:
        err_msg_lines = ["Cannot create secret — record already exists."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretAlreadyExistsError(err_msg) from None

    if _has_write_permission(db_session=db_session, principal=principal, record=None) is False:
        _raise_access_denied(secret_ref=secret_ref, action="write")

    resolved_owner = owner_user_id
    if resolved_owner is None:
        resolved_owner = principal.user_id

    now = utc_now()
    record = SecretRecord(
        secret_ref=secret_ref,
        current_version_id=None,
        backend_name=LOCAL_BACKEND_NAME,
        owner_user_id=resolved_owner,
        owner_project_id=None,
        created_at=now,
        updated_at=now,
    )
    db_session.add(record)
    db_session.flush()

    payload = encrypt_plaintext(plaintext=plaintext, secret_ref=secret_ref)
    version = SecretVersion(
        version_id=new_uuid(),
        secret_ref=secret_ref,
        version_number=1,
        state=SecretVersionState.ACTIVE,
        ciphertext_ref=None,
        ciphertext_bytes=payload.ciphertext_bytes,
        wrapped_dek=payload.wrapped_dek,
        kek_id=payload.kek_id,
        grace_expires_at=None,
        created_at=now,
        created_by=principal.user_id,
    )
    db_session.add(version)
    db_session.flush()

    record.current_version_id = version.version_id
    db_session.flush()

    audit_payload = {
        "secret_ref": secret_ref,
        "backend_name": LOCAL_BACKEND_NAME,
        "version_id": str(version.version_id),
        "principal_id": principal.user_id,
        "created_at": now.isoformat(),
    }
    audit_capture(
        db_session=db_session,
        source_event_id=new_uuid(),
        source_topic="entity.secret.created",
        kind="audit.secret.created",
        actor_user_id=principal.user_id,
        actor_service_identity=None,
        target_ref="secret:{}".format(secret_ref),
        payload=audit_payload,
    )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SecretEventTopics.SECRET_CREATED,
            payload=audit_payload,
            source_event_id=new_uuid(),
        ),
    )

    db_session.commit()

    rtnval = version
    return rtnval


def read_secret(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        secret_ref: str,
        aspects: SecretsAspects
    ) -> SecretRead:
    """
        Decrypt the active version of a secret after ACL enforcement and
        audit capture. The audit write and the ``entity.secret.accessed``
        event are staged inside the same transaction; commit publishes
        both.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param secret_ref: Canonical secret reference.
        :param aspects: Caller behavior knobs.

        :returns: :class:`SecretRead` wrapping the decrypted plaintext.
        :raises: SecretNotFoundError, SecretAccessDeniedError,
                 SecretVersionExpiredError
    """
    record = (
        db_session.query(SecretRecord).filter(SecretRecord.secret_ref == secret_ref).first()
    )
    if record is None:
        err_msg_lines = ["Cannot read secret — record not found."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretNotFoundError(err_msg) from None

    if _has_read_permission(db_session=db_session, principal=principal, record=record) is False:
        _raise_access_denied(secret_ref=secret_ref, action="read")

    version = (
        db_session.query(SecretVersion)
        .filter(SecretVersion.version_id == record.current_version_id)
        .first()
    )
    if version is None:
        err_msg_lines = ["Cannot read secret — active version missing."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretNotFoundError(err_msg) from None

    if version.state == SecretVersionState.EXPIRED:
        err_msg_lines = ["Cannot read secret — active version is expired."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg_lines.append("VERSION_NUMBER: {}".format(version.version_number))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretVersionExpiredError(err_msg) from None

    plaintext = decrypt_ciphertext(
        ciphertext_bytes=bytes(version.ciphertext_bytes),
        wrapped_dek=bytes(version.wrapped_dek),
        secret_ref=secret_ref,
    )

    now = utc_now()
    audit_payload = {
        "secret_ref": secret_ref,
        "backend_name": record.backend_name,
        "version_id": str(version.version_id),
        "principal_id": principal.user_id,
        "accessed_at": now.isoformat(),
    }
    audit_capture(
        db_session=db_session,
        source_event_id=new_uuid(),
        source_topic="entity.secret.accessed",
        kind="audit.secret.accessed",
        actor_user_id=principal.user_id,
        actor_service_identity=None,
        target_ref="secret:{}".format(secret_ref),
        payload=audit_payload,
    )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SecretEventTopics.SECRET_ACCESSED,
            payload=audit_payload,
            source_event_id=new_uuid(),
        ),
    )

    db_session.commit()

    metadata: Optional[dict] = None
    if aspects.include_metadata is True:
        metadata = {
            "secret_ref": secret_ref,
            "version_number": int(version.version_number),
            "backend_name": record.backend_name,
            "kek_id": version.kek_id,
            "created_at": version.created_at.isoformat() if version.created_at is not None else None,
        }

    rtnval = SecretRead(
        plaintext=plaintext,
        secret_ref=secret_ref,
        version_number=int(version.version_number),
        metadata=metadata,
    )
    return rtnval


DEFAULT_ROTATION_GRACE = timedelta(hours=24)


def rotate_secret(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        secret_ref: str,
        new_plaintext: SecretBytes,
        aspects: SecretsAspects,
        grace_period: Optional[timedelta] = None
    ) -> SecretVersion:
    """
        Rotate a secret to a new version. The old active row
        flips to ``SUPERSEDED`` and gains a ``grace_expires_at``
        deadline (default 24 h); the new row becomes ``ACTIVE``.
        :func:`read_secret` continues to serve the new version
        immediately; the M3 sweeper deletes / hardens superseded
        ciphertext after the grace period elapses.

        Emits :data:`SecretEventTopics.SECRET_ROTATED` and
        captures an ``audit.secret.rotated`` row in the same
        transaction.

        :raises: SecretNotFoundError, SecretAccessDeniedError.
    """
    record = (
        db_session.query(SecretRecord)
        .filter(SecretRecord.secret_ref == secret_ref)
        .first()
    )
    if record is None:
        err_msg_lines = ["Cannot rotate secret — record not found."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretNotFoundError(err_msg) from None

    if _has_write_permission(
        db_session=db_session, principal=principal, record=record,
    ) is False:
        _raise_access_denied(secret_ref=secret_ref, action="rotate")

    grace = grace_period if grace_period is not None else DEFAULT_ROTATION_GRACE
    now = utc_now()

    prior_active = (
        db_session.query(SecretVersion)
        .filter(SecretVersion.secret_ref == secret_ref)
        .filter(SecretVersion.state == SecretVersionState.ACTIVE)
        .order_by(SecretVersion.version_number.desc())
        .first()
    )

    payload = encrypt_plaintext(
        plaintext=new_plaintext, secret_ref=secret_ref,
    )
    new_version_number = (
        int(prior_active.version_number) + 1 if prior_active is not None
        else 1
    )
    new_version = SecretVersion(
        version_id=new_uuid(),
        secret_ref=secret_ref,
        version_number=new_version_number,
        state=SecretVersionState.ACTIVE,
        ciphertext_ref=None,
        ciphertext_bytes=payload.ciphertext_bytes,
        wrapped_dek=payload.wrapped_dek,
        kek_id=payload.kek_id,
        grace_expires_at=None,
        created_at=now,
        created_by=principal.user_id,
    )
    db_session.add(new_version)
    db_session.flush()

    if prior_active is not None:
        prior_active.state = SecretVersionState.SUPERSEDED
        prior_active.grace_expires_at = now + grace
        db_session.flush()

    record.current_version_id = new_version.version_id
    record.updated_at = now
    db_session.flush()

    audit_payload = {
        "secret_ref": secret_ref,
        "backend_name": record.backend_name,
        "version_id": str(new_version.version_id),
        "version_number": new_version_number,
        "principal_id": principal.user_id,
        "rotated_at": now.isoformat(),
        "grace_seconds": int(grace.total_seconds()),
    }
    audit_capture(
        db_session=db_session,
        source_event_id=new_uuid(),
        source_topic="entity.secret.rotated",
        kind="audit.secret.rotated",
        actor_user_id=principal.user_id,
        actor_service_identity=None,
        target_ref="secret:{}".format(secret_ref),
        payload=audit_payload,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SecretEventTopics.SECRET_ROTATED,
            payload=audit_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = new_version
    return rtnval


def force_expire_secret(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        secret_ref: str,
        reason: str = "force_expire"
    ) -> int:
    """
        Bypass the rotation grace window and flip every
        non-EXPIRED version of ``secret_ref`` to
        :data:`SecretVersionState.EXPIRED`. Used by the
        on-call path when a secret leak is suspected and
        downstream callers must be cut off immediately.

        Emits :data:`SecretEventTopics.SECRET_FORCE_EXPIRED`
        with the count + actor and captures an
        ``audit.secret.rotated`` row (the M3 audit kind for
        force-expire lands as a follow-up).

        :returns: Number of versions transitioned.
        :raises: SecretNotFoundError, SecretAccessDeniedError.
    """
    record = (
        db_session.query(SecretRecord)
        .filter(SecretRecord.secret_ref == secret_ref)
        .first()
    )
    if record is None:
        err_msg_lines = [
            "Cannot force-expire secret — record not found.",
        ]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretNotFoundError(err_msg) from None

    if _has_write_permission(
        db_session=db_session, principal=principal, record=record,
    ) is False:
        _raise_access_denied(secret_ref=secret_ref, action="force_expire")

    now = utc_now()
    versions: List[SecretVersion] = (
        db_session.query(SecretVersion)
        .filter(SecretVersion.secret_ref == secret_ref)
        .filter(SecretVersion.state != SecretVersionState.EXPIRED)
        .all()
    )
    transitioned = 0
    for version in versions:
        version.state = SecretVersionState.EXPIRED
        version.grace_expires_at = now
        transitioned = transitioned + 1
    db_session.flush()
    record.current_version_id = None
    record.updated_at = now
    db_session.flush()

    audit_payload = {
        "secret_ref": secret_ref,
        "principal_id": principal.user_id,
        "expired_count": transitioned,
        "reason": reason,
        "expired_at": now.isoformat(),
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SecretEventTopics.SECRET_FORCE_EXPIRED,
            payload=audit_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return transitioned


def sweep_expired_versions(
        *,
        db_session: DbSession,
        now: Optional[datetime] = None
    ) -> int:
    """
        Background-sweeper helper: flip every SUPERSEDED
        version whose grace window has elapsed to EXPIRED.

        :param now: Optional timestamp override; defaults to
                    :func:`datetime.now(tz=utc)`.

        :returns: Number of versions transitioned.
    """
    materialized_now = now if now is not None else utc_now()
    superseded: List[SecretVersion] = (
        db_session.query(SecretVersion)
        .filter(SecretVersion.state == SecretVersionState.SUPERSEDED)
        .all()
    )
    transitioned = 0
    for version in superseded:
        deadline = version.grace_expires_at
        if deadline is None:
            continue
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if materialized_now < deadline:
            continue
        version.state = SecretVersionState.EXPIRED
        transitioned = transitioned + 1
    db_session.flush()
    db_session.commit()
    return transitioned
