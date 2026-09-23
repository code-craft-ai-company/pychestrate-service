"""
.. module:: secrets.secrets_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Public internal API for the 1-secrets-vault feature.

.. moduleauthor:: Code Craft AI LLC

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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.audit.audit_writer import capture_event as audit_capture
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.secrets.events import SecretEventTopics
from ccai.pychestrate.webservice.secrets.exceptions import (
    SecretAccessDeniedError,
    SecretAlreadyExistsError,
    SecretNotFoundError,
    SecretVersionExpiredError,
)
from ccai.pychestrate.webservice.secrets.factories.local_backend import (
    decrypt_ciphertext,
    encrypt_plaintext,
)
from ccai.pychestrate.webservice.secrets.models import (
    SecretRecord,
    SecretScopeKind,
    SecretVersion,
    SecretVersionState,
)
from ccai.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from ccai.pychestrate.webservice.secrets.secrets_aspects import SecretsAspects
from ccai.pychestrate.webservice.security.auth.session_service import AuthPrincipal
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


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


# ---------------------------------------------------------------------------
# Scope-aware permission evaluation (PR p20g)
# ---------------------------------------------------------------------------
#
# A secret belongs to exactly one scope:
#
#   ORG     -- service-wide; gated by ``system:secrets.*``.
#   PROJECT -- bound to ``scope_ref`` (a project_id); gated by project
#              membership PLUS ``system:project_secrets.*`` (admins with
#              ``system:secrets.admin`` bypass the membership check).
#   USER    -- bound to ``scope_ref`` (a user_id); the owning user OR an
#              admin holding ``system:secrets.admin``.
#
# A holder of ``system:secrets.admin`` may always read / write / delete
# any secret at any scope.


def _holds_permission(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        permission_key: str
    ) -> bool:
    """
        Return True when the principal holds ``permission_key`` now.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param permission_key: RBAC permission key to evaluate.

        :returns: True when the RBAC decision allows.
    """
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=permission_key,
        now=datetime.now(timezone.utc),
    )
    rtnval = decision.allowed
    return rtnval


def _is_project_member(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        project_id: str
    ) -> bool:
    """
        Return True when the principal has at least one member binding
        on the given project.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param project_id: The project the secret is scoped to.

        :returns: True when a binding exists.
    """
    from ccai.pychestrate.webservice.projects.models import (
        ProjectMemberBinding,
    )

    binding = (
        db_session.query(ProjectMemberBinding)
        .filter(ProjectMemberBinding.project_id == project_id)
        .filter(ProjectMemberBinding.user_id == principal.user_id)
        .first()
    )
    rtnval = binding is not None
    return rtnval


def _has_scope_permission(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        scope_kind: SecretScopeKind,
        scope_ref: Optional[str],
        write: bool
    ) -> bool:
    """
        Evaluate the scope-aware permission decision for a secret.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param scope_kind: The :class:`SecretScopeKind` of the secret.
        :param scope_ref: The project_id (PROJECT) or user_id (USER);
                          None for ORG scope.
        :param write: True for write / rotate / delete; False for read.

        :returns: True when the principal is authorized.
    """
    # A secrets admin may always act on any scope.
    if _holds_permission(
            db_session=db_session,
            principal=principal,
            permission_key="system:secrets.admin") is True:
        return True

    if scope_kind == SecretScopeKind.ORG:
        if write is True:
            rtnval = _holds_permission(
                db_session=db_session,
                principal=principal,
                permission_key="system:secrets.write",
            )
            return rtnval
        rtnval = _holds_permission(
            db_session=db_session,
            principal=principal,
            permission_key="system:secrets.read",
        )
        return rtnval

    if scope_kind == SecretScopeKind.USER:
        # A user manages their own personal secrets.
        if scope_ref is not None and str(scope_ref) == str(principal.user_id):
            return True
        rtnval = False
        return rtnval

    # PROJECT scope: project membership PLUS the project-secrets
    # permission.
    if scope_ref is None:
        rtnval = False
        return rtnval

    if _is_project_member(
            db_session=db_session,
            principal=principal,
            project_id=scope_ref) is False:
        rtnval = False
        return rtnval

    if write is True:
        rtnval = _holds_permission(
            db_session=db_session,
            principal=principal,
            permission_key="system:project_secrets.write",
        )
        return rtnval
    rtnval = _holds_permission(
        db_session=db_session,
        principal=principal,
        permission_key="system:project_secrets.read",
    )
    return rtnval


def _has_write_permission(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        record: Optional[SecretRecord],
        scope_kind: Optional[SecretScopeKind] = None,
        scope_ref: Optional[str] = None
    ) -> bool:
    """
        Evaluate the write decision for a create / rotate / delete.

        When ``record`` is supplied the scope is read from the row;
        otherwise the explicit ``scope_kind`` / ``scope_ref`` of the
        pending create are used.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param record: The owning :class:`SecretRecord` when it exists.
        :param scope_kind: Scope kind for a pending create.
        :param scope_ref: Scope ref for a pending create.

        :returns: True when the principal may write / rotate / delete.
    """
    if record is not None:
        resolved_kind = record.scope_kind
        resolved_ref = record.scope_ref
    else:
        resolved_kind = scope_kind if scope_kind is not None else SecretScopeKind.ORG
        resolved_ref = scope_ref

    rtnval = _has_scope_permission(
        db_session=db_session,
        principal=principal,
        scope_kind=resolved_kind,
        scope_ref=resolved_ref,
        write=True,
    )
    return rtnval


def _has_read_permission(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        record: SecretRecord
    ) -> bool:
    """
        Evaluate the scope-aware read decision for a secret value read.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param record: The owning :class:`SecretRecord`.

        :returns: True when the principal may read the secret value.
    """
    rtnval = _has_scope_permission(
        db_session=db_session,
        principal=principal,
        scope_kind=record.scope_kind,
        scope_ref=record.scope_ref,
        write=False,
    )
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


def _resolve_scope_or_raise(
        *,
        secret_ref: str,
        scope_kind: SecretScopeKind,
        scope_ref: Optional[str]
    ) -> Optional[str]:
    """
        Validate that ``scope_ref`` is consistent with ``scope_kind``.

        :param secret_ref: Canonical secret reference (for messages).
        :param scope_kind: The requested :class:`SecretScopeKind`.
        :param scope_ref: The requested project_id / user_id.

        :returns: The normalized ``scope_ref`` (None for ORG scope).
        :raises: SemanticError
    """
    from ccai.errors.exceptions import SemanticError

    if scope_kind == SecretScopeKind.ORG:
        if scope_ref is not None and len(str(scope_ref)) > 0:
            err_msg_lines = ["ORG-scoped secrets must not carry a scope_ref."]
            err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg) from None
        rtnval = None
        return rtnval

    if scope_ref is None or len(str(scope_ref)) == 0:
        err_msg_lines = ["PROJECT / USER scoped secrets require a scope_ref."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg_lines.append("SCOPE_KIND: {}".format(scope_kind.value))
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg) from None

    rtnval = str(scope_ref)
    return rtnval


def list_secrets(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        scope_kind: Optional[SecretScopeKind] = None,
        scope_ref: Optional[str] = None
    ) -> list:
    """
        Return secret metadata rows, optionally filtered by scope. No
        plaintext or ciphertext is touched by this function.

        The caller must hold ``system:secrets.read`` OR
        ``system:secrets.admin``. This mirrors the pattern used in
        :func:`read_secret` and :func:`put_secret` where
        :func:`_has_read_permission` / :func:`_has_write_permission`
        gate the operation at the service layer.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal; used for the
                          service-layer authz check.
        :param scope_kind: Optional :class:`SecretScopeKind` filter.
        :param scope_ref: Optional scope_ref filter.

        :returns: List of :class:`SecretRecord` rows.
        :raises: SecretAccessDeniedError
    """
    holds_read = _holds_permission(
        db_session=db_session,
        principal=principal,
        permission_key="system:secrets.read",
    )
    holds_admin = _holds_permission(
        db_session=db_session,
        principal=principal,
        permission_key="system:secrets.admin",
    )
    if holds_read is False and holds_admin is False:
        err_msg_lines = ["Secret list access denied."]
        err_msg_lines.append("PRINCIPAL: {}".format(principal.user_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretAccessDeniedError(err_msg) from None

    query = db_session.query(SecretRecord)
    if scope_kind is not None:
        query = query.filter(SecretRecord.scope_kind == scope_kind)
    if scope_ref is not None and len(scope_ref) > 0:
        query = query.filter(SecretRecord.scope_ref == scope_ref)

    rtnval = query.order_by(SecretRecord.secret_ref.asc()).all()
    return rtnval


def get_secret_record(
        *,
        db_session: DbSession,
        secret_ref: str
    ) -> SecretRecord:
    """
        Return a single secret metadata row.

        :param db_session: Active SQLAlchemy session.
        :param secret_ref: Canonical secret reference.

        :returns: The :class:`SecretRecord`.
        :raises: SecretNotFoundError
    """
    record = (
        db_session.query(SecretRecord)
        .filter(SecretRecord.secret_ref == secret_ref)
        .first()
    )
    if record is None:
        err_msg_lines = ["Cannot read secret — record not found."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretNotFoundError(err_msg) from None

    rtnval = record
    return rtnval


def put_secret(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        secret_ref: str,
        plaintext: SecretBytes,
        aspects: SecretsAspects,
        scope_kind: SecretScopeKind = SecretScopeKind.ORG,
        scope_ref: Optional[str] = None,
        owner_user_id: Optional[str] = None
    ) -> SecretVersion:
    """
        Store a secret at version 1 using the local backend's AES-GCM
        encryption. The scope-aware ACL is enforced, an audit record is
        captured in the same transaction, and ``entity.secret.created``
        is staged for after-commit publication.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param secret_ref: Canonical secret reference.
        :param plaintext: The :class:`SecretBytes` payload.
        :param aspects: Caller behavior knobs.
        :param scope_kind: The :class:`SecretScopeKind` of the new
                           secret. Defaults to ORG (service-wide).
        :param scope_ref: The project_id (PROJECT) or user_id (USER);
                          must be None for ORG scope.
        :param owner_user_id: Owner for the new record. Defaults to the
                              principal's ``user_id`` when None.

        :returns: The persisted :class:`SecretVersion`.
        :raises: SecretAlreadyExistsError, SecretAccessDeniedError,
                 SemanticError
    """
    resolved_scope_ref = _resolve_scope_or_raise(
        secret_ref=secret_ref,
        scope_kind=scope_kind,
        scope_ref=scope_ref,
    )

    existing = (
        db_session.query(SecretRecord).filter(SecretRecord.secret_ref == secret_ref).first()
    )
    if existing is not None:
        err_msg_lines = ["Cannot create secret — record already exists."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretAlreadyExistsError(err_msg) from None

    if _has_write_permission(
            db_session=db_session,
            principal=principal,
            record=None,
            scope_kind=scope_kind,
            scope_ref=resolved_scope_ref) is False:
        _raise_access_denied(secret_ref=secret_ref, action="write")

    resolved_owner = owner_user_id
    if resolved_owner is None:
        resolved_owner = principal.user_id

    resolved_project_id: Optional[str] = None
    if scope_kind == SecretScopeKind.PROJECT:
        resolved_project_id = resolved_scope_ref
    if scope_kind == SecretScopeKind.USER:
        resolved_owner = resolved_scope_ref

    now = utc_now()
    record = SecretRecord(
        secret_ref=secret_ref,
        current_version_id=None,
        backend_name=LOCAL_BACKEND_NAME,
        owner_user_id=resolved_owner,
        owner_project_id=resolved_project_id,
        scope_kind=scope_kind,
        scope_ref=resolved_scope_ref,
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


def update_secret(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        secret_ref: str,
        plaintext: SecretBytes,
        aspects: SecretsAspects
    ) -> SecretVersion:
    """
        Rotate / update a secret's value. The current ACTIVE version is
        marked SUPERSEDED and a new ACTIVE version is installed with a
        fresh DEK. The scope-aware write ACL is enforced, an audit
        record (``audit.secret.updated``) is captured in the same
        transaction, and ``entity.secret.rotated`` is staged.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param secret_ref: Canonical secret reference.
        :param plaintext: The new :class:`SecretBytes` payload.
        :param aspects: Caller behavior knobs.

        :returns: The persisted new :class:`SecretVersion`.
        :raises: SecretNotFoundError, SecretAccessDeniedError
    """
    record = get_secret_record(db_session=db_session, secret_ref=secret_ref)

    if _has_write_permission(
            db_session=db_session,
            principal=principal,
            record=record) is False:
        _raise_access_denied(secret_ref=secret_ref, action="rotate")

    previous = (
        db_session.query(SecretVersion)
        .filter(SecretVersion.secret_ref == secret_ref)
        .order_by(SecretVersion.version_number.desc())
        .first()
    )
    next_number = 1
    if previous is not None:
        next_number = int(previous.version_number) + 1
        previous.state = SecretVersionState.SUPERSEDED

    now = utc_now()
    payload = encrypt_plaintext(plaintext=plaintext, secret_ref=secret_ref)
    version = SecretVersion(
        version_id=new_uuid(),
        secret_ref=secret_ref,
        version_number=next_number,
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
    record.updated_at = now
    db_session.flush()

    audit_payload = {
        "secret_ref": secret_ref,
        "backend_name": record.backend_name,
        "version_id": str(version.version_id),
        "principal_id": principal.user_id,
        "updated_at": now.isoformat(),
    }
    audit_capture(
        db_session=db_session,
        source_event_id=new_uuid(),
        source_topic="entity.secret.rotated",
        kind="audit.secret.updated",
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

    rtnval = version
    return rtnval


def delete_secret(
        *,
        db_session: DbSession,
        principal: AuthPrincipal,
        secret_ref: str,
        aspects: SecretsAspects
    ) -> None:
    """
        Delete a secret and every version row. The scope-aware write
        ACL is enforced, an audit record (``audit.secret.deleted``) is
        captured in the same transaction, and
        ``entity.secret.force_expired`` is staged.

        :param db_session: Active SQLAlchemy session.
        :param principal: The authenticated principal.
        :param secret_ref: Canonical secret reference.
        :param aspects: Caller behavior knobs.

        :returns: None.
        :raises: SecretNotFoundError, SecretAccessDeniedError
    """
    record = get_secret_record(db_session=db_session, secret_ref=secret_ref)

    if _has_write_permission(
            db_session=db_session,
            principal=principal,
            record=record) is False:
        _raise_access_denied(secret_ref=secret_ref, action="delete")

    backend_name = record.backend_name
    now = utc_now()
    audit_payload = {
        "secret_ref": secret_ref,
        "backend_name": backend_name,
        "principal_id": principal.user_id,
        "deleted_at": now.isoformat(),
    }
    audit_capture(
        db_session=db_session,
        source_event_id=new_uuid(),
        source_topic="entity.secret.force_expired",
        kind="audit.secret.deleted",
        actor_user_id=principal.user_id,
        actor_service_identity=None,
        target_ref="secret:{}".format(secret_ref),
        payload=audit_payload,
    )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SecretEventTopics.SECRET_FORCE_EXPIRED,
            payload=audit_payload,
            source_event_id=new_uuid(),
        ),
    )

    db_session.query(SecretVersion).filter(
        SecretVersion.secret_ref == secret_ref
    ).delete(synchronize_session=False)
    db_session.delete(record)
    db_session.commit()

    rtnval = None
    return rtnval


# ---------------------------------------------------------------------------
# Service-identity reads (8-webhooks-in, audit ORC-29)
# ---------------------------------------------------------------------------


def read_secret_for_service(
        *,
        db_session: DbSession,
        secret_ref: str,
        service_identity: str
    ) -> SecretRead:
    """
        Decrypt the active version of a secret on behalf of in-process
        service code rather than a user.

        Some consumers must resolve a secret reference while serving a
        request that carries no principal -- the inbound-webhook receiver
        verifies a provider's HMAC signature with the shared secret an
        authorized user bound to the integration when configuring it. No
        principal ACL applies here: the binding step is where the user's
        right to use the secret was checked (and audited), and this
        function is only reachable from service code, never from a REST
        route.

        No audit record is written per read. The callers are machine
        paths that resolve the same reference on every inbound request;
        auditing each resolution would let unauthenticated traffic grow
        the audit chain without bound. The security-relevant events --
        creating the secret and binding it to its consumer -- are
        audited where they happen.

        :param db_session: Active SQLAlchemy session.
        :param secret_ref: Canonical secret reference.
        :param service_identity: Name of the calling service (for
                                 example ``"webhooks_in"``); used in
                                 error messages only.

        :returns: :class:`SecretRead` wrapping the decrypted plaintext.
        :raises: SecretNotFoundError, SecretVersionExpiredError
    """
    record = (
        db_session.query(SecretRecord).filter(SecretRecord.secret_ref == secret_ref).first()
    )
    if record is None:
        err_msg_lines = ["Cannot resolve secret for service — record not found."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg_lines.append("SERVICE: {}".format(service_identity))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretNotFoundError(err_msg) from None

    version = (
        db_session.query(SecretVersion)
        .filter(SecretVersion.version_id == record.current_version_id)
        .first()
    )
    if version is None:
        err_msg_lines = ["Cannot resolve secret for service — active version missing."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg_lines.append("SERVICE: {}".format(service_identity))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretNotFoundError(err_msg) from None

    if version.state == SecretVersionState.EXPIRED:
        err_msg_lines = ["Cannot resolve secret for service — active version is expired."]
        err_msg_lines.append("SECRET_REF: {}".format(secret_ref))
        err_msg_lines.append("SERVICE: {}".format(service_identity))
        err_msg_lines.append("VERSION_NUMBER: {}".format(version.version_number))
        err_msg = os.linesep.join(err_msg_lines)
        raise SecretVersionExpiredError(err_msg) from None

    plaintext = decrypt_ciphertext(
        ciphertext_bytes=bytes(version.ciphertext_bytes),
        wrapped_dek=bytes(version.wrapped_dek),
        secret_ref=secret_ref,
    )

    rtnval = SecretRead(
        plaintext=plaintext,
        secret_ref=secret_ref,
        version_number=int(version.version_number),
        metadata=None,
    )
    return rtnval
