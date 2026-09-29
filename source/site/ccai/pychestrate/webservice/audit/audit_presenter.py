"""
.. module:: audit.audit_presenter
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Human-readable rows for audit records (the admin Audit
               Logs page and its CSV / JSONL export).

.. moduleauthor:: Code Craft AI LLC

An audit record stores a kind (``audit.data.updated``) and a JSON
payload. This module turns one into what an administrator reads: who,
did what ("Updated project"), to what ("Demo (#5)"), with which
details ("changed: status (running -> done)"), from where.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


SYSTEM_ACTOR_LABEL: str = "System"


@dataclass(frozen=True)
class AuditRow:
    """
        One audit record, ready to display or export.

        :param sequence_number: The record's sequence number.
        :param written_at: When it was written (UTC).
        :param kind: The audit kind.
        :param action: Short readable action ("Signed in").
        :param actor_user_id: Acting user id (may be None).
        :param actor_label: Acting user's login, a service identity,
                            or "System".
        :param target_ref: The record's target reference.
        :param summary: One-line readable details.
        :param client_address: Client address, when recorded.
        :param payload: The record's payload.
        :param payload_text: The payload as indented JSON.
        :param record_hash_hex: The hash-chain value.
    """
    sequence_number: int
    written_at: Optional[datetime]
    kind: str
    action: str
    actor_user_id: Optional[str]
    actor_label: str
    target_ref: Optional[str]
    summary: str
    client_address: Optional[str]
    payload: Dict[str, Any]
    payload_text: str
    record_hash_hex: str


_ACTIONS = {
    "audit.auth.login_rejected": "Sign-in rejected",
    "audit.session.opened": "Signed in",
    "audit.session.closed": "Session ended",
    "audit.user.created": "Created user",
    "audit.user.updated": "Updated user",
    "audit.user.deactivated": "Deactivated user",
    "audit.user.reactivated": "Reactivated user",
    "audit.user.password_changed": "Changed own password",
    "audit.user.password_reset": "Reset a user's password",
    "audit.user.password_link_issued": "Issued a password link",
    "audit.user.password_link_redeemed": "Set password from a link",
    "audit.role.assigned": "Granted role",
    "audit.role.revoked": "Removed role",
    "audit.role.created": "Created role",
    "audit.role.updated": "Updated role",
    "audit.role.deleted": "Deleted role",
    "audit.secret.created": "Created secret",
    "audit.secret.accessed": "Read secret",
    "audit.secret.updated": "Rotated secret",
    "audit.secret.deleted": "Deleted secret",
    "audit.variable.set": "Set variable",
    "audit.variable.unset": "Removed variable",
    "audit.project.created": "Created project",
    "audit.project.archived": "Archived project",
    "audit.project.unarchived": "Unarchived project",
    "audit.project.deleted": "Deleted project",
    "audit.project.member_added": "Added project member",
    "audit.project.member_removed": "Removed project member",
    "audit.ui_profile.deployment_changed": "Changed the UI profile",
    "audit.reservation.overridden": "Acted on another person's reservation",
    "audit.ip_allocation.force_released": "Released another person's IP address",
}

_DATA_VERBS = {
    "audit.data.created": "Created",
    "audit.data.updated": "Updated",
    "audit.data.deleted": "Deleted",
}

_SESSION_CLOSE_REASONS = {
    "user_logout": "signed out",
    "admin_terminated": "terminated by an administrator",
    "user_deactivated": "account deactivated",
    "password_changed": "password changed",
    "password_reset": "password reset",
    "signed_out_everywhere": "signed out everywhere",
}

_LOGIN_REJECTION_REASONS = {
    "invalid_credentials": "wrong username or password",
    "rate_limited": "too many recent failures",
    "account_inactive": "account not active",
    "missing_credentials": "username or password missing",
    "password_change_required": "password change required",
}


def action_for_kind(*, kind: str, payload: Optional[Dict[str, Any]] = None) -> str:
    """
        Short readable action for an audit kind.

        :param kind: The audit kind.
        :param payload: The payload (data-change events name their
                        entity).

        :returns: E.g. ``"Updated project"`` or ``"Signed in"``.
    """
    if kind in _DATA_VERBS:
        entity = ""
        if payload is not None:
            entity = str(payload.get("entity", "") or "")
        rtnval = "{} {}".format(_DATA_VERBS[kind], entity).strip()
        return rtnval
    known = _ACTIONS.get(kind, None)
    if known is not None:
        return known
    text = kind
    if text.startswith("audit.") is True:
        text = text[len("audit."):]
    text = text.replace(".", " ").replace("_", " ").strip()
    if len(text) == 0:
        return kind
    rtnval = text[0].upper() + text[1:]
    return rtnval


def _name_for(*, user_id: Any, logins: Dict[str, str]) -> Optional[str]:
    if user_id is None:
        return None
    rtnval = logins.get(str(user_id), None)
    return rtnval


def _format_change(*, field_name: str, change: Dict[str, Any]) -> str:
    old_value = change.get("from", None)
    new_value = change.get("to", None)
    rtnval = "{} ({} -> {})".format(field_name, old_value, new_value)
    return rtnval


def _summary(*, kind: str, payload: Dict[str, Any], logins: Dict[str, str]) -> str:
    """
        One-line readable details for a record.

        :param kind: The audit kind.
        :param payload: The payload.
        :param logins: ``{user_id: login_name}`` for name lookups.

        :returns: Summary text.
    """
    parts: List[str] = []

    if kind in _DATA_VERBS:
        label = payload.get("label", None)
        entity_id = payload.get("entity_id", "")
        if label is not None and len(str(label)) > 0:
            parts.append('"{}" (#{})'.format(label, entity_id))
        else:
            parts.append("#{}".format(entity_id))
        changed = payload.get("changed_fields", None)
        changes = payload.get("changes", None)
        if isinstance(changes, dict) is False:
            changes = {}
        if changed is not None and len(changed) > 0:
            described = []
            for field_name in changed:
                if field_name in changes:
                    described.append(_format_change(field_name=field_name, change=changes[field_name]))
                else:
                    described.append(field_name)
            parts.append("changed: {}".format(", ".join(described)))
        return " - ".join(parts)

    if kind.startswith("audit.session.") is True:
        user_name = _name_for(user_id=payload.get("user_id"), logins=logins)
        if user_name is not None:
            parts.append(user_name)
        reason = payload.get("reason", None)
        if reason is not None:
            parts.append(_SESSION_CLOSE_REASONS.get(str(reason), str(reason)))
        agent = payload.get("user_agent", None)
        if agent is not None and len(str(agent)) > 0:
            parts.append(str(agent))
        return " - ".join(parts)

    if kind == "audit.auth.login_rejected":
        parts.append('username "{}"'.format(payload.get("login_name", "")))
        reason = str(payload.get("reason", ""))
        parts.append(_LOGIN_REJECTION_REASONS.get(reason, reason))
        return " - ".join(parts)

    if kind.startswith("audit.user.") is True:
        login_name = payload.get("login_name", None)
        if login_name is None:
            login_name = _name_for(user_id=payload.get("user_id"), logins=logins)
        if login_name is not None:
            parts.append(str(login_name))
        changed = payload.get("changed_fields", None)
        if changed is not None and len(changed) > 0:
            parts.append("changed: {}".format(", ".join(str(item) for item in changed)))
        purpose = payload.get("purpose", None)
        if purpose is not None:
            parts.append("{} link".format(purpose))
        expires = payload.get("expires_at", None)
        if expires is not None:
            parts.append("expires {}".format(expires))
        if payload.get("must_change", None) is True:
            parts.append("must change at next sign-in")
        return " - ".join(parts)

    if kind == "audit.ip_allocation.force_released":
        parts.append(str(payload.get("ip_address", "")))
        holder = _name_for(user_id=payload.get("holder_user_id"), logins=logins)
        if holder is not None:
            parts.append("held by {}".format(holder))
        parts.append('reason: "{}"'.format(payload.get("reason", "")))
        return " - ".join(parts)

    if kind == "audit.reservation.overridden":
        parts.append("reservation #{}".format(payload.get("reservation_id", "")))
        parts.append(str(payload.get("action", "")))
        owner = _name_for(user_id=payload.get("owner_user_id"), logins=logins)
        if owner is not None:
            parts.append("owner {}".format(owner))
        parts.append('reason: "{}"'.format(payload.get("reason", "")))
        return " - ".join(parts)

    if kind.startswith("audit.role.") is True:
        role_name = payload.get("role_name", None)
        if role_name is not None:
            parts.append(str(role_name))
        principal = payload.get("principal_id", None)
        if principal is not None:
            name = _name_for(user_id=principal, logins=logins)
            parts.append("user {}".format(name if name is not None else principal))
        keys = payload.get("permission_keys", None)
        if keys is not None:
            parts.append("{} permission(s)".format(len(keys)))
        removed = payload.get("removed_binding_count", None)
        if removed is not None:
            parts.append("{} binding(s) removed".format(removed))
        return " - ".join(parts)

    for key in ("secret_ref", "slug", "name", "type_id", "job_id", "spec_id"):
        value = payload.get(key, None)
        if value is not None:
            parts.append("{}: {}".format(key.replace("_", " "), value))
    surfaces = payload.get("surfaces", None)
    if surfaces is not None:
        parts.append("surfaces: {}".format(", ".join(str(item) for item in surfaces)))
    rtnval = " - ".join(parts)
    return rtnval


def actor_label_for(
        *,
        actor_user_id: Optional[str],
        actor_service_identity: Optional[str],
        logins: Dict[str, str]
    ) -> str:
    """
        The display name of a record's actor.

        :param actor_user_id: Acting user id.
        :param actor_service_identity: Acting service identity.
        :param logins: ``{user_id: login_name}``.

        :returns: A login name, the user id when the user no longer
                  exists, the service identity, or "System".
    """
    if actor_user_id is not None:
        rtnval = logins.get(str(actor_user_id), str(actor_user_id))
        return rtnval
    if actor_service_identity is not None and len(str(actor_service_identity)) > 0:
        return str(actor_service_identity)
    return SYSTEM_ACTOR_LABEL


def user_ids_in_records(*, records: Iterable[Any]) -> List[str]:
    """
        Every user id a batch of records mentions (actors, subjects,
        principals), for one login-name lookup.

        :param records: :class:`AuditRecord` rows.

        :returns: Distinct user id strings.
    """
    found = set()
    for record in records:
        if record.actor_user_id is not None:
            found.add(str(record.actor_user_id))
        payload = record.payload_json if isinstance(record.payload_json, dict) else {}
        for key in ("user_id", "principal_id"):
            value = payload.get(key, None)
            if value is not None:
                found.add(str(value))
    rtnval = sorted(found)
    return rtnval


def describe_audit_record(*, record: Any, logins: Dict[str, str]) -> AuditRow:
    """
        Turn one :class:`AuditRecord` into an :class:`AuditRow`.

        :param record: The record.
        :param logins: ``{user_id: login_name}``.

        :returns: The row.
    """
    payload = record.payload_json if isinstance(record.payload_json, dict) else {}
    actor_user_id = str(record.actor_user_id) if record.actor_user_id is not None else None
    record_hash = record.record_hash
    rtnval = AuditRow(
        sequence_number=int(record.sequence_number),
        written_at=record.written_at,
        kind=record.kind,
        action=action_for_kind(kind=record.kind, payload=payload),
        actor_user_id=actor_user_id,
        actor_label=actor_label_for(
            actor_user_id=actor_user_id,
            actor_service_identity=record.actor_service_identity,
            logins=logins,
        ),
        target_ref=record.target_ref,
        summary=_summary(kind=record.kind, payload=payload, logins=logins),
        client_address=payload.get("client_address", None),
        payload=payload,
        payload_text=json.dumps(payload, indent=2, sort_keys=True, default=str),
        record_hash_hex=bytes(record_hash).hex() if record_hash is not None else "",
    )
    return rtnval


def load_login_names(*, db_session: Any, user_ids: List[str]) -> Dict[str, str]:
    """
        ``{user_id: login_name}`` for the given ids (unknown ids are
        left out).

        :param db_session: Active SQLAlchemy session.
        :param user_ids: User id strings.

        :returns: The mapping.
    """
    import uuid as _uuid  # noqa: E402

    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityUser,
    )

    parsed = []
    for value in user_ids:
        try:
            parsed.append(_uuid.UUID(str(value)))
        except ValueError:
            continue
    rtnval: Dict[str, str] = {}
    if len(parsed) == 0:
        return rtnval
    rows = (
        db_session.query(IdentityUser.user_id, IdentityUser.login_name)
        .filter(IdentityUser.user_id.in_(parsed))
        .all()
    )
    for user_id, login_name in rows:
        rtnval[str(user_id)] = login_name
    return rtnval


__all__ = [
    "AuditRow",
    "SYSTEM_ACTOR_LABEL",
    "action_for_kind",
    "actor_label_for",
    "describe_audit_record",
    "load_login_names",
    "user_ids_in_records",
]
