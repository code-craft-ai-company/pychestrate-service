"""
.. module:: clients.registry.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Client registry service — M1 surface.

.. moduleauthor:: Code Craft AI LLC

M1 implements the read/write core the rest of Phase 2 relies on:

* :func:`register_client` — called by the enrollment service after a
  successful token redemption. Creates the ``clients_clients`` row and
  publishes ``entity.client.registered``.
* :func:`record_heartbeat` — updates ``last_seen`` / ``last_agent_version``
  / ``transport_name`` with a monotonic guard so a slower-to-arrive
  heartbeat never overwrites a newer ``last_seen``.
* :func:`update_attributes` — validates each submitted (kind, value)
  against the registered :class:`ClientAttributeExtension` schema and
  upserts the row; publishes ``entity.client.attributes_changed``.
* :func:`set_liveness_state` — operator-triggered transition (used by
  heartbeat watchdogs and admin flows).
* :func:`list_clients` / :func:`get_client` / :func:`get_client_by_scope` —
  read surface.
* :func:`find_scope_holder` — the non-revoked client holding a
  ``(project_id, pod_name)`` scope, if any.

The richer Python facade described in ``specs/3-client-registry/design.md``
(with a dedicated ``ClientRegistry`` class, async repository, and cache
priming) is left for M2. The free-function surface here keeps parity with
every other Phase-1 service module and is trivial to wrap in an object
facade later.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.clients.enums import (
    ClientStatus,
    LivenessState,
)
from ccai.pychestrate.webservice.clients.events import ClientEventTopics
from ccai.pychestrate.webservice.clients.exceptions import (
    ClientAlreadyExistsError,
    ClientNotFoundError,
    InvalidAttributeValueError,
    UnknownAttributeKindError,
)
from ccai.pychestrate.webservice.clients.models import (
    Client,
    ClientAttribute,
)
from ccai.pychestrate.webservice.clients.registry.extensions.client_attribute_extension import (
    ClientAttributeExtension,
)
from ccai.pychestrate.webservice.extensions.registry import list_resource_extensions
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


@dataclass(frozen=True)
class AttributeUpdate:
    """
        One kind-value pair submitted to :func:`update_attributes`.

        :param kind: Canonical attribute kind name (must match a
                     registered :class:`ClientAttributeExtension`).
        :param value: JSON-serializable value to persist.
    """
    kind: str
    value: Any


@dataclass(frozen=True)
class ClientView:
    """
        Read-model for the REST + internal surfaces.

        :param client_id: Server-assigned UUID.
        :param project_id: Owning project UUID.
        :param pod_name: Pod this agent registered under.
        :param status: ClientStatus enum value.
        :param liveness_state: LivenessState enum value.
        :param enrolled_at_iso: ISO-8601 enrollment timestamp.
        :param last_seen_iso: Last heartbeat timestamp (may be None).
        :param last_agent_version: Reported agent version string.
        :param transport_name: Transport last observed on (http, ws, …).
        :param degraded_at_iso: When the agent entered DEGRADED (nullable).
        :param revision_token: Monotonic update token.
        :param attributes: Map of kind -> value_json for this client.
    """
    client_id: str
    project_id: str
    pod_name: str
    status: ClientStatus
    liveness_state: LivenessState
    enrolled_at_iso: str
    last_seen_iso: Optional[str]
    last_agent_version: Optional[str]
    transport_name: Optional[str]
    degraded_at_iso: Optional[str]
    revision_token: str
    attributes: Mapping[str, Any] = field(default_factory=dict)


def _load_attribute_kinds() -> Dict[str, type]:
    """
        Snapshot the registered :class:`ClientAttributeExtension` kinds
        by name. Rebuilt on every call — the registry is authoritative
        and cheap to read.

        :returns: Dict of kind_name -> extension class.
    """
    packs = list_resource_extensions(base_class=ClientAttributeExtension)
    rtnval: Dict[str, type] = {}
    for pack in packs:
        name = getattr(pack, "attribute_kind_name", "")
        if name is None or len(name) == 0:
            continue
        rtnval[name] = pack
    return rtnval


def _validate_attribute_value(*, kind: str, value: Any, pack: type) -> None:
    """
        Minimal schema validation for an attribute value. The M1 path
        checks enum membership, object-required keys, and integer bounds
        declared in the attribute's ``value_schema``. Full JSON-Schema
        draft-07 validation lands in M2 once ``jsonschema`` is on the
        classpath.

        :param kind: Attribute kind name.
        :param value: Submitted value.
        :param pack: Registered :class:`ClientAttributeExtension` subclass.

        :returns: None.
        :raises: InvalidAttributeValueError
    """
    schema = getattr(pack, "value_schema", {})
    declared_type = schema.get("type", None)

    if declared_type == "string":
        if isinstance(value, str) is False:
            _raise_invalid_attribute(kind=kind, reason="expected_string")
        enum_choices = schema.get("enum", None)
        if enum_choices is not None and value not in enum_choices:
            _raise_invalid_attribute(kind=kind, reason="not_in_enum")
        return

    if declared_type == "object":
        if isinstance(value, dict) is False:
            _raise_invalid_attribute(kind=kind, reason="expected_object")
        required = schema.get("required", [])
        for required_key in required:
            if required_key not in value:
                _raise_invalid_attribute(
                    kind=kind,
                    reason="missing_required_key:{}".format(required_key),
                )
        properties = schema.get("properties", {})
        for key, field_schema in properties.items():
            if key not in value:
                continue
            raw = value[key]
            if "enum" in field_schema and raw not in field_schema["enum"]:
                _raise_invalid_attribute(
                    kind=kind,
                    reason="property_not_in_enum:{}".format(key),
                )
            if field_schema.get("type") == "integer":
                if isinstance(raw, bool) is True or isinstance(raw, int) is False:
                    _raise_invalid_attribute(
                        kind=kind,
                        reason="property_not_integer:{}".format(key),
                    )
                minimum = field_schema.get("minimum", None)
                maximum = field_schema.get("maximum", None)
                if minimum is not None and raw < minimum:
                    _raise_invalid_attribute(
                        kind=kind,
                        reason="property_below_minimum:{}".format(key),
                    )
                if maximum is not None and raw > maximum:
                    _raise_invalid_attribute(
                        kind=kind,
                        reason="property_above_maximum:{}".format(key),
                    )
            if field_schema.get("type") == "string":
                if isinstance(raw, str) is False:
                    _raise_invalid_attribute(
                        kind=kind,
                        reason="property_not_string:{}".format(key),
                    )
                min_length = field_schema.get("minLength", None)
                max_length = field_schema.get("maxLength", None)
                if min_length is not None and len(raw) < min_length:
                    _raise_invalid_attribute(
                        kind=kind,
                        reason="property_too_short:{}".format(key),
                    )
                if max_length is not None and len(raw) > max_length:
                    _raise_invalid_attribute(
                        kind=kind,
                        reason="property_too_long:{}".format(key),
                    )
        allow_additional = schema.get("additionalProperties", True)
        if allow_additional is False:
            for key in value.keys():
                if key not in properties:
                    _raise_invalid_attribute(
                        kind=kind,
                        reason="unexpected_property:{}".format(key),
                    )
        return

    # Unknown schema shape: treat as opaque JSON and accept. M2 will tighten.
    return


def _raise_invalid_attribute(*, kind: str, reason: str) -> None:
    err_msg_lines = ["Client attribute value failed schema validation."]
    err_msg_lines.append("KIND: {}".format(kind))
    err_msg_lines.append("REASON: {}".format(reason))
    err_msg = os.linesep.join(err_msg_lines)
    raise InvalidAttributeValueError(err_msg) from None


def _load_client(*, db_session: DbSession, client_id: str) -> Client:
    client = db_session.query(Client).filter(Client.client_id == client_id).first()
    if client is None:
        err_msg_lines = ["Client not found."]
        err_msg_lines.append("CLIENT_ID: {}".format(client_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ClientNotFoundError(err_msg) from None
    return client


def find_scope_holder(
        *,
        db_session: DbSession,
        project_id: str,
        pod_name: str
    ) -> Optional[Client]:
    """
        Return the client that holds the ``(project_id, pod_name)``
        scope: the one that is not REVOKED. A revoked client gives up
        its pod name so a replacement machine can enroll under it
        (E2E-25); its row stays for history.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID.
        :param pod_name: Pod name.

        :returns: The holding :class:`Client`, or None when the scope
                  is free.
    """
    rtnval = (
        db_session.query(Client)
        .filter(Client.project_id == project_id)
        .filter(Client.pod_name == pod_name)
        .filter(Client.status != ClientStatus.REVOKED)
        .first()
    )
    return rtnval


def register_client(
        *,
        db_session: DbSession,
        project_id: str,
        pod_name: str,
        bearer_token_hash: Optional[bytes],
        agent_version: Optional[str],
        transport_name: Optional[str],
        client_id: Optional[str] = None,
        commit: bool = True
    ) -> Client:
    """
        Create a new ``clients_clients`` row and publish
        ``entity.client.registered``. Called by the enrollment service
        after a successful token redemption.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.
        :param pod_name: Pod scope the token was issued against.
        :param bearer_token_hash: Server-side digest of the bearer token
                                  returned to the agent; None for anonymous
                                  M1 test flows.
        :param agent_version: Reported agent version string.
        :param transport_name: Transport name the agent plans to use.
        :param client_id: Client UUID to register under. The enrollment
                          service mints it up front so the client
                          certificate can be issued for it before any
                          row is written; ``None`` mints a fresh one.
        :param commit: Commit the new row (the default). The enrollment
                       service passes ``False`` so the client, its
                       certificate and the redeemed token land in one
                       transaction -- a later failure then leaves no
                       half-enrolled client behind.

        :returns: The persisted :class:`Client`.
        :raises: ClientAlreadyExistsError
    """
    existing = find_scope_holder(
        db_session=db_session, project_id=project_id, pod_name=pod_name,
    )
    if existing is not None:
        err_msg_lines = [
            "Pod name {!r} is already enrolled in this project as client {} ({}). Revoke "
            "that client before enrolling a replacement, or enroll under a different "
            "pod name.".format(pod_name, existing.client_id, existing.status.value)
        ]
        err_msg_lines.append("PROJECT_ID: {}".format(project_id))
        err_msg_lines.append("POD_NAME: {}".format(pod_name))
        err_msg_lines.append("CLIENT_ID: {}".format(existing.client_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise ClientAlreadyExistsError(err_msg) from None

    resolved_client_id = client_id
    if resolved_client_id is None or len(str(resolved_client_id)) == 0:
        resolved_client_id = new_uuid()

    now = utc_now()
    client = Client(
        client_id=resolved_client_id,
        project_id=project_id,
        pod_name=pod_name,
        status=ClientStatus.ACTIVE,
        liveness_state=LivenessState.ALIVE,
        enrolled_at=now,
        last_seen=None,
        last_agent_version=agent_version,
        transport_name=transport_name,
        degraded_at=None,
        revision_token=new_uuid(),
        bearer_token_hash=bearer_token_hash,
    )
    db_session.add(client)
    db_session.flush()

    payload = {
        "client_id": str(client.client_id),
        "project_id": str(project_id),
        "pod_name": pod_name,
        "enrolled_at": now.isoformat(),
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientEventTopics.REGISTERED,
            payload=payload,
            source_event_id=new_uuid(),
        ),
    )
    if commit is True:
        db_session.commit()

    rtnval = client
    return rtnval


def record_heartbeat(
        *,
        db_session: DbSession,
        client_id: str,
        received_at: datetime,
        agent_version: Optional[str],
        transport_name: Optional[str]
    ) -> None:
    """
        Apply a heartbeat to the registry. Writes are guarded by a
        ``last_seen`` monotonicity check so a stale heartbeat cannot
        overwrite a newer one.

        :param db_session: Active SQLAlchemy session.
        :param client_id: Target client UUID.
        :param received_at: Server-side receive timestamp.
        :param agent_version: Reported agent version.
        :param transport_name: Transport name the heartbeat arrived on.

        :returns: None.
        :raises: ClientNotFoundError
    """
    client = _load_client(db_session=db_session, client_id=client_id)

    previous_last_seen = client.last_seen
    if previous_last_seen is not None:
        if previous_last_seen.tzinfo is None:
            previous_last_seen = previous_last_seen.replace(tzinfo=timezone.utc)
        if received_at <= previous_last_seen:
            return

    client.last_seen = received_at
    if agent_version is not None:
        client.last_agent_version = agent_version
    if transport_name is not None:
        client.transport_name = transport_name
    if client.liveness_state != LivenessState.ALIVE:
        client.liveness_state = LivenessState.ALIVE
        client.degraded_at = None
    client.revision_token = new_uuid()

    payload = {
        "client_id": str(client.client_id),
        "received_at": received_at.isoformat(),
        "agent_version": client.last_agent_version,
        "transport_name": client.transport_name,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientEventTopics.HEARTBEAT,
            payload=payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    return


def set_liveness_state(
        *,
        db_session: DbSession,
        client_id: str,
        liveness_state: LivenessState,
        now: Optional[datetime] = None
    ) -> None:
    """
        Transition a client's ``liveness_state`` and publish
        ``entity.client.liveness_changed``. Idempotent on the same state.

        :param db_session: Active SQLAlchemy session.
        :param client_id: Target client UUID.
        :param liveness_state: New liveness state.
        :param now: Optional evaluation timestamp (defaults to utc_now).

        :returns: None.
        :raises: ClientNotFoundError
    """
    client = _load_client(db_session=db_session, client_id=client_id)

    if client.liveness_state == liveness_state:
        return

    effective_now = now if now is not None else utc_now()
    previous_state = client.liveness_state
    client.liveness_state = liveness_state
    if liveness_state == LivenessState.DEGRADED:
        client.degraded_at = effective_now
    elif liveness_state == LivenessState.ALIVE:
        client.degraded_at = None
    client.revision_token = new_uuid()

    payload = {
        "client_id": str(client.client_id),
        "previous_state": previous_state.value,
        "new_state": liveness_state.value,
        "changed_at": effective_now.isoformat(),
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientEventTopics.LIVENESS_CHANGED,
            payload=payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    return


def update_attributes(
        *,
        db_session: DbSession,
        client_id: str,
        updates: List[AttributeUpdate],
        expected_revision_token: Optional[str] = None
    ) -> List[str]:
    """
        Validate and upsert one or more client attributes. All updates
        apply as a single transaction; any validation error aborts the
        whole batch per spec.

        :param db_session: Active SQLAlchemy session.
        :param client_id: Target client UUID.
        :param updates: Batch of :class:`AttributeUpdate` values.
        :param expected_revision_token: If supplied and the current
                                         ``revision_token`` does not
                                         match, the call aborts.

        :returns: List of kind names that were written.
        :raises: ClientNotFoundError, UnknownAttributeKindError,
                 InvalidAttributeValueError
    """
    client = _load_client(db_session=db_session, client_id=client_id)
    if expected_revision_token is not None:
        if client.revision_token != expected_revision_token:
            err_msg_lines = ["Client attribute update aborted — revision_token mismatch."]
            err_msg_lines.append("CLIENT_ID: {}".format(client_id))
            err_msg_lines.append("EXPECTED: {}".format(expected_revision_token))
            err_msg_lines.append("ACTUAL: {}".format(client.revision_token))
            err_msg = os.linesep.join(err_msg_lines)
            raise InvalidAttributeValueError(err_msg) from None

    kinds = _load_attribute_kinds()
    for update in updates:
        pack = kinds.get(update.kind, None)
        if pack is None:
            err_msg_lines = ["Unknown client attribute kind."]
            err_msg_lines.append("KIND: {}".format(update.kind))
            err_msg_lines.append("REGISTERED: {}".format(sorted(kinds.keys())))
            err_msg = os.linesep.join(err_msg_lines)
            raise UnknownAttributeKindError(err_msg) from None
        _validate_attribute_value(kind=update.kind, value=update.value, pack=pack)

    now = utc_now()
    written: List[str] = []
    for update in updates:
        row = (
            db_session.query(ClientAttribute)
            .filter(ClientAttribute.client_id == client_id)
            .filter(ClientAttribute.kind == update.kind)
            .first()
        )
        if row is None:
            row = ClientAttribute(
                attribute_id=new_uuid(),
                client_id=client_id,
                kind=update.kind,
                value_json=update.value,
                updated_at=now,
            )
            db_session.add(row)
        else:
            row.value_json = update.value
            row.updated_at = now
        written.append(update.kind)

    client.revision_token = new_uuid()
    db_session.flush()

    payload = {
        "client_id": str(client_id),
        "kinds": written,
        "updated_at": now.isoformat(),
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ClientEventTopics.ATTRIBUTES_CHANGED,
            payload=payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    return written


def _build_view(*, client: Client, attributes: List[ClientAttribute]) -> ClientView:
    attr_map: Dict[str, Any] = {}
    for attr in attributes:
        attr_map[attr.kind] = attr.value_json

    rtnval = ClientView(
        client_id=str(client.client_id),
        project_id=str(client.project_id),
        pod_name=client.pod_name,
        status=client.status,
        liveness_state=client.liveness_state,
        enrolled_at_iso=client.enrolled_at.isoformat() if client.enrolled_at is not None else "",
        last_seen_iso=client.last_seen.isoformat() if client.last_seen is not None else None,
        last_agent_version=client.last_agent_version,
        transport_name=client.transport_name,
        degraded_at_iso=client.degraded_at.isoformat() if client.degraded_at is not None else None,
        revision_token=str(client.revision_token),
        attributes=attr_map,
    )
    return rtnval


def get_client(*, db_session: DbSession, client_id: str) -> ClientView:
    """
        Return the :class:`ClientView` for ``client_id``.

        :raises: ClientNotFoundError
    """
    client = _load_client(db_session=db_session, client_id=client_id)
    attrs = (
        db_session.query(ClientAttribute)
        .filter(ClientAttribute.client_id == client_id)
        .all()
    )
    rtnval = _build_view(client=client, attributes=attrs)
    return rtnval


def get_client_by_scope(
        *,
        db_session: DbSession,
        project_id: str,
        pod_name: str
    ) -> ClientView:
    """
        Return the :class:`ClientView` for the ``(project_id, pod_name)``
        pair: the client holding the scope, else the most recently
        enrolled revoked one.

        :raises: ClientNotFoundError
    """
    client = find_scope_holder(
        db_session=db_session, project_id=project_id, pod_name=pod_name,
    )
    if client is None:
        client = (
            db_session.query(Client)
            .filter(Client.project_id == project_id)
            .filter(Client.pod_name == pod_name)
            .order_by(Client.enrolled_at.desc())
            .first()
        )
    if client is None:
        err_msg_lines = ["Client not found for scope."]
        err_msg_lines.append("PROJECT_ID: {}".format(project_id))
        err_msg_lines.append("POD_NAME: {}".format(pod_name))
        err_msg = os.linesep.join(err_msg_lines)
        raise ClientNotFoundError(err_msg) from None

    attrs = (
        db_session.query(ClientAttribute)
        .filter(ClientAttribute.client_id == client.client_id)
        .all()
    )
    rtnval = _build_view(client=client, attributes=attrs)
    return rtnval


def list_clients(
        *,
        db_session: DbSession,
        project_id: Optional[str] = None,
        status: Optional[ClientStatus] = None,
        liveness_state: Optional[LivenessState] = None
    ) -> List[ClientView]:
    """
        Return clients matching the supplied filters.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Optional project filter.
        :param status: Optional status filter.
        :param liveness_state: Optional liveness filter.

        :returns: List of :class:`ClientView` ordered by enrolled_at.
    """
    query = db_session.query(Client)
    if project_id is not None:
        query = query.filter(Client.project_id == project_id)
    if status is not None:
        query = query.filter(Client.status == status)
    if liveness_state is not None:
        query = query.filter(Client.liveness_state == liveness_state)

    clients = query.order_by(Client.enrolled_at.asc()).all()
    client_ids = [c.client_id for c in clients]

    attrs_by_client: Dict[str, List[ClientAttribute]] = {}
    if len(client_ids) > 0:
        attr_rows = (
            db_session.query(ClientAttribute)
            .filter(ClientAttribute.client_id.in_(client_ids))
            .all()
        )
        for row in attr_rows:
            bucket = attrs_by_client.setdefault(str(row.client_id), [])
            bucket.append(row)

    rtnval: List[ClientView] = []
    for client in clients:
        attrs = attrs_by_client.get(str(client.client_id), [])
        rtnval.append(_build_view(client=client, attributes=attrs))
    return rtnval
