"""
.. module:: resources.pools.service
    :synopsis: Pool facade — create / get / list / add / remove / pick.

M1 ships a hard-wired FIFO allocation strategy: ``pick_candidate``
returns the eligible member with the earliest ``added_at`` among
those whose underlying resource is :attr:`ResourceState.AVAILABLE`.
M2 swaps in a registry-driven strategy via the
``pool_allocation_strategy`` factory protocol.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.resources.inventory.models import (
    Resource,
    ResourceState,
)
from ccai.pychestrate.webservice.resources.pools import repository
from ccai.pychestrate.webservice.resources.pools.errors import (
    PoolEmptyError,
    PoolMemberConflictError,
    PoolNotFoundError,
)
from ccai.pychestrate.webservice.resources.pools.events import (
    PoolEventTopics,
)
from ccai.pychestrate.webservice.resources.pools.models import (
    ResourcePool,
    ResourcePoolMember,
)


@dataclass(frozen=True)
class PoolView:
    """
        Caller-facing pool read-model.
    """
    pool_id: str
    project_id: str
    name: str
    description: str
    capability_tags: Tuple[str, ...]
    member_count: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class PoolCandidate:
    """
        One eligible pool member.
    """
    resource_id: str
    pool_id: str
    added_at: datetime


@dataclass(frozen=True)
class AllocationAspects:
    """
        Knobs that influence allocation. M1 honors only
        ``preferred_member`` (returned ahead of any other if
        present + eligible). ``sticky_tag`` and ``job_hint``
        land in M2.
    """
    sticky_tag: Optional[str] = None
    job_hint: Optional[str] = None
    preferred_member: Optional[str] = None


def create_pool(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        description: str = "",
        capability_tags: Optional[Tuple[str, ...]] = None
    ) -> PoolView:
    """
        Create a fresh pool. Raises
        :class:`PoolMemberConflictError` on duplicate name.
    """
    existing = repository.find_pool_by_name(
        db_session=db_session, project_id=project_id, name=name,
    )
    if existing is not None:
        err_lines = ["Pool name already exists in this project."]
        err_lines.append("PROJECT_ID: {}".format(project_id))
        err_lines.append("NAME: {}".format(name))
        err_msg = os.linesep.join(err_lines)
        raise PoolMemberConflictError(err_msg) from None

    now = utc_now()
    row = repository.insert_pool(
        db_session=db_session,
        project_id=project_id,
        name=name,
        description=description,
        capability_tags=list(capability_tags or ()),
        created_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PoolEventTopics.CREATED,
            payload={
                "pool_id": str(row.pool_id),
                "project_id": project_id,
                "name": name,
                "capability_tags": list(capability_tags or ()),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row, member_count=0)
    return rtnval


def get_pool(
        *,
        db_session: DbSession,
        pool_id: str
    ) -> PoolView:
    """
        Fetch a pool by id, raising on miss.
    """
    row = repository.find_pool_by_id(db_session=db_session, pool_id=pool_id)
    if row is None:
        err_lines = ["Pool not found."]
        err_lines.append("POOL_ID: {}".format(pool_id))
        err_msg = os.linesep.join(err_lines)
        raise PoolNotFoundError(err_msg) from None
    members = repository.list_members(db_session=db_session, pool_id=pool_id)
    rtnval = _to_view(row=row, member_count=len(members))
    return rtnval


def list_pools(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[PoolView]:
    rows = repository.list_pools(db_session=db_session, project_id=project_id)
    rtnval: List[PoolView] = []
    for row in rows:
        members = repository.list_members(
            db_session=db_session, pool_id=str(row.pool_id),
        )
        rtnval.append(_to_view(row=row, member_count=len(members)))
    return rtnval


def add_member(
        *,
        db_session: DbSession,
        pool_id: str,
        resource_id: str
    ) -> ResourcePoolMember:
    """
        Add a resource to a pool. Idempotent — returns the
        existing membership row when one already exists.
    """
    pool = repository.find_pool_by_id(db_session=db_session, pool_id=pool_id)
    if pool is None:
        err_lines = ["Pool not found."]
        err_lines.append("POOL_ID: {}".format(pool_id))
        err_msg = os.linesep.join(err_lines)
        raise PoolNotFoundError(err_msg) from None

    existing = repository.find_member(
        db_session=db_session, pool_id=pool_id, resource_id=resource_id,
    )
    if existing is not None:
        return existing

    now = utc_now()
    row = repository.insert_member(
        db_session=db_session,
        pool_id=pool_id,
        resource_id=resource_id,
        added_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PoolEventTopics.MEMBER_ADDED,
            payload={"pool_id": pool_id, "resource_id": resource_id},
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return row


def remove_member(
        *,
        db_session: DbSession,
        pool_id: str,
        resource_id: str
    ) -> None:
    """
        Remove a resource from a pool. Idempotent on missing
        membership.
    """
    existing = repository.find_member(
        db_session=db_session, pool_id=pool_id, resource_id=resource_id,
    )
    if existing is None:
        return
    repository.delete_member(db_session=db_session, row=existing)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PoolEventTopics.MEMBER_REMOVED,
            payload={"pool_id": pool_id, "resource_id": resource_id},
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def pick_candidate(
        *,
        db_session: DbSession,
        pool_id: str,
        aspects: Optional[AllocationAspects] = None
    ) -> PoolCandidate:
    """
        Hard-wired FIFO M1 allocation: among members whose
        underlying resource is AVAILABLE, return the one with the
        earliest ``added_at``. ``aspects.preferred_member`` short-
        circuits if it is eligible.

        :raises: PoolNotFoundError, PoolEmptyError.
    """
    pool = repository.find_pool_by_id(db_session=db_session, pool_id=pool_id)
    if pool is None:
        err_lines = ["Pool not found."]
        err_lines.append("POOL_ID: {}".format(pool_id))
        err_msg = os.linesep.join(err_lines)
        raise PoolNotFoundError(err_msg) from None

    members = repository.list_members(db_session=db_session, pool_id=pool_id)
    if len(members) == 0:
        err_lines = ["Pool has no members."]
        err_lines.append("POOL_ID: {}".format(pool_id))
        err_msg = os.linesep.join(err_lines)
        raise PoolEmptyError(err_msg) from None

    member_ids = [str(m.resource_id) for m in members]
    resource_rows = (
        db_session.query(Resource)
        .filter(Resource.resource_id.in_(member_ids))
        .filter(Resource.state == ResourceState.AVAILABLE)
        .all()
    )
    eligible_ids = {str(r.resource_id) for r in resource_rows}

    eligible_members = [m for m in members if str(m.resource_id) in eligible_ids]
    if len(eligible_members) == 0:
        err_lines = ["No member of the pool is in AVAILABLE state."]
        err_lines.append("POOL_ID: {}".format(pool_id))
        err_lines.append("MEMBER_COUNT: {}".format(len(members)))
        err_msg = os.linesep.join(err_lines)
        raise PoolEmptyError(err_msg) from None

    effective = aspects or AllocationAspects()
    if effective.preferred_member is not None:
        for member in eligible_members:
            if str(member.resource_id) == effective.preferred_member:
                rtnval = PoolCandidate(
                    resource_id=str(member.resource_id),
                    pool_id=str(member.pool_id),
                    added_at=member.added_at,
                )
                return rtnval

    eligible_members.sort(key=lambda m: m.added_at)
    chosen = eligible_members[0]
    rtnval = PoolCandidate(
        resource_id=str(chosen.resource_id),
        pool_id=str(chosen.pool_id),
        added_at=chosen.added_at,
    )
    return rtnval


def _to_view(*, row: ResourcePool, member_count: int) -> PoolView:
    """
        Convert a pool row to the read-model.
    """
    rtnval = PoolView(
        pool_id=str(row.pool_id),
        project_id=str(row.project_id),
        name=row.name,
        description=row.description,
        capability_tags=tuple(row.capability_tags or ()),
        member_count=member_count,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval
