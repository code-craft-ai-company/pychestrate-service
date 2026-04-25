"""
.. module:: maintenance.service
    :synopsis: Maintenance-mode facade — set / clear / read.

M1 ships:

* :func:`set_scope_mode` — persist + audit + in-memory cache
  + emit MODE_CHANGED.
* :func:`clear_scope_mode` — persist (mode=active) + audit +
  drop from cache + emit MODE_CLEARED.
* :func:`get_scope_mode` / :func:`get_effective_mode` /
  :func:`list_active_scopes` — read helpers.
* :func:`list_audit_for_scope` — read every audit row for a
  scope newest-first.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.maintenance import repository
from automojo.pychestrate.webservice.maintenance.errors import (
    MaintenanceScopeInvalidError,
    MaintenanceScopeNotFoundError,
)
from automojo.pychestrate.webservice.maintenance.events import (
    MaintenanceEventTopics,
)
from automojo.pychestrate.webservice.maintenance.gate import (
    MaintenanceMode,
    get_gate,
)
from automojo.pychestrate.webservice.maintenance.models import (
    MaintenanceModeAudit,
    MaintenanceModeRow,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


SERVICE_SCOPE: str = "service"
PROJECT_SCOPE_PREFIX: str = "project:"


@dataclass(frozen=True)
class MaintenanceScopeView:
    """
        Caller-facing scope read-model.
    """
    scope: str
    mode: MaintenanceMode
    reason: str
    ends_at: Optional[datetime]
    changed_at: datetime
    changed_by: Optional[str]
    version: int


@dataclass(frozen=True)
class EffectiveModeView:
    """
        Caller-facing effective-mode read-model — the gate's
        verdict for a request.
    """
    mode: MaintenanceMode
    contributing_scopes: Tuple[str, ...] = ()


@dataclass(frozen=True)
class MaintenanceAuditView:
    """
        Caller-facing audit read-model.
    """
    audit_id: str
    scope: str
    from_mode: MaintenanceMode
    to_mode: MaintenanceMode
    reason: str
    ends_at: Optional[datetime]
    actor_user_id: Optional[str]
    changed_at: datetime


def set_scope_mode(
        *,
        db_session: DbSession,
        scope: str,
        mode: MaintenanceMode,
        reason: str,
        ends_at: Optional[datetime] = None,
        actor_id: Optional[str] = None
    ) -> MaintenanceScopeView:
    """
        Persist + audit + in-memory cache the new mode for a
        scope. Emits :data:`MaintenanceEventTopics.MODE_CHANGED`
        plus :data:`MaintenanceEventTopics.DRAIN_STARTED` when
        the transition enters DRAINING. Idempotent on
        no-change writes.

        :raises: MaintenanceScopeInvalidError on a malformed
                 scope (must be ``"service"`` or
                 ``"project:<slug>"``).
    """
    _validate_scope(scope=scope)
    if mode == MaintenanceMode.ACTIVE:
        # ACTIVE is the default and does NOT belong on the
        # ledger via this entry-point — :func:`clear_scope_mode`
        # owns the active-restoration path so it can emit the
        # right event topic.
        rtnval = clear_scope_mode(
            db_session=db_session, scope=scope, reason=reason,
            actor_id=actor_id,
        )
        return rtnval

    now = utc_now()
    existing = repository.find_mode_row(
        db_session=db_session, scope=scope,
    )
    from_mode = (
        MaintenanceMode(existing.mode) if existing is not None
        else MaintenanceMode.ACTIVE
    )

    if existing is not None and existing.mode == mode.value:
        # No-op — keep the cache fresh and exit without
        # appending a redundant ledger row or re-emitting.
        get_gate().set_mode_in_memory(scope=scope, mode=mode)
        rtnval = _row_to_view(row=existing)
        return rtnval

    row = repository.upsert_mode_row(
        db_session=db_session,
        scope=scope,
        mode=mode.value,
        reason=reason,
        ends_at=ends_at,
        actor_id=actor_id,
        now=now,
    )
    repository.insert_audit_row(
        db_session=db_session,
        scope=scope,
        from_mode=from_mode.value,
        to_mode=mode.value,
        reason=reason,
        ends_at=ends_at,
        actor_id=actor_id,
        changed_at=now,
    )
    get_gate().set_mode_in_memory(scope=scope, mode=mode)

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=MaintenanceEventTopics.MODE_CHANGED,
            payload={
                "scope": scope,
                "from_mode": from_mode.value,
                "to_mode": mode.value,
                "reason": reason,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    if mode == MaintenanceMode.DRAINING and from_mode != MaintenanceMode.DRAINING:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=MaintenanceEventTopics.DRAIN_STARTED,
                payload={"scope": scope, "reason": reason},
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()
    rtnval = _row_to_view(row=row)
    return rtnval


def clear_scope_mode(
        *,
        db_session: DbSession,
        scope: str,
        reason: str,
        actor_id: Optional[str] = None
    ) -> MaintenanceScopeView:
    """
        Restore a scope to ``ACTIVE``. Persists ``mode=active``
        on the row, drops the cache entry, audits the
        transition, and emits MODE_CLEARED + DRAIN_ENDED when
        the prior mode was DRAINING. Idempotent on already-
        active scopes.
    """
    _validate_scope(scope=scope)
    existing = repository.find_mode_row(
        db_session=db_session, scope=scope,
    )
    if existing is None or existing.mode == MaintenanceMode.ACTIVE.value:
        get_gate().set_mode_in_memory(
            scope=scope, mode=MaintenanceMode.ACTIVE,
        )
        if existing is not None:
            rtnval = _row_to_view(row=existing)
            return rtnval
        # Synthesize an active view so callers always get a
        # well-formed read-model.
        rtnval = MaintenanceScopeView(
            scope=scope,
            mode=MaintenanceMode.ACTIVE,
            reason="",
            ends_at=None,
            changed_at=utc_now(),
            changed_by=None,
            version=0,
        )
        return rtnval

    now = utc_now()
    from_mode = MaintenanceMode(existing.mode)
    row = repository.upsert_mode_row(
        db_session=db_session,
        scope=scope,
        mode=MaintenanceMode.ACTIVE.value,
        reason=reason,
        ends_at=None,
        actor_id=actor_id,
        now=now,
    )
    repository.insert_audit_row(
        db_session=db_session,
        scope=scope,
        from_mode=from_mode.value,
        to_mode=MaintenanceMode.ACTIVE.value,
        reason=reason,
        ends_at=None,
        actor_id=actor_id,
        changed_at=now,
    )
    get_gate().set_mode_in_memory(
        scope=scope, mode=MaintenanceMode.ACTIVE,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=MaintenanceEventTopics.MODE_CLEARED,
            payload={
                "scope": scope,
                "from_mode": from_mode.value,
                "actor_id": actor_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    if from_mode == MaintenanceMode.DRAINING:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=MaintenanceEventTopics.DRAIN_ENDED,
                payload={"scope": scope},
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()
    rtnval = _row_to_view(row=row)
    return rtnval


def get_scope_mode(
        *,
        db_session: DbSession,
        scope: str
    ) -> MaintenanceScopeView:
    """
        Read by scope. Synthesizes an ACTIVE view for scopes
        that were never touched.

        :raises: MaintenanceScopeInvalidError on a malformed
                 scope.
    """
    _validate_scope(scope=scope)
    existing = repository.find_mode_row(
        db_session=db_session, scope=scope,
    )
    if existing is None:
        rtnval = MaintenanceScopeView(
            scope=scope,
            mode=MaintenanceMode.ACTIVE,
            reason="",
            ends_at=None,
            changed_at=utc_now(),
            changed_by=None,
            version=0,
        )
        return rtnval
    rtnval = _row_to_view(row=existing)
    return rtnval


def get_effective_mode(
        *,
        scopes: Iterable[str] = ()
    ) -> EffectiveModeView:
    """
        Return the most-restrictive mode across every supplied
        scope (the global ``"service"`` scope is implicit).
        Cache-only — no DB reads on the hot path.
    """
    gate = get_gate()
    materialized = list(scopes)
    contributing: List[str] = []
    if gate.get_mode_in_memory(scope=SERVICE_SCOPE) != MaintenanceMode.ACTIVE:
        contributing.append(SERVICE_SCOPE)
    for scope in materialized:
        if scope == SERVICE_SCOPE:
            continue
        if gate.get_mode_in_memory(scope=scope) != MaintenanceMode.ACTIVE:
            contributing.append(scope)
    mode = gate.get_effective_mode(scopes=materialized)
    rtnval = EffectiveModeView(
        mode=mode, contributing_scopes=tuple(contributing),
    )
    return rtnval


def list_active_scopes(
        *,
        db_session: DbSession
    ) -> List[MaintenanceScopeView]:
    """
        List every persisted scope whose mode is not
        ``ACTIVE``.
    """
    rows = repository.list_active_rows(db_session=db_session)
    rtnval = [_row_to_view(row=r) for r in rows]
    return rtnval


def list_audit_for_scope(
        *,
        db_session: DbSession,
        scope: str,
        limit: int = 100
    ) -> List[MaintenanceAuditView]:
    """
        Return audit rows for a scope, newest-first.
    """
    _validate_scope(scope=scope)
    rows = repository.list_audit_for_scope(
        db_session=db_session, scope=scope, limit=limit,
    )
    rtnval = [
        MaintenanceAuditView(
            audit_id=str(r.audit_id),
            scope=r.scope,
            from_mode=MaintenanceMode(r.from_mode),
            to_mode=MaintenanceMode(r.to_mode),
            reason=r.reason,
            ends_at=r.ends_at,
            actor_user_id=(
                str(r.actor_user_id) if r.actor_user_id is not None else None
            ),
            changed_at=r.changed_at,
        )
        for r in rows
    ]
    return rtnval


def warm_gate_from_db(
        *,
        db_session: DbSession
    ) -> int:
    """
        Service-start path: load every persisted non-active
        scope into the in-memory gate. Returns the count of
        scopes loaded.
    """
    rows = repository.list_active_rows(db_session=db_session)
    initial = [(row.scope, MaintenanceMode(row.mode)) for row in rows]
    get_gate().warm(initial_modes=initial)
    return len(initial)


def _validate_scope(*, scope: str) -> None:
    if scope is None or len(scope) == 0:
        err_lines = ["Maintenance scope must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise MaintenanceScopeInvalidError(err_msg) from None
    if scope == SERVICE_SCOPE:
        return
    if scope.startswith(PROJECT_SCOPE_PREFIX) and len(scope) > len(PROJECT_SCOPE_PREFIX):
        return
    err_lines = ["Maintenance scope must be 'service' or 'project:<slug>'."]
    err_lines.append("VALUE: {!r}".format(scope))
    err_msg = os.linesep.join(err_lines)
    raise MaintenanceScopeInvalidError(err_msg) from None


def _row_to_view(*, row: MaintenanceModeRow) -> MaintenanceScopeView:
    rtnval = MaintenanceScopeView(
        scope=row.scope,
        mode=MaintenanceMode(row.mode),
        reason=row.reason,
        ends_at=row.ends_at,
        changed_at=row.changed_at,
        changed_by=(
            str(row.changed_by) if row.changed_by is not None else None
        ),
        version=row.version,
    )
    return rtnval
