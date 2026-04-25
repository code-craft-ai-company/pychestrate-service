"""
.. module:: identity.users.directory_sync
    :synopsis: M2 directory synchronization driver.

The sync diff'd against the last-good snapshot of an external
``user_directory_source`` produces three buckets — *creates*,
*updates*, and *deactivations* — and applies each one through
the existing user-management service entry points so audit
events and outbox emissions remain unchanged. The same diff
shape applies to groups, including membership churn.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.identity.users import (
    group_service,
    user_service,
)
from automojo.pychestrate.webservice.identity.users.exceptions import (
    DirectoryCollisionError,
)
from automojo.pychestrate.webservice.identity.users.factories.user_directory_source import (
    ExternalGroupRecord,
    ExternalUserRecord,
    UserDirectorySourceProtocol,
)
from automojo.pychestrate.webservice.identity.users.models import UserStatus
from automojo.pychestrate.webservice.identity.users.repositories import (
    group_repository,
    user_repository,
)


@dataclass(frozen=True)
class DirectorySyncReport:
    """
        Per-cycle sync result.

        :param source_name: Name of the directory source.
        :param users_created: External ids of newly created
                              users.
        :param users_updated: External ids of users whose
                              fields changed.
        :param users_deactivated: External ids of users no
                                  longer present in the source.
        :param groups_created: Names of newly created groups.
        :param groups_membership_changed: Names of groups whose
                                          membership changed.
        :param errors: Stable token + detail tuples for any
                       per-record failure that did not stop the
                       cycle.
    """
    source_name: str
    users_created: Tuple[str, ...] = ()
    users_updated: Tuple[str, ...] = ()
    users_deactivated: Tuple[str, ...] = ()
    groups_created: Tuple[str, ...] = ()
    groups_membership_changed: Tuple[str, ...] = ()
    errors: Tuple[Tuple[str, str], ...] = ()


def run_directory_sync(
        *,
        db_session: DbSession,
        source_name: str,
        actor_user_id: Optional[str] = None
    ) -> DirectorySyncReport:
    """
        Run one full sync cycle against the registered
        :class:`UserDirectorySourceProtocol` whose
        :meth:`source_name` matches ``source_name``.

        The cycle:

        1. Resolve the source via the registry.
        2. Build the source's authoritative user / group
           snapshots.
        3. Compute the diff against the local rows owned by
           ``source_name``.
        4. Apply creates and updates through
           :mod:`user_service`; deactivate rows that vanished
           from the source.
        5. Apply group + membership churn through
           :mod:`group_service`.

        :raises: :class:`DirectoryCollisionError` when two
                 source records claim the same login
                 (the spec requires fail-closed behavior).
    """
    source = _resolve_source(source_name=source_name)
    if source is None:
        err_lines = ["No registered user_directory_source for the supplied name."]
        err_lines.append("SOURCE_NAME: {!r}".format(source_name))
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None

    raw_users = list(source.iter_user_records())
    raw_groups = list(source.iter_group_records())
    _check_login_uniqueness(records=raw_users)

    snapshot_by_external = {
        record.external_id: record for record in raw_users
    }
    local_users = user_repository.list_active_users_for_directory(
        db_session=db_session, provisioning_source=source_name,
    )
    local_by_external = {
        str(row.external_id): row for row in local_users
        if row.external_id is not None and len(str(row.external_id)) > 0
    }

    users_created: List[str] = []
    users_updated: List[str] = []
    users_deactivated: List[str] = []
    errors: List[Tuple[str, str]] = []

    for external_id, record in snapshot_by_external.items():
        local = local_by_external.get(external_id)
        if local is None:
            try:
                _create_from_record(
                    db_session=db_session,
                    source_name=source_name,
                    record=record,
                    actor_user_id=actor_user_id,
                )
                users_created.append(external_id)
            except Exception as create_err:
                errors.append(("user_create_failed", str(create_err)))
            continue
        if _record_differs(local=local, record=record):
            try:
                _apply_record_update(
                    db_session=db_session,
                    user_id=str(local.user_id),
                    record=record,
                    actor_user_id=actor_user_id,
                )
                users_updated.append(external_id)
            except Exception as update_err:
                errors.append(("user_update_failed", str(update_err)))

    for external_id, local in local_by_external.items():
        if external_id in snapshot_by_external:
            continue
        if local.status == UserStatus.DEACTIVATED:
            continue
        try:
            user_service.deactivate_user(
                db_session=db_session,
                user_id=str(local.user_id),
                reason="directory_sync:vanished",
                actor_user_id=actor_user_id,
            )
            users_deactivated.append(external_id)
        except Exception as deact_err:
            errors.append(("user_deactivate_failed", str(deact_err)))

    groups_created, groups_membership_changed = _apply_group_diff(
        db_session=db_session,
        records=raw_groups,
        source_name=source_name,
        actor_user_id=actor_user_id,
        errors=errors,
    )

    rtnval = DirectorySyncReport(
        source_name=source_name,
        users_created=tuple(users_created),
        users_updated=tuple(users_updated),
        users_deactivated=tuple(users_deactivated),
        groups_created=tuple(groups_created),
        groups_membership_changed=tuple(groups_membership_changed),
        errors=tuple(errors),
    )
    return rtnval


def _resolve_source(
        *, source_name: str
    ) -> Optional[Type[UserDirectorySourceProtocol]]:
    candidates = list_factory_implementations(
        factory_protocol_name=UserDirectorySourceProtocol.factory_protocol_name,
    )
    for impl in candidates:
        try:
            name = impl.source_name()
        except NotImplementedError:
            continue
        if name == source_name:
            return impl
    return None


def _check_login_uniqueness(*, records: Iterable[ExternalUserRecord]) -> None:
    seen = {}
    for record in records:
        normalized = record.login_name.strip().lower()
        if len(normalized) == 0:
            continue
        prior = seen.get(normalized)
        if prior is not None and prior != record.external_id:
            err_lines = [
                "Directory sync detected duplicate login_name.",
            ]
            err_lines.append("LOGIN_NAME: {}".format(normalized))
            err_lines.append("EXTERNAL_IDS: {}, {}".format(
                prior, record.external_id,
            ))
            err_msg = os.linesep.join(err_lines)
            raise DirectoryCollisionError(err_msg) from None
        seen[normalized] = record.external_id
    return


def _record_differs(*, local, record: ExternalUserRecord) -> bool:
    """
        Return True when at least one field differs between the
        local row and the source's authoritative record.
    """
    if local.login_name != record.login_name.strip().lower():
        return True
    if local.primary_email != record.primary_email.strip().lower():
        return True
    if local.display_name != record.display_name:
        return True
    if local.timezone != record.timezone:
        return True
    if record.is_active is True and local.status == UserStatus.DEACTIVATED:
        return True
    if record.is_active is False and local.status == UserStatus.ACTIVE:
        return True
    return False


def _create_from_record(
        *,
        db_session: DbSession,
        source_name: str,
        record: ExternalUserRecord,
        actor_user_id: Optional[str]
    ) -> None:
    user_service.create_user(
        db_session=db_session,
        login_name=record.login_name,
        primary_email=record.primary_email,
        display_name=record.display_name,
        timezone=record.timezone,
        provisioning_source=source_name,
        external_id=record.external_id,
        actor_user_id=actor_user_id,
    )
    return


def _apply_record_update(
        *,
        db_session: DbSession,
        user_id: str,
        record: ExternalUserRecord,
        actor_user_id: Optional[str]
    ) -> None:
    user_service.update_profile(
        db_session=db_session,
        user_id=user_id,
        display_name=record.display_name,
        timezone_name=record.timezone,
        actor_user_id=actor_user_id,
    )
    if record.is_active is False:
        user_service.deactivate_user(
            db_session=db_session,
            user_id=user_id,
            reason="directory_sync:source_inactive",
            actor_user_id=actor_user_id,
        )
    elif record.is_active is True:
        local = user_repository.get_by_id(
            db_session=db_session, user_id=user_id,
        )
        if local is not None and local.status == UserStatus.DEACTIVATED:
            user_service.reactivate_user(
                db_session=db_session,
                user_id=user_id,
                actor_user_id=actor_user_id,
            )
    return


def _apply_group_diff(
        *,
        db_session: DbSession,
        records: Iterable[ExternalGroupRecord],
        source_name: str,
        actor_user_id: Optional[str],
        errors: List[Tuple[str, str]]
    ) -> Tuple[List[str], List[str]]:
    groups_created: List[str] = []
    groups_membership_changed: List[str] = []
    for record in records:
        existing = group_repository.get_by_name(
            db_session=db_session, group_name=record.group_name,
        )
        if existing is None:
            try:
                view = group_service.create_group(
                    db_session=db_session,
                    group_name=record.group_name,
                    description=record.description,
                    actor_user_id=actor_user_id,
                )
                groups_created.append(record.group_name)
                group_id = view.group_id
            except Exception as create_err:
                errors.append(("group_create_failed", str(create_err)))
                continue
        else:
            group_id = str(existing.group_id)

        try:
            membership_changed = _reconcile_group_membership(
                db_session=db_session,
                group_id=group_id,
                source_name=source_name,
                desired_external_ids=record.member_external_ids,
                actor_user_id=actor_user_id,
            )
            if membership_changed is True:
                groups_membership_changed.append(record.group_name)
        except Exception as membership_err:
            errors.append(
                ("group_membership_failed", str(membership_err)),
            )
    return (groups_created, groups_membership_changed)


def _reconcile_group_membership(
        *,
        db_session: DbSession,
        group_id: str,
        source_name: str,
        desired_external_ids: Iterable[str],
        actor_user_id: Optional[str]
    ) -> bool:
    desired_set = set()
    for external_id in desired_external_ids:
        if external_id is None or len(external_id) == 0:
            continue
        desired_set.add(external_id)

    desired_user_ids = set()
    for external_id in desired_set:
        for row in user_repository.list_active_users_for_directory(
            db_session=db_session, provisioning_source=source_name,
        ):
            if str(row.external_id) == external_id:
                desired_user_ids.add(str(row.user_id))
                break

    actual_memberships = group_repository.list_memberships_for_group(
        db_session=db_session, group_id=group_id,
    )
    actual_user_ids = set(
        str(membership.user_id) for membership in actual_memberships
    )

    to_add = desired_user_ids - actual_user_ids
    to_remove = actual_user_ids - desired_user_ids

    changed = False
    for user_id in to_add:
        group_service.add_user_to_group(
            db_session=db_session,
            group_id=group_id,
            user_id=user_id,
            actor_user_id=actor_user_id,
        )
        changed = True
    for user_id in to_remove:
        group_service.remove_user_from_group(
            db_session=db_session,
            group_id=group_id,
            user_id=user_id,
            actor_user_id=actor_user_id,
        )
        changed = True
    return changed
