"""
.. module:: resources.inventory.service
    :synopsis: Inventory facade — register / get / list / transition.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.resources.inventory import repository
from ccai.pychestrate.webservice.resources.inventory.errors import (
    ResourceIdentityConflictError,
    ResourceKindUnknownError,
    ResourceNotFoundError,
    ResourceStateTransitionError,
)
from ccai.pychestrate.webservice.resources.inventory.events import (
    ResourceEventTopics,
)
from ccai.pychestrate.webservice.resources.inventory.kinds.kind_protocol import (
    ResourceKindProtocol,
)
from ccai.pychestrate.webservice.resources.inventory.models import (
    Resource,
    ResourceState,
)


RESOURCE_KIND_PROTOCOL: str = "resource_kind"


@dataclass(frozen=True)
class ResourceView:
    """
        Caller-facing read-model.
    """
    resource_id: str
    project_id: str
    kind: str
    display_name: str
    description: str
    identity_hash: str
    state: ResourceState
    tags: Tuple[str, ...]
    attributes: Mapping[str, Any]
    created_at: datetime
    updated_at: datetime


# Permitted (from_state, to_state) transitions. Retired is
# terminal — un-retiring requires a fresh registration.
_PERMITTED_TRANSITIONS = frozenset({
    (ResourceState.AVAILABLE, ResourceState.LEASED),
    (ResourceState.LEASED, ResourceState.AVAILABLE),
    (ResourceState.AVAILABLE, ResourceState.QUARANTINED),
    (ResourceState.QUARANTINED, ResourceState.AVAILABLE),
    (ResourceState.AVAILABLE, ResourceState.MAINTENANCE),
    (ResourceState.MAINTENANCE, ResourceState.AVAILABLE),
    (ResourceState.LEASED, ResourceState.QUARANTINED),
    (ResourceState.AVAILABLE, ResourceState.RETIRED),
    (ResourceState.QUARANTINED, ResourceState.RETIRED),
    (ResourceState.MAINTENANCE, ResourceState.RETIRED),
})


def register_resource(
        *,
        db_session: DbSession,
        project_id: str,
        kind: str,
        display_name: str,
        attributes: Mapping[str, Any],
        description: str = "",
        tags: Optional[Tuple[str, ...]] = None
    ) -> ResourceView:
    """
        Register a fresh resource. Resolves the registered
        :class:`ResourceKindProtocol` for ``kind``, validates +
        normalizes attributes through it, computes the identity
        hash, and inserts a row in
        :attr:`ResourceState.AVAILABLE`.

        :raises: ResourceKindUnknownError, SemanticError,
                 ResourceIdentityConflictError.
    """
    kind_impl = _resolve_kind(kind=kind)
    normalized = kind_impl.normalize(attributes=attributes)
    identity_hash = kind_impl.identity_hash(attributes=normalized)

    existing = repository.find_by_identity(
        db_session=db_session, kind=kind, identity_hash=identity_hash,
    )
    if existing is not None:
        err_lines = ["Resource identity already registered."]
        err_lines.append("KIND: {}".format(kind))
        err_lines.append("IDENTITY_HASH: {}".format(identity_hash))
        err_lines.append("EXISTING_ID: {}".format(existing.resource_id))
        err_msg = os.linesep.join(err_lines)
        raise ResourceIdentityConflictError(err_msg) from None

    now = utc_now()
    row = repository.insert_resource(
        db_session=db_session,
        project_id=project_id,
        kind=kind,
        display_name=display_name,
        description=description,
        identity_hash=identity_hash,
        tags=list(tags or ()),
        attributes=dict(normalized),
        created_at=now,
    )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ResourceEventTopics.REGISTERED,
            payload={
                "resource_id": str(row.resource_id),
                "project_id": project_id,
                "kind": kind,
                "display_name": display_name,
                "identity_hash": identity_hash,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def get_resource(
        *,
        db_session: DbSession,
        resource_id: str
    ) -> ResourceView:
    """
        Return a :class:`ResourceView` or raise.
    """
    row = repository.find_by_id(db_session=db_session, resource_id=resource_id)
    if row is None:
        err_lines = ["Resource not found."]
        err_lines.append("RESOURCE_ID: {}".format(resource_id))
        err_msg = os.linesep.join(err_lines)
        raise ResourceNotFoundError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def list_resources(
        *,
        db_session: DbSession,
        project_id: str,
        kind: Optional[str] = None,
        include_retired: bool = False
    ) -> List[ResourceView]:
    """
        List resources with optional filters.
    """
    rows = repository.list_by_project(
        db_session=db_session,
        project_id=project_id,
        kind=kind,
        include_retired=include_retired,
    )
    rtnval = [_to_view(row=row) for row in rows]
    return rtnval


def transition_state(
        *,
        db_session: DbSession,
        resource_id: str,
        new_state: ResourceState,
        actor: str = "system:test"
    ) -> ResourceView:
    """
        Apply a permitted state transition. Idempotent on
        same-state moves; raises
        :class:`ResourceStateTransitionError` otherwise.
    """
    row = repository.find_by_id(db_session=db_session, resource_id=resource_id)
    if row is None:
        err_lines = ["Resource not found."]
        err_lines.append("RESOURCE_ID: {}".format(resource_id))
        err_msg = os.linesep.join(err_lines)
        raise ResourceNotFoundError(err_msg) from None

    from_state = row.state
    if from_state == new_state:
        rtnval = _to_view(row=row)
        return rtnval

    if (from_state, new_state) not in _PERMITTED_TRANSITIONS:
        err_lines = ["Resource state transition not permitted."]
        err_lines.append("RESOURCE_ID: {}".format(resource_id))
        err_lines.append("FROM: {}".format(from_state.value))
        err_lines.append("TO: {}".format(new_state.value))
        err_msg = os.linesep.join(err_lines)
        raise ResourceStateTransitionError(err_msg) from None

    now = utc_now()
    repository.update_state(
        db_session=db_session, row=row, new_state=new_state, updated_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ResourceEventTopics.STATE_CHANGED,
            payload={
                "resource_id": str(row.resource_id),
                "project_id": str(row.project_id),
                "from_state": from_state.value,
                "to_state": new_state.value,
                "actor": actor,
            },
            source_event_id=new_uuid(),
        ),
    )
    if new_state == ResourceState.RETIRED:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ResourceEventTopics.RETIRED,
                payload={
                    "resource_id": str(row.resource_id),
                    "project_id": str(row.project_id),
                },
                source_event_id=new_uuid(),
            ),
        )
    elif new_state == ResourceState.QUARANTINED:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ResourceEventTopics.QUARANTINED,
                payload={
                    "resource_id": str(row.resource_id),
                    "project_id": str(row.project_id),
                },
                source_event_id=new_uuid(),
            ),
        )
    elif from_state == ResourceState.QUARANTINED and new_state == ResourceState.AVAILABLE:
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ResourceEventTopics.UNQUARANTINED,
                payload={
                    "resource_id": str(row.resource_id),
                    "project_id": str(row.project_id),
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.commit()

    rtnval = _to_view(row=row)
    return rtnval


def _resolve_kind(*, kind: str):
    """
        Find the registered :class:`ResourceKindProtocol` whose
        ``kind_name`` matches.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=RESOURCE_KIND_PROTOCOL,
    )
    for impl in candidates:
        try:
            if impl.kind_name() == kind:
                return impl
        except NotImplementedError:
            continue
    err_lines = ["No resource_kind implementation registered for kind."]
    err_lines.append("KIND: {}".format(kind))
    err_lines.append("REGISTERED: ({})".format(len(candidates)))
    err_msg = os.linesep.join(err_lines)
    raise ResourceKindUnknownError(err_msg) from None


def _to_view(*, row: Resource) -> ResourceView:
    """
        Convert an ORM row to the read-model.
    """
    rtnval = ResourceView(
        resource_id=str(row.resource_id),
        project_id=str(row.project_id),
        kind=row.kind,
        display_name=row.display_name,
        description=row.description,
        identity_hash=row.identity_hash,
        state=row.state,
        tags=tuple(row.tags or ()),
        attributes=dict(row.attributes or {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
    return rtnval
