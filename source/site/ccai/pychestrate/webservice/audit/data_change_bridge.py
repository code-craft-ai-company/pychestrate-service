"""
.. module:: audit.data_change_bridge
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Records the rows a signed-in user changes in the web UI's
               ``core.orm`` stores as audit events.

.. moduleauthor:: Code Craft AI LLC

The web UI's projects, resources, variables and legacy-secrets pages
write the ``core.orm`` tables through the legacy managers. Those
managers take an optional ``audit_logger`` but every builder creates
them without one, and the admin Audit Logs page read a legacy table
nothing wrote to, so none of those actions was ever recorded (audit
ADM-02).

Rather than threading a logger through every manager and builder, this
bridge watches the ORM. Every insert, update and delete of a
``core.orm`` row made through a database session that is *tagged with
an acting user* becomes an ``entity.data.*`` event on the session's
outbox (:mod:`messaging.outbox`). The outbox publishes only after the
transaction commits -- a rolled-back change is never recorded -- and
the audit bus subscriber writes the event into ``audit_records``.

Sessions are tagged by the code that authenticated the request:
:func:`tag_session_actor` is called for the web UI by
``config.routes._resolve_authenticated_request`` and for the REST API
by the session middleware. Untagged sessions (background workers,
startup, tests) are ignored, so the log records what people did, not
what the system did on its own.

What an event carries:

* the table, a readable entity name, the row's primary key and a label
  (its ``name`` / ``display_name`` / ... when it has one);
* for updates, the names of the changed columns, and old / new values
  only for a short list of non-sensitive fields such as ``status`` and
  ``name`` (never values of password, secret, token or value columns);
* the acting user id and client address.

History and log tables, the legacy user mirror (the identity admin
publishes its own user events) and bookkeeping-only updates
(``updated_at``, ``last_activity_at`` ...) are skipped.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import datetime as _datetime
import decimal
import enum
import logging
import threading
import uuid

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import event as sqla_event
from sqlalchemy import inspect as sqla_inspect
from sqlalchemy.orm import object_session

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


_module_logger = logging.getLogger(__name__)


DATA_CREATED_TOPIC: str = "entity.data.created"
DATA_UPDATED_TOPIC: str = "entity.data.updated"
DATA_DELETED_TOPIC: str = "entity.data.deleted"

#: ``Session.info`` keys carrying the acting user and client address.
SESSION_INFO_ACTOR_KEY: str = "pychestrate.audit.actor_user_id"
SESSION_INFO_CLIENT_ADDRESS_KEY: str = "pychestrate.audit.client_address"

#: Tables whose rows are history, logs, bookkeeping, or covered by
#: dedicated audit events -- recording them would only add noise.
_EXCLUDED_TABLES = frozenset((
    "audit_logs",
    "sessions",
    "password_history",
    "password_reset_tokens",
    "user",
    "permissions",
    "system_roles",
    "secret_versions",
    "health_transition_logs",
    "resource_metadata_history",
    "project_channel_history",
    "project_watch_trigger_logs",
    "work_queue",
    "work_packet",
    "build_result",
    "build_byproduct",
    "test_result",
    "test_result_container",
    "project_test_results",
    "project_stage_runs",
))

#: Columns that change as a side effect of other work. An update that
#: touches only these is not recorded.
_BOOKKEEPING_FIELDS = frozenset((
    "updated_at",
    "last_activity_at",
    "last_seen",
    "last_seen_at",
    "last_accessed_at",
    "last_used_at",
    "accessed_at",
    "last_checked_at",
    "last_check_at",
))

#: Fields whose old / new values are safe and useful to record.
_VALUE_SAFE_FIELDS = frozenset((
    "status",
    "state",
    "mode",
    "role",
    "health_status",
    "is_active",
    "enabled",
    "is_enabled",
    "is_archived",
    "archived",
    "name",
    "display_name",
    "priority",
    "version",
))

#: A field whose name contains one of these never has its value
#: recorded, even when listed above.
_SENSITIVE_FIELD_MARKERS = (
    "password",
    "secret",
    "token",
    "encrypted",
    "credential",
    "hash",
    "private",
)

#: Attributes tried, in order, for a row's human-readable label.
_LABEL_ATTRIBUTES = (
    "name",
    "display_name",
    "title",
    "slug",
    "login",
    "label",
    "hostname",
    "ip_address",
    "branch_name",
    "version",
)

_ENTITY_NAMES = {
    "allocations": "allocation",
    "health_check_configs": "health check",
    "ip_allocations": "IP allocation",
    "ip_pools": "IP pool",
    "project_build_specs": "build spec",
    "project_builds": "build",
    "project_calendar_events": "calendar event",
    "project_infra_jobs": "infrastructure job",
    "project_infra_specs": "infrastructure spec",
    "project_members": "project member",
    "project_merge_events": "merge event",
    "project_phase_events": "phase event",
    "project_pipeline_runs": "pipeline run",
    "project_pull_events": "pull event",
    "project_release_artifacts": "release artifact",
    "project_release_branches": "release branch",
    "project_release_channels": "release channel",
    "project_release_events": "release event",
    "project_release_pipelines": "release pipeline",
    "project_release_schedules": "release schedule",
    "project_release_templates": "release template",
    "project_releases": "release",
    "project_repositories": "repository",
    "project_test_jobs": "test job",
    "project_test_specs": "test spec",
    "project_variables": "project variable",
    "project_watches": "watch",
    "projects": "project",
    "reservations": "reservation",
    "resource_pools": "resource pool",
    "resource_tags_def": "tag",
    "resources": "resource",
    "secret_scopes": "secret scope",
    "secrets": "secret",
}

_MAX_TEXT_LENGTH: int = 200

_INSTALL_LOCK = threading.Lock()
_INSTALLED: List[bool] = [False]


# ---------------------------------------------------------------------------
# Session tagging
# ---------------------------------------------------------------------------


def tag_session_actor(
        *,
        db_session: Any,
        actor_user_id: Optional[str],
        client_address: Optional[str] = None
    ) -> None:
    """
        Mark a database session as acting for ``actor_user_id``: rows it
        changes are recorded in the audit log under that user. Called by
        the code that authenticated the request.

        :param db_session: The request's SQLAlchemy session.
        :param actor_user_id: The signed-in user's id (None clears the
                              tag).
        :param client_address: The request's client address, when known.

        :returns: None.
    """
    info = getattr(db_session, "info", None)
    if isinstance(info, dict) is False:
        return
    if actor_user_id is None or len(str(actor_user_id)) == 0:
        info.pop(SESSION_INFO_ACTOR_KEY, None)
        info.pop(SESSION_INFO_CLIENT_ADDRESS_KEY, None)
        return
    info[SESSION_INFO_ACTOR_KEY] = str(actor_user_id)
    if client_address is not None and len(str(client_address)) > 0:
        info[SESSION_INFO_CLIENT_ADDRESS_KEY] = str(client_address)
    return


def session_actor(*, db_session: Any) -> Optional[str]:
    """
        The acting user a session is tagged with, or None.

        :param db_session: SQLAlchemy session.

        :returns: User id string or None.
    """
    info = getattr(db_session, "info", None)
    if isinstance(info, dict) is False:
        return None
    rtnval = info.get(SESSION_INFO_ACTOR_KEY, None)
    return rtnval


def session_client_address(*, db_session: Any) -> Optional[str]:
    """
        The client address a session is tagged with, or None.

        :param db_session: SQLAlchemy session.

        :returns: Address string or None.
    """
    info = getattr(db_session, "info", None)
    if isinstance(info, dict) is False:
        return None
    rtnval = info.get(SESSION_INFO_CLIENT_ADDRESS_KEY, None)
    return rtnval


# ---------------------------------------------------------------------------
# Payload building
# ---------------------------------------------------------------------------


def entity_name_for_table(*, table_name: str) -> str:
    """
        Readable singular name for a ``core.orm`` table.

        :param table_name: The table name.

        :returns: E.g. ``"project"`` for ``projects``.
    """
    known = _ENTITY_NAMES.get(table_name, None)
    if known is not None:
        return known
    words = table_name.replace("_", " ").strip()
    if words.endswith("s") is True and len(words) > 1:
        words = words[:-1]
    rtnval = words
    return rtnval


def _json_safe(value: Any) -> Any:
    """
        A JSON-serializable, bounded form of a column value.

        :param value: Any column value.

        :returns: None / bool / int / float / short string.
    """
    if value is None:
        return None
    if isinstance(value, bool) is True:
        return value
    if isinstance(value, (int, float)) is True:
        return value
    if isinstance(value, enum.Enum) is True:
        rtnval = _json_safe(value.value)
        return rtnval
    if isinstance(value, (_datetime.datetime, _datetime.date)) is True:
        rtnval = value.isoformat()
        return rtnval
    if isinstance(value, (uuid.UUID, decimal.Decimal)) is True:
        rtnval = str(value)
        return rtnval
    if isinstance(value, (bytes, bytearray, memoryview)) is True:
        return "<binary>"
    text = str(value)
    if len(text) > _MAX_TEXT_LENGTH:
        text = text[:_MAX_TEXT_LENGTH] + "..."
    rtnval = text
    return rtnval


def _is_sensitive_field(*, field_name: str) -> bool:
    """
        Whether a field's values must never be recorded.

        :param field_name: Attribute name.

        :returns: True for password / secret / token ... fields.
    """
    lowered = field_name.lower()
    for marker in _SENSITIVE_FIELD_MARKERS:
        if marker in lowered:
            return True
    return False


def _primary_key_text(*, mapper: Any, target: Any) -> str:
    """
        The row's primary key as text (composite keys joined by ``/``).

        :param mapper: The row's mapper.
        :param target: The ORM instance.

        :returns: Primary key text ("" when unavailable).
    """
    try:
        values = mapper.primary_key_from_instance(target)
    except Exception:
        return ""
    parts = [str(_json_safe(value)) for value in values if value is not None]
    rtnval = "/".join(parts)
    return rtnval


def _row_label(*, loaded: Dict[str, Any]) -> Optional[str]:
    """
        The row's human-readable label from its loaded attributes
        (never triggers a load).

        :param loaded: ``InstanceState.dict`` of the row.

        :returns: Label text or None.
    """
    for attribute_name in _LABEL_ATTRIBUTES:
        value = loaded.get(attribute_name, None)
        if value is None:
            continue
        text = _json_safe(value)
        if isinstance(text, str) is True and len(text.strip()) > 0:
            return text
        if isinstance(text, (int, float)) is True:
            rtnval = str(text)
            return rtnval
    return None


def _changed_fields(
        *, mapper: Any, state: Any
    ) -> Tuple[List[str], Dict[str, Dict[str, Any]]]:
    """
        The column attributes an update changed, and the old / new
        values of the safe ones.

        :param mapper: The row's mapper.
        :param state: The row's ``InstanceState``.

        :returns: ``(changed_field_names, {field: {"from", "to"}})``.
    """
    changed: List[str] = []
    changes: Dict[str, Dict[str, Any]] = {}
    for column_attr in mapper.column_attrs:
        key = column_attr.key
        try:
            history = state.attrs[key].history
        except Exception:
            continue
        if history.has_changes() is False:
            continue
        changed.append(key)
        if key in _VALUE_SAFE_FIELDS and _is_sensitive_field(field_name=key) is False:
            old_value = history.deleted[0] if len(history.deleted) > 0 else None
            new_value = history.added[0] if len(history.added) > 0 else None
            changes[key] = {
                "from": _json_safe(old_value),
                "to": _json_safe(new_value),
            }
    changed.sort()
    rtnval = (changed, changes)
    return rtnval


def build_data_change_payload(
        *,
        mapper: Any,
        target: Any,
        operation: str,
        actor_user_id: Optional[str],
        client_address: Optional[str]
    ) -> Optional[Dict[str, Any]]:
    """
        The ``entity.data.*`` payload for one changed row, or None when
        the change is not worth recording (excluded table, bookkeeping
        only).

        :param mapper: The row's mapper.
        :param target: The ORM instance.
        :param operation: ``"created"``, ``"updated"`` or ``"deleted"``.
        :param actor_user_id: Acting user id.
        :param client_address: Client address, when known.

        :returns: Payload dict or None.
    """
    table = getattr(mapper, "local_table", None)
    table_name = getattr(table, "name", None)
    if table_name is None:
        return None
    if table_name in _EXCLUDED_TABLES:
        return None

    state = sqla_inspect(target)
    changed: List[str] = []
    changes: Dict[str, Dict[str, Any]] = {}
    if operation == "updated":
        changed, changes = _changed_fields(mapper=mapper, state=state)
        meaningful = [name for name in changed if name not in _BOOKKEEPING_FIELDS]
        if len(meaningful) == 0:
            return None

    rtnval: Dict[str, Any] = {
        "table": table_name,
        "entity": entity_name_for_table(table_name=table_name),
        "entity_id": _primary_key_text(mapper=mapper, target=target),
        "label": _row_label(loaded=state.dict),
        "actor_user_id": actor_user_id,
        "client_address": client_address,
    }
    if operation == "updated":
        rtnval["changed_fields"] = changed
        rtnval["changes"] = changes
    return rtnval


# ---------------------------------------------------------------------------
# ORM listeners
# ---------------------------------------------------------------------------


_TOPIC_BY_OPERATION = {
    "created": DATA_CREATED_TOPIC,
    "updated": DATA_UPDATED_TOPIC,
    "deleted": DATA_DELETED_TOPIC,
}


def _record(*, mapper: Any, target: Any, operation: str) -> None:
    """
        Stage an ``entity.data.*`` event for one changed row on its
        session's outbox, when the session is tagged with an actor.
        Never raises: auditing must not break the user's action.

        :param mapper: The row's mapper.
        :param target: The ORM instance.
        :param operation: ``"created"``, ``"updated"`` or ``"deleted"``.

        :returns: None.
    """
    try:
        db_session = object_session(target)
        if db_session is None:
            return
        actor_user_id = session_actor(db_session=db_session)
        if actor_user_id is None:
            return
        payload = build_data_change_payload(
            mapper=mapper,
            target=target,
            operation=operation,
            actor_user_id=actor_user_id,
            client_address=session_client_address(db_session=db_session),
        )
        if payload is None:
            return
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=_TOPIC_BY_OPERATION[operation],
                payload=payload,
                source_event_id=new_uuid(),
            ),
        )
    except Exception as xcpt:  # noqa: BLE001 -- never break the write
        _module_logger.warning(
            "pychestrate.audit.data_change.skipped operation=%s error=%s",
            operation, xcpt,
        )
    return


def _after_insert(mapper: Any, connection: Any, target: Any) -> None:
    _record(mapper=mapper, target=target, operation="created")
    return


def _after_update(mapper: Any, connection: Any, target: Any) -> None:
    _record(mapper=mapper, target=target, operation="updated")
    return


def _after_delete(mapper: Any, connection: Any, target: Any) -> None:
    _record(mapper=mapper, target=target, operation="deleted")
    return


def install_data_change_bridge() -> None:
    """
        Attach the insert / update / delete listeners to every
        ``core.orm`` model (idempotent; process-wide).

        :returns: None.
    """
    from ccai.pychestrate.core.orm import PychestrateModelBase  # noqa: E402

    with _INSTALL_LOCK:
        if _INSTALLED[0] is True:
            return
        sqla_event.listen(PychestrateModelBase, "after_insert", _after_insert, propagate=True)
        sqla_event.listen(PychestrateModelBase, "after_update", _after_update, propagate=True)
        sqla_event.listen(PychestrateModelBase, "after_delete", _after_delete, propagate=True)
        _INSTALLED[0] = True
    return


def is_data_change_bridge_installed() -> bool:
    """
        Whether :func:`install_data_change_bridge` has run.

        :returns: True once installed.
    """
    rtnval = _INSTALLED[0]
    return rtnval


__all__ = [
    "DATA_CREATED_TOPIC",
    "DATA_DELETED_TOPIC",
    "DATA_UPDATED_TOPIC",
    "SESSION_INFO_ACTOR_KEY",
    "SESSION_INFO_CLIENT_ADDRESS_KEY",
    "build_data_change_payload",
    "entity_name_for_table",
    "install_data_change_bridge",
    "is_data_change_bridge_installed",
    "session_actor",
    "session_client_address",
    "tag_session_actor",
]
