"""
.. module:: orchestration.pipelines.sharding.repository
    :synopsis: CRUD helpers for shard-set / shard-spec rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.orchestration.pipelines.sharding.models import (
    ShardSet,
    ShardSetState,
    ShardSpec,
    ShardState,
)


def insert_shard_set(
        *,
        db_session: DbSession,
        project_id: str,
        parent_kind: str,
        parent_id: str,
        strategy_name: str,
        matrix_spec_canonical_sha256: str,
        fail_fast: bool,
        allow_partial_success: bool,
        min_success_fraction: float,
        started_at: datetime,
        note: str,
        shard_count: int
    ) -> ShardSet:
    row = ShardSet(
        shard_set_id=new_uuid(),
        project_id=project_id,
        parent_kind=parent_kind,
        parent_id=parent_id,
        strategy_name=strategy_name,
        matrix_spec_canonical_sha256=matrix_spec_canonical_sha256,
        state=ShardSetState.IN_PROGRESS,
        fail_fast=fail_fast,
        allow_partial_success=allow_partial_success,
        min_success_fraction=min_success_fraction,
        shard_count=shard_count,
        started_at=started_at,
        finished_at=None,
        note=note,
    )
    db_session.add(row)
    db_session.flush()
    return row


def insert_shard_spec(
        *,
        db_session: DbSession,
        shard_set_id: str,
        shard_id: str,
        parallel_group: str,
        sequence_in_group: int,
        dimension_values: Dict[str, str],
        canonical_dims_json: str
    ) -> ShardSpec:
    row = ShardSpec(
        shard_set_id=shard_set_id,
        shard_id=shard_id,
        parallel_group=parallel_group,
        sequence_in_group=sequence_in_group,
        dimension_values=dict(dimension_values),
        canonical_dims_json=canonical_dims_json,
        state=ShardState.PENDING,
        run_id=None,
        dispatched_at=None,
        finished_at=None,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_shard_set_by_id(
        *,
        db_session: DbSession,
        shard_set_id: str
    ) -> Optional[ShardSet]:
    rtnval = (
        db_session.query(ShardSet)
        .filter(ShardSet.shard_set_id == shard_set_id)
        .first()
    )
    return rtnval


def list_shards_for_set(
        *,
        db_session: DbSession,
        shard_set_id: str
    ) -> List[ShardSpec]:
    rows = (
        db_session.query(ShardSpec)
        .filter(ShardSpec.shard_set_id == shard_set_id)
        .order_by(
            ShardSpec.parallel_group.asc(),
            ShardSpec.sequence_in_group.asc(),
        )
        .all()
    )
    rtnval = list(rows)
    return rtnval


def find_shard_spec(
        *,
        db_session: DbSession,
        shard_set_id: str,
        shard_id: str
    ) -> Optional[ShardSpec]:
    rtnval = (
        db_session.query(ShardSpec)
        .filter(ShardSpec.shard_set_id == shard_set_id)
        .filter(ShardSpec.shard_id == shard_id)
        .first()
    )
    return rtnval
