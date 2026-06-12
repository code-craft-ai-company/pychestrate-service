"""
.. module:: resources.pools.repository
    :synopsis: CRUD helpers for resource pools.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.resources.pools.models import (
    ResourcePool,
    ResourcePoolMember,
)


def insert_pool(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        description: str,
        capability_tags: list,
        created_at: datetime
    ) -> ResourcePool:
    """
        Insert a fresh pool row.
    """
    row = ResourcePool(
        pool_id=new_uuid(),
        project_id=project_id,
        name=name,
        description=description,
        capability_tags=list(capability_tags),
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_pool_by_id(
        *,
        db_session: DbSession,
        pool_id: str
    ) -> Optional[ResourcePool]:
    rtnval = (
        db_session.query(ResourcePool)
        .filter(ResourcePool.pool_id == pool_id)
        .first()
    )
    return rtnval


def find_pool_by_name(
        *,
        db_session: DbSession,
        project_id: str,
        name: str
    ) -> Optional[ResourcePool]:
    rtnval = (
        db_session.query(ResourcePool)
        .filter(ResourcePool.project_id == project_id)
        .filter(ResourcePool.name == name)
        .first()
    )
    return rtnval


def list_pools(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[ResourcePool]:
    rows = (
        db_session.query(ResourcePool)
        .filter(ResourcePool.project_id == project_id)
        .order_by(ResourcePool.name.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def delete_pool(
        *,
        db_session: DbSession,
        row: ResourcePool
    ) -> None:
    db_session.delete(row)
    db_session.flush()
    return


def find_member(
        *,
        db_session: DbSession,
        pool_id: str,
        resource_id: str
    ) -> Optional[ResourcePoolMember]:
    rtnval = (
        db_session.query(ResourcePoolMember)
        .filter(ResourcePoolMember.pool_id == pool_id)
        .filter(ResourcePoolMember.resource_id == resource_id)
        .first()
    )
    return rtnval


def list_members(
        *,
        db_session: DbSession,
        pool_id: str
    ) -> List[ResourcePoolMember]:
    rows = (
        db_session.query(ResourcePoolMember)
        .filter(ResourcePoolMember.pool_id == pool_id)
        .order_by(ResourcePoolMember.added_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def insert_member(
        *,
        db_session: DbSession,
        pool_id: str,
        resource_id: str,
        added_at: datetime
    ) -> ResourcePoolMember:
    row = ResourcePoolMember(
        membership_id=new_uuid(),
        pool_id=pool_id,
        resource_id=resource_id,
        added_at=added_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def delete_member(
        *,
        db_session: DbSession,
        row: ResourcePoolMember
    ) -> None:
    db_session.delete(row)
    db_session.flush()
    return
