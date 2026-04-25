"""
.. module:: identity.users.group_service
    :synopsis: M2 group CRUD + membership service.

The service owns:

* :func:`create_group` — UNIQUE on ``group_name``.
* :func:`delete_group` — drops the group + cascades the
  membership rows.
* :func:`add_user_to_group` /
  :func:`remove_user_from_group` — idempotent membership
  toggles.
* :func:`get_group` / :func:`list_groups` / read helpers.

Every mutation enqueues an outbox event so downstream
consumers (audit log, RBAC cache invalidation) see the
transition without polling.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.identity.users.events import (
    UserEventTopics,
)
from automojo.pychestrate.webservice.identity.users.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)
from automojo.pychestrate.webservice.identity.users.models import (
    IdentityGroup,
    IdentityGroupMembership,
)
from automojo.pychestrate.webservice.identity.users.repositories import (
    group_repository,
    user_repository,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


class GroupNotFoundError(Exception):
    """
        Raised when a group lookup misses.
    """


class GroupAlreadyExistsError(Exception):
    """
        Raised when create_group conflicts on ``group_name``.
    """


@dataclass(frozen=True)
class GroupView:
    """
        Caller-facing group read-model.
    """
    group_id: str
    group_name: str
    description: str
    created_at: datetime
    member_user_ids: Tuple[str, ...]


def create_group(
        *,
        db_session: DbSession,
        group_name: str,
        description: str = "",
        actor_user_id: Optional[str] = None
    ) -> GroupView:
    """
        Create a group. UNIQUE on ``group_name``.

        :raises: SemanticError on empty name;
                 GroupAlreadyExistsError on duplicate.
    """
    if group_name is None or len(group_name.strip()) == 0:
        err_lines = ["create_group requires a non-empty group_name."]
        err_msg = os.linesep.join(err_lines)
        raise SemanticError(err_msg) from None
    normalized = group_name.strip()
    existing = group_repository.get_by_name(
        db_session=db_session, group_name=normalized,
    )
    if existing is not None:
        err_lines = ["Group with that name already exists."]
        err_lines.append("GROUP_NAME: {}".format(normalized))
        err_msg = os.linesep.join(err_lines)
        raise GroupAlreadyExistsError(err_msg) from None

    now = utc_now()
    row = IdentityGroup(
        group_id=new_uuid(),
        group_name=normalized,
        description=description,
        created_at=now,
    )
    try:
        group_repository.insert(db_session=db_session, group=row)
    except IntegrityError:
        err_lines = ["Group with that name already exists."]
        err_lines.append("GROUP_NAME: {}".format(normalized))
        err_msg = os.linesep.join(err_lines)
        raise GroupAlreadyExistsError(err_msg) from None
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UserEventTopics.GROUP_CREATED,
            payload={
                "group_id": str(row.group_id),
                "group_name": normalized,
                "actor_user_id": actor_user_id,
                "created_at": now.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _row_to_view(row=row, member_ids=())
    return rtnval


def delete_group(
        *,
        db_session: DbSession,
        group_id: str,
        actor_user_id: Optional[str] = None
    ) -> bool:
    """
        Delete a group + its membership rows. Idempotent —
        returns ``False`` when no row was found.

        Emits :data:`UserEventTopics.GROUP_DELETED` only on the
        successful first transition.
    """
    row = group_repository.get_by_id(
        db_session=db_session, group_id=group_id,
    )
    if row is None:
        return False
    name = row.group_name
    group_repository.delete(db_session=db_session, group=row)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UserEventTopics.GROUP_DELETED,
            payload={
                "group_id": group_id,
                "group_name": name,
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return True


def get_group(
        *,
        db_session: DbSession,
        group_id: str
    ) -> GroupView:
    """
        Read a group by id, including its membership.

        :raises: GroupNotFoundError on miss.
    """
    row = _require_group(db_session=db_session, group_id=group_id)
    member_ids = _list_member_ids(
        db_session=db_session, group_id=group_id,
    )
    rtnval = _row_to_view(row=row, member_ids=member_ids)
    return rtnval


def list_groups(*, db_session: DbSession) -> List[GroupView]:
    """
        List every group ordered by name. Membership is
        materialized per row.
    """
    rows = group_repository.list_groups(db_session=db_session)
    rtnval: List[GroupView] = []
    for row in rows:
        member_ids = _list_member_ids(
            db_session=db_session, group_id=str(row.group_id),
        )
        rtnval.append(_row_to_view(row=row, member_ids=member_ids))
    return rtnval


def add_user_to_group(
        *,
        db_session: DbSession,
        group_id: str,
        user_id: str,
        actor_user_id: Optional[str] = None
    ) -> IdentityGroupMembership:
    """
        Add a user to a group. Idempotent — returns the
        existing membership row when the join already exists.

        :raises: GroupNotFoundError, UserNotFoundError.
    """
    _require_group(db_session=db_session, group_id=group_id)
    user = user_repository.get_by_id(
        db_session=db_session, user_id=user_id,
    )
    if user is None:
        err_lines = ["Cannot add membership — user_id not found."]
        err_lines.append("USER_ID: {}".format(user_id))
        err_msg = os.linesep.join(err_lines)
        raise UserNotFoundError(err_msg) from None

    existing = group_repository.find_membership(
        db_session=db_session, group_id=group_id, user_id=user_id,
    )
    if existing is not None:
        return existing
    now = utc_now()
    row = group_repository.insert_membership(
        db_session=db_session,
        group_id=group_id,
        user_id=user_id,
        added_by=actor_user_id,
        added_at=now,
    )
    _emit_membership_changed(
        db_session=db_session,
        group_id=group_id,
        user_id=user_id,
        added=True,
        actor_user_id=actor_user_id,
    )
    db_session.commit()
    return row


def remove_user_from_group(
        *,
        db_session: DbSession,
        group_id: str,
        user_id: str,
        actor_user_id: Optional[str] = None
    ) -> bool:
    """
        Remove a user from a group. Idempotent — returns
        ``False`` when the membership row does not exist.
    """
    _require_group(db_session=db_session, group_id=group_id)
    membership = group_repository.find_membership(
        db_session=db_session, group_id=group_id, user_id=user_id,
    )
    if membership is None:
        return False
    group_repository.delete_membership(
        db_session=db_session, membership=membership,
    )
    _emit_membership_changed(
        db_session=db_session,
        group_id=group_id,
        user_id=user_id,
        added=False,
        actor_user_id=actor_user_id,
    )
    db_session.commit()
    return True


def list_groups_for_user(
        *,
        db_session: DbSession,
        user_id: str
    ) -> List[GroupView]:
    """
        Return every group the user is a member of.
    """
    memberships = group_repository.list_memberships_for_user(
        db_session=db_session, user_id=user_id,
    )
    rtnval: List[GroupView] = []
    for membership in memberships:
        row = group_repository.get_by_id(
            db_session=db_session, group_id=str(membership.group_id),
        )
        if row is None:
            continue
        member_ids = _list_member_ids(
            db_session=db_session, group_id=str(row.group_id),
        )
        rtnval.append(_row_to_view(row=row, member_ids=member_ids))
    return rtnval


def _require_group(
        *, db_session: DbSession, group_id: str
    ) -> IdentityGroup:
    row = group_repository.get_by_id(
        db_session=db_session, group_id=group_id,
    )
    if row is None:
        err_lines = ["Group not found."]
        err_lines.append("GROUP_ID: {}".format(group_id))
        err_msg = os.linesep.join(err_lines)
        raise GroupNotFoundError(err_msg) from None
    return row


def _list_member_ids(
        *, db_session: DbSession, group_id: str
    ) -> Tuple[str, ...]:
    rows = group_repository.list_memberships_for_group(
        db_session=db_session, group_id=group_id,
    )
    rtnval = tuple(str(row.user_id) for row in rows)
    return rtnval


def _emit_membership_changed(
        *,
        db_session: DbSession,
        group_id: str,
        user_id: str,
        added: bool,
        actor_user_id: Optional[str]
    ) -> None:
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=UserEventTopics.GROUP_MEMBERSHIP_CHANGED,
            payload={
                "group_id": group_id,
                "user_id": user_id,
                "added": added,
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    return


def _row_to_view(
        *, row: IdentityGroup, member_ids: Tuple[str, ...]
    ) -> GroupView:
    rtnval = GroupView(
        group_id=str(row.group_id),
        group_name=row.group_name,
        description=row.description,
        created_at=row.created_at,
        member_user_ids=member_ids,
    )
    return rtnval
