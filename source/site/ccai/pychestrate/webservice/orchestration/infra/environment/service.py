"""
.. module:: orchestration.infra.environment.service
    :synopsis: Environment-registry facade — declare / state ops / read.

M1 ships:

* :func:`declare_environment` — resolve kind → validate attrs
  → reject duplicate (project, kind, name) → persist row +
  emit DECLARED.
* :func:`update_attrs` — re-validates against the kind, emits
  UPDATED. Disallowed on archived / destroyed rows.
* :func:`freeze_environment` / :func:`unfreeze_environment` —
  toggle the FROZEN state with operator-supplied reason;
  ledger row + emit.
* :func:`archive_environment` / :func:`mark_destroyed` —
  terminal-state transitions.
* :func:`record_apply` — called by the M2 infra orchestrator
  after a successful apply; stamps ``last_applied_run_id`` +
  ``last_output_digest_sha256`` + ``last_applied_at`` and
  appends the APPLIED ledger row.
* Read helpers.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.orchestration.infra.environment import (
    repository,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.errors import (
    EnvironmentAttrsInvalidError,
    EnvironmentKindUnknownError,
    EnvironmentNameConflictError,
    EnvironmentNotFoundError,
    EnvironmentStateError,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.events import (
    EnvironmentEventTopics,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.factories.kind_protocol import (
    EnvironmentKindProtocol,
)
from ccai.pychestrate.webservice.orchestration.infra.environment.models import (
    Environment,
    EnvironmentEventKind,
    EnvironmentState,
)


ENVIRONMENT_KIND_PROTOCOL: str = "environment_kind"
LIST_ENVIRONMENTS_DEFAULT_LIMIT: int = 100
TERMINAL_STATES: Tuple[EnvironmentState, ...] = (
    EnvironmentState.ARCHIVED,
    EnvironmentState.DESTROYED,
)


@dataclass(frozen=True)
class EnvironmentDeclareInputs:
    """
        Caller-supplied environment declaration.
    """
    name: str
    kind_name: str
    attrs: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EnvironmentView:
    """
        Caller-facing read-model.
    """
    environment_id: str
    project_id: str
    kind_name: str
    name: str
    state: EnvironmentState
    attrs: Mapping[str, Any] = field(default_factory=dict)
    frozen_by: Optional[str] = None
    frozen_reason: Optional[str] = None
    frozen_at: Optional[datetime] = None
    last_applied_run_id: Optional[str] = None
    last_output_digest_sha256: str = ""
    last_applied_at: Optional[datetime] = None
    archived_reason: Optional[str] = None
    archived_at: Optional[datetime] = None
    destroyed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


def declare_environment(
        *,
        db_session: DbSession,
        project_id: str,
        inputs: EnvironmentDeclareInputs,
        actor_id: Optional[str] = None
    ) -> EnvironmentView:
    """
        Resolve the kind, validate attrs, reject duplicate
        (project, kind, name), persist + emit DECLARED.

        :raises: EnvironmentKindUnknownError,
                 EnvironmentAttrsInvalidError,
                 EnvironmentNameConflictError.
    """
    if inputs.name is None or len(inputs.name) == 0:
        err_lines = ["EnvironmentDeclareInputs.name must be non-empty."]
        err_msg = os.linesep.join(err_lines)
        raise EnvironmentAttrsInvalidError(err_msg) from None

    kind_cls = _resolve_kind(kind_name=inputs.kind_name)
    ok, issues = kind_cls.validate_attrs(attrs=inputs.attrs)
    if ok is False:
        err_lines = [
            "Environment attrs failed kind validation: {} issue(s).".format(
                len(issues),
            ),
        ]
        err_lines.append("KIND_NAME: {}".format(inputs.kind_name))
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise EnvironmentAttrsInvalidError(err_msg) from None

    existing = repository.find_by_name(
        db_session=db_session,
        project_id=project_id,
        kind_name=inputs.kind_name,
        name=inputs.name,
    )
    if existing is not None:
        err_lines = ["Environment name already exists in this project + kind."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("KIND_NAME: {}".format(inputs.kind_name))
        err_lines.append("NAME: {}".format(inputs.name))
        err_msg = os.linesep.join(err_lines)
        raise EnvironmentNameConflictError(err_msg) from None

    now = utc_now()
    row = repository.insert_environment(
        db_session=db_session,
        project_id=project_id,
        kind_name=inputs.kind_name,
        name=inputs.name,
        attrs=dict(inputs.attrs),
        created_at=now,
    )
    repository.insert_history_entry(
        db_session=db_session,
        environment_id=str(row.environment_id),
        event_kind=EnvironmentEventKind.DECLARED,
        actor_id=actor_id,
        run_id=None,
        payload={"name": inputs.name, "kind_name": inputs.kind_name},
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=EnvironmentEventTopics.DECLARED,
            payload={
                "environment_id": str(row.environment_id),
                "project_id": project_id,
                "kind_name": inputs.kind_name,
                "name": inputs.name,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def update_attrs(
        *,
        db_session: DbSession,
        environment_id: str,
        new_attrs: Mapping[str, Any],
        actor_id: Optional[str] = None
    ) -> EnvironmentView:
    """
        Re-validate against the kind, persist new attrs, emit
        UPDATED.

        :raises: EnvironmentNotFoundError,
                 EnvironmentAttrsInvalidError,
                 EnvironmentStateError.
    """
    row = repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if row is None:
        _raise_not_found(environment_id=environment_id)

    if row.state in TERMINAL_STATES:
        err_lines = ["Cannot update attrs on a terminal environment."]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_lines.append("STATE: {}".format(row.state.value))
        err_msg = os.linesep.join(err_lines)
        raise EnvironmentStateError(err_msg) from None

    kind_cls = _resolve_kind(kind_name=row.kind_name)
    ok, issues = kind_cls.validate_attrs(attrs=new_attrs)
    if ok is False:
        err_lines = [
            "Updated attrs failed kind validation: {} issue(s).".format(
                len(issues),
            ),
        ]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise EnvironmentAttrsInvalidError(err_msg) from None

    now = utc_now()
    row.attrs = dict(new_attrs)
    row.updated_at = now
    db_session.flush()
    repository.insert_history_entry(
        db_session=db_session,
        environment_id=str(row.environment_id),
        event_kind=EnvironmentEventKind.UPDATED,
        actor_id=actor_id,
        run_id=None,
        payload={"updated": True},
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=EnvironmentEventTopics.UPDATED,
            payload={
                "environment_id": str(row.environment_id),
                "project_id": str(row.project_id),
                "kind_name": row.kind_name,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def freeze_environment(
        *,
        db_session: DbSession,
        environment_id: str,
        reason: str,
        actor_id: Optional[str] = None
    ) -> EnvironmentView:
    """
        Move the env to FROZEN. Idempotent on already-FROZEN.

        :raises: EnvironmentNotFoundError,
                 EnvironmentStateError.
    """
    row = _require_active_or_frozen(
        db_session=db_session, environment_id=environment_id,
    )
    if row.state == EnvironmentState.FROZEN:
        rtnval = _to_view(row=row)
        return rtnval

    now = utc_now()
    row.state = EnvironmentState.FROZEN
    row.frozen_by = actor_id
    row.frozen_reason = reason
    row.frozen_at = now
    row.updated_at = now
    db_session.flush()
    repository.insert_history_entry(
        db_session=db_session,
        environment_id=str(row.environment_id),
        event_kind=EnvironmentEventKind.FROZEN,
        actor_id=actor_id,
        run_id=None,
        payload={"reason": reason},
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=EnvironmentEventTopics.FROZEN,
            payload={
                "environment_id": str(row.environment_id),
                "actor_id": actor_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def unfreeze_environment(
        *,
        db_session: DbSession,
        environment_id: str,
        reason: str,
        actor_id: Optional[str] = None
    ) -> EnvironmentView:
    """
        Move FROZEN → ACTIVE. Idempotent on already-ACTIVE.

        :raises: EnvironmentNotFoundError,
                 EnvironmentStateError.
    """
    row = _require_active_or_frozen(
        db_session=db_session, environment_id=environment_id,
    )
    if row.state == EnvironmentState.ACTIVE:
        rtnval = _to_view(row=row)
        return rtnval

    now = utc_now()
    row.state = EnvironmentState.ACTIVE
    row.frozen_by = None
    row.frozen_reason = None
    row.frozen_at = None
    row.updated_at = now
    db_session.flush()
    repository.insert_history_entry(
        db_session=db_session,
        environment_id=str(row.environment_id),
        event_kind=EnvironmentEventKind.UNFROZEN,
        actor_id=actor_id,
        run_id=None,
        payload={"reason": reason},
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=EnvironmentEventTopics.UNFROZEN,
            payload={
                "environment_id": str(row.environment_id),
                "actor_id": actor_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def archive_environment(
        *,
        db_session: DbSession,
        environment_id: str,
        reason: str,
        actor_id: Optional[str] = None
    ) -> EnvironmentView:
    """
        Move to ARCHIVED. Idempotent on already-ARCHIVED.

        :raises: EnvironmentNotFoundError,
                 EnvironmentStateError when the env is
                 destroyed.
    """
    row = repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if row is None:
        _raise_not_found(environment_id=environment_id)
    if row.state == EnvironmentState.DESTROYED:
        err_lines = ["Cannot archive a destroyed environment."]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_msg = os.linesep.join(err_lines)
        raise EnvironmentStateError(err_msg) from None
    if row.state == EnvironmentState.ARCHIVED:
        rtnval = _to_view(row=row)
        return rtnval

    now = utc_now()
    row.state = EnvironmentState.ARCHIVED
    row.archived_reason = reason
    row.archived_at = now
    row.updated_at = now
    db_session.flush()
    repository.insert_history_entry(
        db_session=db_session,
        environment_id=str(row.environment_id),
        event_kind=EnvironmentEventKind.ARCHIVED,
        actor_id=actor_id,
        run_id=None,
        payload={"reason": reason},
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=EnvironmentEventTopics.ARCHIVED,
            payload={
                "environment_id": str(row.environment_id),
                "actor_id": actor_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def mark_destroyed(
        *,
        db_session: DbSession,
        environment_id: str,
        actor_id: Optional[str] = None,
        run_id: Optional[str] = None,
        reason: str = ""
    ) -> EnvironmentView:
    """
        Mark the env DESTROYED. Idempotent on already-DESTROYED.
        Called by the M2 infra orchestrator when a destroy run
        completes.

        :raises: EnvironmentNotFoundError.
    """
    row = repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if row is None:
        _raise_not_found(environment_id=environment_id)
    if row.state == EnvironmentState.DESTROYED:
        rtnval = _to_view(row=row)
        return rtnval

    now = utc_now()
    row.state = EnvironmentState.DESTROYED
    row.destroyed_at = now
    row.updated_at = now
    db_session.flush()
    repository.insert_history_entry(
        db_session=db_session,
        environment_id=str(row.environment_id),
        event_kind=EnvironmentEventKind.DESTROYED,
        actor_id=actor_id,
        run_id=run_id,
        payload={"reason": reason},
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=EnvironmentEventTopics.DESTROYED,
            payload={
                "environment_id": str(row.environment_id),
                "actor_id": actor_id,
                "run_id": run_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def record_apply(
        *,
        db_session: DbSession,
        environment_id: str,
        run_id: str,
        output_digest_sha256: str,
        actor_id: Optional[str] = None
    ) -> EnvironmentView:
    """
        Stamp the env with the latest applied run id + output
        digest + timestamp; append the APPLIED ledger row.

        :raises: EnvironmentNotFoundError,
                 EnvironmentStateError when the env is
                 archived / destroyed.
    """
    row = repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if row is None:
        _raise_not_found(environment_id=environment_id)
    if row.state in TERMINAL_STATES:
        err_lines = ["Cannot record_apply against a terminal environment."]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_lines.append("STATE: {}".format(row.state.value))
        err_msg = os.linesep.join(err_lines)
        raise EnvironmentStateError(err_msg) from None

    now = utc_now()
    row.last_applied_run_id = run_id
    row.last_output_digest_sha256 = output_digest_sha256
    row.last_applied_at = now
    row.updated_at = now
    db_session.flush()
    repository.insert_history_entry(
        db_session=db_session,
        environment_id=str(row.environment_id),
        event_kind=EnvironmentEventKind.APPLIED,
        actor_id=actor_id,
        run_id=run_id,
        payload={"output_digest_sha256": output_digest_sha256},
        at_ts=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=EnvironmentEventTopics.APPLIED,
            payload={
                "environment_id": str(row.environment_id),
                "run_id": run_id,
                "output_digest_sha256": output_digest_sha256,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def get_environment(
        *,
        db_session: DbSession,
        environment_id: str
    ) -> EnvironmentView:
    """
        Read by id.

        :raises: EnvironmentNotFoundError on miss.
    """
    row = repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if row is None:
        _raise_not_found(environment_id=environment_id)
    rtnval = _to_view(row=row)
    return rtnval


def list_environments(
        *,
        db_session: DbSession,
        project_id: str,
        kind_name: Optional[str] = None,
        state: Optional[EnvironmentState] = None,
        limit: int = LIST_ENVIRONMENTS_DEFAULT_LIMIT
    ) -> List[EnvironmentView]:
    """
        Filter by project + optional kind / state.
    """
    rows = repository.list_environments(
        db_session=db_session,
        project_id=project_id,
        kind_name=kind_name,
        state=state,
        limit=limit,
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def _resolve_kind(*, kind_name: str) -> Type[EnvironmentKindProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=ENVIRONMENT_KIND_PROTOCOL,
    )
    for impl in candidates:
        if impl.kind_name() == kind_name:
            return impl
    err_lines = ["No registered environment_kind for name."]
    err_lines.append("KIND_NAME: {}".format(kind_name))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.kind_name() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise EnvironmentKindUnknownError(err_msg) from None


def _require_active_or_frozen(
        *, db_session: DbSession, environment_id: str
    ) -> Environment:
    row = repository.find_by_id(
        db_session=db_session, environment_id=environment_id,
    )
    if row is None:
        _raise_not_found(environment_id=environment_id)
    if row.state in TERMINAL_STATES:
        err_lines = [
            "Operation not allowed on terminal environment.",
        ]
        err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
        err_lines.append("STATE: {}".format(row.state.value))
        err_msg = os.linesep.join(err_lines)
        raise EnvironmentStateError(err_msg) from None
    return row


def _raise_not_found(*, environment_id: str) -> None:
    err_lines = ["Environment not found."]
    err_lines.append("ENVIRONMENT_ID: {}".format(environment_id))
    err_msg = os.linesep.join(err_lines)
    raise EnvironmentNotFoundError(err_msg) from None


def _to_view(*, row: Environment) -> EnvironmentView:
    rtnval = EnvironmentView(
        environment_id=str(row.environment_id),
        project_id=str(row.project_id),
        kind_name=row.kind_name,
        name=row.name,
        state=row.state,
        attrs=dict(row.attrs or {}),
        frozen_by=(
            str(row.frozen_by) if row.frozen_by is not None else None
        ),
        frozen_reason=row.frozen_reason,
        frozen_at=row.frozen_at,
        last_applied_run_id=(
            str(row.last_applied_run_id)
            if row.last_applied_run_id is not None
            else None
        ),
        last_output_digest_sha256=row.last_output_digest_sha256,
        last_applied_at=row.last_applied_at,
        archived_reason=row.archived_reason,
        archived_at=row.archived_at,
        destroyed_at=row.destroyed_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval
