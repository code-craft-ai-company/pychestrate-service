"""
.. module:: resources.inventory.repository
    :synopsis: CRUD helpers for ``resources_resource`` rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.resources.inventory.models import (
    Resource,
    ResourceState,
)


def insert_resource(
        *,
        db_session: DbSession,
        project_id: str,
        kind: str,
        display_name: str,
        description: str,
        identity_hash: str,
        tags: list,
        attributes: dict,
        created_at: datetime
    ) -> Resource:
    """
        Insert a fresh resource row in
        :attr:`ResourceState.AVAILABLE`.
    """
    row = Resource(
        resource_id=new_uuid(),
        project_id=project_id,
        kind=kind,
        display_name=display_name,
        description=description,
        identity_hash=identity_hash,
        state=ResourceState.AVAILABLE,
        tags=list(tags),
        attributes=dict(attributes),
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_by_identity(
        *,
        db_session: DbSession,
        kind: str,
        identity_hash: str
    ) -> Optional[Resource]:
    """
        Return the non-retired row for a ``(kind, identity_hash)``
        pair or ``None``.
    """
    rtnval = (
        db_session.query(Resource)
        .filter(Resource.kind == kind)
        .filter(Resource.identity_hash == identity_hash)
        .filter(Resource.state != ResourceState.RETIRED)
        .first()
    )
    return rtnval


def find_by_id(
        *,
        db_session: DbSession,
        resource_id: str
    ) -> Optional[Resource]:
    """
        Fetch a row by id.
    """
    rtnval = (
        db_session.query(Resource)
        .filter(Resource.resource_id == resource_id)
        .first()
    )
    return rtnval


def list_by_project(
        *,
        db_session: DbSession,
        project_id: str,
        kind: Optional[str] = None,
        include_retired: bool = False
    ) -> List[Resource]:
    """
        List resources for a project with optional kind filter.
    """
    query = (
        db_session.query(Resource)
        .filter(Resource.project_id == project_id)
    )
    if kind is not None:
        query = query.filter(Resource.kind == kind)
    if include_retired is False:
        query = query.filter(Resource.state != ResourceState.RETIRED)
    rows = query.order_by(Resource.created_at.asc()).all()
    rtnval = list(rows)
    return rtnval


def update_profile(
        *,
        db_session: DbSession,
        row: Resource,
        display_name: str,
        description: str,
        tags: list,
        updated_at: datetime
    ) -> None:
    """
        Apply a change to the fields a person edits (the identity and the
        kind-validated attributes are not among them).
    """
    row.display_name = display_name
    row.description = description
    row.tags = list(tags)
    row.updated_at = updated_at
    db_session.flush()
    return


def update_state(
        *,
        db_session: DbSession,
        row: Resource,
        new_state: ResourceState,
        updated_at: datetime
    ) -> None:
    """
        Apply a state change.
    """
    row.state = new_state
    row.updated_at = updated_at
    db_session.flush()
    return
