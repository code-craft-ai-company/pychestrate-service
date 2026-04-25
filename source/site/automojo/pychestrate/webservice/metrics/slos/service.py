"""
.. module:: metrics.slos.service
    :synopsis: SLO-views facade — create / read / delete / status.

M1 ships:

* :func:`create_slo` — UNIQUE per project; target clamped to
  [0.0, 1.0]; window_seconds positive; kind config validated.
* :func:`get_slo` / :func:`list_slos_for_project`.
* :func:`delete_slo` — cascades the burn-rate-state row via
  FK; idempotent on miss.
* :func:`compute_status` — delegate to the kind's ``compute``,
  return :class:`SLOStatus`. Emits STATUS_COMPUTED +
  BUDGET_DEPLETED when the achieved ratio drops past target.
* :func:`list_slo_kinds`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, List, Mapping, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.metrics.slos import repository
from automojo.pychestrate.webservice.metrics.slos.errors import (
    SLOConfigInvalidError,
    SLOConflictError,
    SLOKindUnknownError,
    SLONotFoundError,
)
from automojo.pychestrate.webservice.metrics.slos.events import (
    SLOEventTopics,
)
from automojo.pychestrate.webservice.metrics.slos.factories.kind_protocol import (
    SLODefinitionProtocol,
    SLOKindRecord,
)
from automojo.pychestrate.webservice.metrics.slos.models import (
    SLO,
    SLOBurnRateState,
)


SLO_DEFINITION_KIND_PROTOCOL: str = "slo_definition_kind"
DEFAULT_WINDOW_SECONDS: int = 30 * 24 * 60 * 60  # 30 days


@dataclass(frozen=True)
class SLOView:
    """
        Caller-facing SLO read-model.
    """
    slo_id: str
    project_id: str
    name: str
    description: str
    kind: str
    target: float
    window_seconds: int
    definition_config: Mapping[str, Any]
    default_notification_route_key: Optional[str]
    auto_attach_burn_rate_alerts: bool
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class SLOStatus:
    """
        Caller-facing SLO status read-model.

        :param achieved_ratio: ``[0.0, 1.0]`` or ``None`` when
                               there were no observations in
                               the window.
        :param error_budget_remaining_ratio: ``[0.0, 1.0]`` —
                                             how much of the
                                             allowed error
                                             budget is left;
                                             ``None`` when
                                             ``achieved_ratio``
                                             is None.
        :param target: SLO target.
        :param window_start, window_end: Window bounds.
        :param good_count, total_count: Counts surfaced from
                                        the kind's compute.
        :param breaching: True iff
                          ``achieved_ratio < target``.
        :param reason: Human-readable explanation.
    """
    slo_id: str
    achieved_ratio: Optional[float]
    error_budget_remaining_ratio: Optional[float]
    target: float
    window_start: datetime
    window_end: datetime
    good_count: int
    total_count: int
    breaching: bool
    reason: str


@dataclass(frozen=True)
class SLOBurnRateStateView:
    """
        Caller-facing burn-rate-state read-model. M1 returns
        zeros until M2 wires the burn-rate evaluator.
    """
    slo_id: str
    last_fast_burn_rate: float
    last_slow_burn_rate: float
    last_fast_over_since: Optional[datetime]
    last_slow_over_since: Optional[datetime]
    last_evaluated_at: Optional[datetime]


def create_slo(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        kind: str,
        target: float,
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        description: str = "",
        definition_config: Optional[Mapping[str, Any]] = None,
        default_notification_route_key: Optional[str] = None,
        auto_attach_burn_rate_alerts: bool = False
    ) -> SLOView:
    """
        Persist a fresh SLO. UNIQUE on (project, name);
        target clamped to ``[0.0, 1.0]``; window_seconds
        positive; kind config validated.

        :raises: SLOConflictError, SLOKindUnknownError,
                 SLOConfigInvalidError.
    """
    if name is None or len(name) == 0:
        err_lines = ["SLO name must be non-empty."]
        err_msg = os.linesep.join(err_lines)
        raise SLOConfigInvalidError(err_msg) from None
    if target < 0.0 or target > 1.0:
        err_lines = ["SLO target must be in [0.0, 1.0]."]
        err_lines.append("VALUE: {}".format(target))
        err_msg = os.linesep.join(err_lines)
        raise SLOConfigInvalidError(err_msg) from None
    if window_seconds <= 0:
        err_lines = ["SLO window_seconds must be positive."]
        err_lines.append("VALUE: {}".format(window_seconds))
        err_msg = os.linesep.join(err_lines)
        raise SLOConfigInvalidError(err_msg) from None

    existing = repository.find_by_name(
        db_session=db_session, project_id=project_id, name=name,
    )
    if existing is not None:
        err_lines = ["SLO name already exists in project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("NAME: {}".format(name))
        err_msg = os.linesep.join(err_lines)
        raise SLOConflictError(err_msg) from None

    kind_cls = _resolve_kind(kind=kind)
    config = dict(definition_config or {})
    ok, issues = kind_cls.validate_config(config=config)
    if ok is False:
        err_lines = [
            "SLO definition_config failed validation: {} issue(s).".format(
                len(issues),
            ),
        ]
        err_lines.append("KIND: {}".format(kind))
        for index, issue in enumerate(issues):
            err_lines.append("  [{}] {}".format(index + 1, issue))
        err_msg = os.linesep.join(err_lines)
        raise SLOConfigInvalidError(err_msg) from None

    now = utc_now()
    row = repository.insert_slo(
        db_session=db_session,
        project_id=project_id,
        name=name,
        description=description,
        kind=kind,
        target=target,
        window_seconds=window_seconds,
        definition_config=config,
        default_notification_route_key=default_notification_route_key,
        auto_attach_burn_rate_alerts=auto_attach_burn_rate_alerts,
        created_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SLOEventTopics.CREATED,
            payload={
                "slo_id": str(row.slo_id),
                "project_id": project_id,
                "name": name,
                "kind": kind,
                "target": target,
                "window_seconds": window_seconds,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def get_slo(
        *,
        db_session: DbSession,
        slo_id: str
    ) -> SLOView:
    """
        Read by id.

        :raises: SLONotFoundError on miss.
    """
    row = _require_slo(db_session=db_session, slo_id=slo_id)
    rtnval = _to_view(row=row)
    return rtnval


def list_slos_for_project(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[SLOView]:
    """
        Project-scoped list, name ascending.
    """
    rows = repository.list_for_project(
        db_session=db_session, project_id=project_id,
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def delete_slo(
        *,
        db_session: DbSession,
        slo_id: str
    ) -> bool:
    """
        Idempotent delete. Returns ``True`` when a row was
        deleted; the FK CASCADE drops the burn-rate-state row
        in the same transaction.
    """
    row = repository.find_by_id(
        db_session=db_session, slo_id=slo_id,
    )
    if row is None:
        return False
    project_id = str(row.project_id)
    repository.delete_slo_row(db_session=db_session, row=row)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SLOEventTopics.DELETED,
            payload={
                "slo_id": slo_id,
                "project_id": project_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return True


def compute_status(
        *,
        db_session: DbSession,
        slo_id: str
    ) -> SLOStatus:
    """
        Compute the current achieved ratio + error-budget
        remaining. Emits STATUS_COMPUTED on every call and
        BUDGET_DEPLETED when the achieved ratio is below the
        target.

        :raises: SLONotFoundError on miss.
    """
    row = _require_slo(db_session=db_session, slo_id=slo_id)
    kind_cls = _resolve_kind(kind=row.kind)
    outcome = kind_cls.compute(
        db_session=db_session,
        project_id=str(row.project_id),
        config=dict(row.definition_config or {}),
        window_seconds=row.window_seconds,
    )
    now = utc_now()
    window_start = now - timedelta(seconds=row.window_seconds)

    achieved = outcome.achieved_ratio
    if achieved is None:
        budget_remaining: Optional[float] = None
        breaching = False
    else:
        # error budget is 1 - target. budget_remaining_ratio =
        # max(0, achieved - target) / (1 - target) clamped to
        # [0, 1] for the typical 0 < target < 1 case. When
        # target == 1.0 the budget_remaining tracks
        # achieved_ratio directly to avoid division by zero.
        if row.target >= 1.0:
            budget_remaining = achieved
        else:
            error_allowance = 1.0 - row.target
            achieved_minus_target = achieved - row.target
            if achieved_minus_target <= 0.0:
                budget_remaining = 0.0
            else:
                ratio = achieved_minus_target / error_allowance
                if ratio > 1.0:
                    budget_remaining = 1.0
                else:
                    budget_remaining = ratio
        breaching = (achieved < row.target)

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SLOEventTopics.STATUS_COMPUTED,
            payload={
                "slo_id": str(row.slo_id),
                "project_id": str(row.project_id),
                "achieved_ratio": achieved,
                "target": row.target,
                "good_count": outcome.good_count,
                "total_count": outcome.total_count,
                "breaching": breaching,
            },
            source_event_id=new_uuid(),
        ),
    )
    if breaching is True:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=SLOEventTopics.BUDGET_DEPLETED,
                payload={
                    "slo_id": str(row.slo_id),
                    "project_id": str(row.project_id),
                    "achieved_ratio": achieved,
                    "target": row.target,
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()

    rtnval = SLOStatus(
        slo_id=str(row.slo_id),
        achieved_ratio=achieved,
        error_budget_remaining_ratio=budget_remaining,
        target=row.target,
        window_start=window_start,
        window_end=now,
        good_count=outcome.good_count,
        total_count=outcome.total_count,
        breaching=breaching,
        reason=outcome.reason,
    )
    return rtnval


def list_slo_kinds() -> Tuple[SLOKindRecord, ...]:
    """
        Enumerate registered SLO-kind records.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=SLO_DEFINITION_KIND_PROTOCOL,
    )
    rtnval = tuple(impl.record() for impl in candidates)
    return rtnval


def _resolve_kind(*, kind: str) -> Type[SLODefinitionProtocol]:
    candidates = list_factory_implementations(
        factory_protocol_name=SLO_DEFINITION_KIND_PROTOCOL,
    )
    for impl in candidates:
        if impl.kind_name() == kind:
            return impl
    err_lines = ["No registered slo_definition_kind for name."]
    err_lines.append("KIND: {}".format(kind))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.kind_name() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise SLOKindUnknownError(err_msg) from None


def _require_slo(*, db_session: DbSession, slo_id: str) -> SLO:
    row = repository.find_by_id(db_session=db_session, slo_id=slo_id)
    if row is None:
        err_lines = ["SLO not found."]
        err_lines.append("SLO_ID: {}".format(slo_id))
        err_msg = os.linesep.join(err_lines)
        raise SLONotFoundError(err_msg) from None
    return row


def _to_view(*, row: SLO) -> SLOView:
    rtnval = SLOView(
        slo_id=str(row.slo_id),
        project_id=str(row.project_id),
        name=row.name,
        description=row.description,
        kind=row.kind,
        target=row.target,
        window_seconds=row.window_seconds,
        definition_config=dict(row.definition_config or {}),
        default_notification_route_key=row.default_notification_route_key,
        auto_attach_burn_rate_alerts=row.auto_attach_burn_rate_alerts,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval
