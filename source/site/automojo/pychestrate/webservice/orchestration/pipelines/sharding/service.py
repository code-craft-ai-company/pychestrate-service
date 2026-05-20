"""
.. module:: orchestration.pipelines.sharding.service
    :synopsis: Sharding facade — expand / get / bind.

M1 ships the synchronous expand surface plus the bookkeeping
helpers that Layer-5 dispatch will call as it materializes
shards into runs:

* :func:`expand_matrix` — resolve a strategy, expand the matrix
  spec, persist the shard-set + shard-spec rows, emit
  ``entity.shard_set.expanded``.
* :func:`bind_shard_to_run` — record the Layer-5 ``run_id`` on
  a freshly dispatched shard and emit ``entity.shard.bound``.
* :func:`get_shard_set` / :func:`list_shards_for_set` — read-side
  helpers used by tests + the M2 reassembly module.

Reassembly + cancellation cascade + the deadline sweep land in
M2 once the Layer-5 run-state mirror lands.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.orchestration.pipelines.sharding import (
    repository,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.errors import (
    ShardSetNotFoundError,
    ShardingStrategyNotFoundError,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.events import (
    ShardingEventTopics,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.expansion import (
    MatrixSpec,
    canonicalize_dimension_values,
    matrix_spec_sha256,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.factories.strategy_protocol import (
    ShardingStrategyProtocol,
)
from automojo.pychestrate.webservice.orchestration.pipelines.sharding.models import (
    ShardSet,
    ShardSetState,
    ShardSpec,
    ShardState,
)


SHARDING_STRATEGY_PROTOCOL: str = "sharding_strategy"
ALLOWED_PARENT_KINDS: Tuple[str, ...] = (
    "test_run", "build_run", "pipeline_stage",
)


@dataclass(frozen=True)
class ExpandAspects:
    """
        Caller-tunable knobs.

        :param fail_fast: Override the strategy's
                          ``should_cancel_on_failure`` flag. M1
                          stores it on the row; M2 reassembly
                          honors it.
        :param allow_partial_success: When True, the M2 reassembly
                                      tolerates failed shards as
                                      long as
                                      ``min_success_fraction`` is
                                      met.
        :param min_success_fraction: Threshold consulted by the M2
                                     partial-success path.
        :param note: Free-form note persisted on the shard set.
    """
    fail_fast: Optional[bool] = None
    allow_partial_success: bool = False
    min_success_fraction: float = 1.0
    note: str = ""


@dataclass(frozen=True)
class ShardSpecView:
    """
        Caller-facing read-model for a single shard.
    """
    shard_set_id: str
    shard_id: str
    parallel_group: str
    sequence_in_group: int
    dimension_values: Dict[str, str] = field(default_factory=dict)
    state: ShardState = ShardState.PENDING
    run_id: Optional[str] = None
    dispatched_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


@dataclass(frozen=True)
class ShardSetView:
    """
        Caller-facing read-model for a shard set.
    """
    shard_set_id: str
    project_id: str
    parent_kind: str
    parent_id: str
    strategy_name: str
    matrix_spec_canonical_sha256: str
    state: ShardSetState
    fail_fast: bool
    allow_partial_success: bool
    min_success_fraction: float
    shard_count: int
    started_at: datetime
    finished_at: Optional[datetime]
    note: str
    shards: Tuple[ShardSpecView, ...] = ()


@dataclass(frozen=True)
class ExpansionPreviewShard:
    """
        One shard of a non-persisted matrix-expansion preview.
    """
    shard_id: str
    parallel_group: str
    sequence_in_group: int
    dimension_values: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExpansionPreview:
    """
        Caller-facing read-model for a non-persisted matrix
        expansion. Computed by :func:`preview_expansion` -- it
        shows how a :class:`MatrixSpec` fans out into concrete
        shards without writing any rows or emitting any events.
    """
    strategy_name: str
    matrix_spec_canonical_sha256: str
    shard_count: int
    shards: Tuple[ExpansionPreviewShard, ...] = ()


def preview_expansion(
        *,
        matrix_spec: MatrixSpec,
        strategy_name: str
    ) -> ExpansionPreview:
    """
        Expand ``matrix_spec`` with the named strategy and return
        the resulting shard set as a pure, non-persisted preview.
        No :class:`ShardSet` / :class:`ShardSpec` rows are written
        and no events are emitted.

        :param matrix_spec: Caller-supplied matrix specification.
        :param strategy_name: Registered sharding-strategy name.

        :returns: An :class:`ExpansionPreview`.
        :raises: ShardingStrategyNotFoundError when no registered
                 implementation declares ``strategy_name``.
        :raises: MatrixSpecInvalidError on malformed matrix specs.
    """
    strategy_cls = _resolve_strategy(strategy_name=strategy_name)
    expanded = strategy_cls.expand(
        matrix_spec=matrix_spec, runtime_history=None,
    )
    canonical_sha = matrix_spec_sha256(matrix_spec=matrix_spec)

    shard_views: List[ExpansionPreviewShard] = []
    for shard in expanded:
        dim_dict = dict(shard.dimension_values)
        shard_views.append(
            ExpansionPreviewShard(
                shard_id=shard.shard_id,
                parallel_group=shard.parallel_group,
                sequence_in_group=shard.sequence_in_group,
                dimension_values=dim_dict,
            )
        )

    rtnval = ExpansionPreview(
        strategy_name=strategy_name,
        matrix_spec_canonical_sha256=canonical_sha,
        shard_count=len(shard_views),
        shards=tuple(shard_views),
    )
    return rtnval


def expand_matrix(
        *,
        db_session: DbSession,
        project_id: str,
        parent_kind: str,
        parent_id: str,
        matrix_spec: MatrixSpec,
        strategy_name: str,
        aspects: Optional[ExpandAspects] = None
    ) -> ShardSetView:
    """
        Resolve the named sharding strategy, expand the matrix
        spec into shards, persist a :class:`ShardSet` plus its
        :class:`ShardSpec` rows, and emit
        ``entity.shard_set.expanded``.

        :raises: ShardingStrategyNotFoundError when no registered
                 implementation declares ``strategy_name``.
        :raises: MatrixSpecInvalidError on malformed matrix
                 specs (bubbled from the strategy).
    """
    if parent_kind not in ALLOWED_PARENT_KINDS:
        err_lines = ["Unsupported parent_kind for shard expansion."]
        err_lines.append("PARENT_KIND: {}".format(parent_kind))
        err_lines.append("ALLOWED: {}".format(", ".join(ALLOWED_PARENT_KINDS)))
        err_msg = os.linesep.join(err_lines)
        raise ShardingStrategyNotFoundError(err_msg) from None

    strategy_cls = _resolve_strategy(strategy_name=strategy_name)
    description = strategy_cls.describe()

    expanded = strategy_cls.expand(
        matrix_spec=matrix_spec, runtime_history=None,
    )

    effective = aspects or ExpandAspects()
    fail_fast = (
        effective.fail_fast
        if effective.fail_fast is not None
        else description.should_cancel_on_failure
    )

    canonical_sha = matrix_spec_sha256(matrix_spec=matrix_spec)
    now = utc_now()
    set_row = repository.insert_shard_set(
        db_session=db_session,
        project_id=project_id,
        parent_kind=parent_kind,
        parent_id=parent_id,
        strategy_name=strategy_name,
        matrix_spec_canonical_sha256=canonical_sha,
        fail_fast=fail_fast,
        allow_partial_success=effective.allow_partial_success,
        min_success_fraction=effective.min_success_fraction,
        started_at=now,
        note=effective.note,
        shard_count=len(expanded),
    )

    spec_views: List[ShardSpecView] = []
    for shard in expanded:
        dim_dict = dict(shard.dimension_values)
        canonical_dims = canonicalize_dimension_values(
            dimension_values=dim_dict,
        )
        spec_row = repository.insert_shard_spec(
            db_session=db_session,
            shard_set_id=str(set_row.shard_set_id),
            shard_id=shard.shard_id,
            parallel_group=shard.parallel_group,
            sequence_in_group=shard.sequence_in_group,
            dimension_values=dim_dict,
            canonical_dims_json=canonical_dims,
        )
        spec_views.append(_to_spec_view(row=spec_row))

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ShardingEventTopics.EXPANDED,
            payload={
                "shard_set_id": str(set_row.shard_set_id),
                "project_id": project_id,
                "parent_kind": parent_kind,
                "parent_id": parent_id,
                "strategy_name": strategy_name,
                "shard_count": len(expanded),
                "matrix_spec_canonical_sha256": canonical_sha,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_set_view(row=set_row, shards=tuple(spec_views))
    return rtnval


def bind_shard_to_run(
        *,
        db_session: DbSession,
        shard_set_id: str,
        shard_id: str,
        run_id: str
    ) -> ShardSpecView:
    """
        Record the Layer-5 ``run_id`` on a freshly dispatched
        shard. Idempotent on a shard already bound to the same
        run id; raises :class:`ShardingStrategyNotFoundError`
        when bound to a different run id (caller bug).

        Emits :data:`ShardingEventTopics.SHARD_BOUND`.
    """
    row = repository.find_shard_spec(
        db_session=db_session,
        shard_set_id=shard_set_id,
        shard_id=shard_id,
    )
    if row is None:
        err_lines = ["Shard spec not found."]
        err_lines.append("SHARD_SET_ID: {}".format(shard_set_id))
        err_lines.append("SHARD_ID: {}".format(shard_id))
        err_msg = os.linesep.join(err_lines)
        raise ShardSetNotFoundError(err_msg) from None

    if row.run_id is not None:
        existing = str(row.run_id)
        if existing == run_id:
            rtnval = _to_spec_view(row=row)
            return rtnval
        err_lines = ["Shard already bound to a different run."]
        err_lines.append("SHARD_SET_ID: {}".format(shard_set_id))
        err_lines.append("SHARD_ID: {}".format(shard_id))
        err_lines.append("EXISTING_RUN_ID: {}".format(existing))
        err_lines.append("REQUESTED_RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise ShardingStrategyNotFoundError(err_msg) from None

    now = utc_now()
    row.run_id = run_id
    row.state = ShardState.DISPATCHED
    row.dispatched_at = now
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ShardingEventTopics.SHARD_BOUND,
            payload={
                "shard_set_id": shard_set_id,
                "shard_id": shard_id,
                "run_id": run_id,
                "dispatched_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_spec_view(row=row)
    return rtnval


def get_shard_set(
        *,
        db_session: DbSession,
        shard_set_id: str
    ) -> ShardSetView:
    """
        Fetch a shard set + its shards by id.

        :raises: ShardSetNotFoundError on miss.
    """
    set_row = repository.find_shard_set_by_id(
        db_session=db_session, shard_set_id=shard_set_id,
    )
    if set_row is None:
        err_lines = ["Shard set not found."]
        err_lines.append("SHARD_SET_ID: {}".format(shard_set_id))
        err_msg = os.linesep.join(err_lines)
        raise ShardSetNotFoundError(err_msg) from None
    spec_rows = repository.list_shards_for_set(
        db_session=db_session, shard_set_id=shard_set_id,
    )
    spec_views = tuple(_to_spec_view(row=r) for r in spec_rows)
    rtnval = _to_set_view(row=set_row, shards=spec_views)
    return rtnval


def list_shards_for_set(
        *,
        db_session: DbSession,
        shard_set_id: str
    ) -> List[ShardSpecView]:
    """
        Return every shard for ``shard_set_id`` ordered by
        ``(parallel_group, sequence_in_group)`` ascending.
    """
    spec_rows = repository.list_shards_for_set(
        db_session=db_session, shard_set_id=shard_set_id,
    )
    rtnval = [_to_spec_view(row=r) for r in spec_rows]
    return rtnval


def _resolve_strategy(*, strategy_name: str) -> Type[ShardingStrategyProtocol]:
    """
        Return the registered strategy whose
        :meth:`strategy_name` matches ``strategy_name``. The
        registry already orders implementations by PRECEDENCE so
        the first match is the operator-preferred one.

        :raises: ShardingStrategyNotFoundError when nothing
                 matches.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=SHARDING_STRATEGY_PROTOCOL,
    )
    for impl in candidates:
        if impl.strategy_name() == strategy_name:
            return impl
    err_lines = ["No registered sharding strategy for name."]
    err_lines.append("STRATEGY_NAME: {}".format(strategy_name))
    err_lines.append("REGISTERED: {}".format(
        ", ".join(impl.strategy_name() for impl in candidates),
    ))
    err_msg = os.linesep.join(err_lines)
    raise ShardingStrategyNotFoundError(err_msg) from None


def _to_spec_view(*, row: ShardSpec) -> ShardSpecView:
    rtnval = ShardSpecView(
        shard_set_id=str(row.shard_set_id),
        shard_id=row.shard_id,
        parallel_group=row.parallel_group,
        sequence_in_group=row.sequence_in_group,
        dimension_values=dict(row.dimension_values or {}),
        state=row.state,
        run_id=str(row.run_id) if row.run_id is not None else None,
        dispatched_at=row.dispatched_at,
        finished_at=row.finished_at,
    )
    return rtnval


def _to_set_view(
        *,
        row: ShardSet,
        shards: Tuple[ShardSpecView, ...]
    ) -> ShardSetView:
    rtnval = ShardSetView(
        shard_set_id=str(row.shard_set_id),
        project_id=str(row.project_id),
        parent_kind=row.parent_kind,
        parent_id=str(row.parent_id),
        strategy_name=row.strategy_name,
        matrix_spec_canonical_sha256=row.matrix_spec_canonical_sha256,
        state=row.state,
        fail_fast=row.fail_fast,
        allow_partial_success=row.allow_partial_success,
        min_success_fraction=row.min_success_fraction,
        shard_count=row.shard_count,
        started_at=row.started_at,
        finished_at=row.finished_at,
        note=row.note,
        shards=shards,
    )
    return rtnval
