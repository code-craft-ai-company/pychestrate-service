"""
.. module:: identity.users.repositories.group_repository
    :synopsis: Repository for IdentityGroup + IdentityGroupMembership rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.identity.users.models import (
    IdentityGroup,
    IdentityGroupMembership,
)


def insert(*, db_session: DbSession, group: IdentityGroup) -> IdentityGroup:
    """
        Insert a new group row and flush.
    """
    db_session.add(group)
    db_session.flush()
    rtnval = group
    return rtnval


def get_by_id(
        *,
        db_session: DbSession,
        group_id: str
    ) -> Optional[IdentityGroup]:
    """
        Lookup by id.
    """
    rtnval = (
        db_session.query(IdentityGroup)
        .filter(IdentityGroup.group_id == group_id)
        .first()
    )
    return rtnval


def get_by_name(
        *,
        db_session: DbSession,
        group_name: str
    ) -> Optional[IdentityGroup]:
    """
        Lookup by ``group_name``. Group names are case-sensitive
        per spec — directory sources own the canonicalization.
    """
    rtnval = (
        db_session.query(IdentityGroup)
        .filter(IdentityGroup.group_name == group_name)
        .first()
    )
    return rtnval


def list_groups(
        *,
        db_session: DbSession
    ) -> List[IdentityGroup]:
    """
        List all groups ordered by name.
    """
    rows = (
        db_session.query(IdentityGroup)
        .order_by(IdentityGroup.group_name.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def delete(*, db_session: DbSession, group: IdentityGroup) -> None:
    """
        Delete a group; ON DELETE CASCADE on the membership row
        drops the join table entries.
    """
    db_session.delete(group)
    db_session.flush()
    return


def insert_membership(
        *,
        db_session: DbSession,
        group_id: str,
        user_id: str,
        added_by: Optional[str],
        added_at: datetime
    ) -> IdentityGroupMembership:
    """
        Persist a membership row. The caller owns the
        already-exists check.
    """
    row = IdentityGroupMembership(
        group_id=group_id,
        user_id=user_id,
        added_by=added_by,
        added_at=added_at,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_membership(
        *,
        db_session: DbSession,
        group_id: str,
        user_id: str
    ) -> Optional[IdentityGroupMembership]:
    """
        Lookup a single membership row.
    """
    rtnval = (
        db_session.query(IdentityGroupMembership)
        .filter(IdentityGroupMembership.group_id == group_id)
        .filter(IdentityGroupMembership.user_id == user_id)
        .first()
    )
    return rtnval


def delete_membership(
        *,
        db_session: DbSession,
        membership: IdentityGroupMembership
    ) -> None:
    """
        Drop a single membership row.
    """
    db_session.delete(membership)
    db_session.flush()
    return


def list_memberships_for_group(
        *,
        db_session: DbSession,
        group_id: str
    ) -> List[IdentityGroupMembership]:
    """
        List every membership row for ``group_id``.
    """
    rows = (
        db_session.query(IdentityGroupMembership)
        .filter(IdentityGroupMembership.group_id == group_id)
        .order_by(IdentityGroupMembership.added_at.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_memberships_for_user(
        *,
        db_session: DbSession,
        user_id: str
    ) -> List[IdentityGroupMembership]:
    """
        List every membership row a user belongs to.
    """
    rows = (
        db_session.query(IdentityGroupMembership)
        .filter(IdentityGroupMembership.user_id == user_id)
        .all()
    )
    rtnval = list(rows)
    return rtnval
