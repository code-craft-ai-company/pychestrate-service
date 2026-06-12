"""
.. module:: extensions.sandbox.service
    :synopsis: Sandbox facade — grant / revoke / reload / read.

M1 ships:

* :func:`grant_capability` — admin-side grant. Persists a
  ledger row + adds the capability to the in-memory authority
  + emits ``extension.capability_granted``.
* :func:`revoke_capability` — admin-side revoke. Stamps
  ``revoked_at`` + drops the in-memory bit + emits
  ``extension.capability_revoked``.
* :func:`reload_authority_from_db` — load every active grant
  from the ledger into the in-memory authority. Called at
  service start; the M2 hot-reload subscriber re-invokes on
  ``extension.reloaded``.
* :func:`list_grants_for_extension` — read helper.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.sandbox import repository
from ccai.pychestrate.webservice.extensions.sandbox.authority import (
    CAPABILITY_VOCABULARY,
    CapabilityAuthority,
    CapabilityGrantSource,
    get_capability_authority,
)
from ccai.pychestrate.webservice.extensions.sandbox.errors import (
    UnknownCapabilityError,
)
from ccai.pychestrate.webservice.extensions.sandbox.events import (
    SandboxEventTopics,
)
from ccai.pychestrate.webservice.extensions.sandbox.models import (
    ExtensionCapabilityGrant,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


@dataclass(frozen=True)
class CapabilityGrantView:
    """
        Caller-facing read-model.
    """
    ext_name: str
    capability: str
    source: str
    granted_at: datetime
    granted_by: Optional[str]
    revoked_at: Optional[datetime]
    revoked_by: Optional[str]
    revoked_reason: Optional[str]
    is_active: bool


def grant_capability(
        *,
        db_session: DbSession,
        ext_name: str,
        capability: str,
        source: CapabilityGrantSource = CapabilityGrantSource.ADMIN,
        actor_id: Optional[str] = None
    ) -> CapabilityGrantView:
    """
        Persist an active grant + add the capability to the
        in-memory authority. Idempotent on a previously-active
        grant. Reviving a previously-revoked grant clears the
        revoked-* columns.

        :raises: UnknownCapabilityError when the capability is
                 not in the closed vocabulary.
    """
    if capability not in CAPABILITY_VOCABULARY:
        err_lines = ["Unknown capability."]
        err_lines.append("CAPABILITY: {!r}".format(capability))
        err_lines.append("VOCABULARY: {}".format(
            ", ".join(sorted(CAPABILITY_VOCABULARY)),
        ))
        err_msg = os.linesep.join(err_lines)
        raise UnknownCapabilityError(err_msg) from None

    if ext_name is None or len(ext_name) == 0:
        err_lines = ["ext_name must be a non-empty string."]
        err_msg = os.linesep.join(err_lines)
        raise UnknownCapabilityError(err_msg) from None

    now = utc_now()
    row = repository.upsert_grant(
        db_session=db_session,
        ext_name=ext_name,
        capability=capability,
        source=source.value,
        granted_by=actor_id,
        granted_at=now,
    )
    authority = get_capability_authority()
    authority.grant_capability_in_memory(
        ext_name=ext_name, capability=capability,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SandboxEventTopics.GRANTED,
            payload={
                "ext_name": ext_name,
                "capability": capability,
                "source": source.value,
                "actor_id": actor_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _grant_to_view(row=row)
    return rtnval


def revoke_capability(
        *,
        db_session: DbSession,
        ext_name: str,
        capability: str,
        actor_id: Optional[str],
        reason: str
    ) -> CapabilityGrantView:
    """
        Stamp ``revoked_at`` on the ledger row + drop the
        in-memory bit + emit ``extension.capability_revoked``.
        Idempotent on already-revoked rows.

        :raises: UnknownCapabilityError when the capability is
                 not in the closed vocabulary or when no row
                 exists for the (ext_name, capability) pair.
    """
    if capability not in CAPABILITY_VOCABULARY:
        err_lines = ["Unknown capability."]
        err_lines.append("CAPABILITY: {!r}".format(capability))
        err_msg = os.linesep.join(err_lines)
        raise UnknownCapabilityError(err_msg) from None

    now = utc_now()
    row = repository.mark_revoked(
        db_session=db_session,
        ext_name=ext_name,
        capability=capability,
        revoked_by=actor_id,
        reason=reason,
        revoked_at=now,
    )
    if row is None:
        err_lines = ["No grant row to revoke."]
        err_lines.append("EXT_NAME: {}".format(ext_name))
        err_lines.append("CAPABILITY: {}".format(capability))
        err_msg = os.linesep.join(err_lines)
        raise UnknownCapabilityError(err_msg) from None

    authority = get_capability_authority()
    authority.revoke_capability_in_memory(
        ext_name=ext_name, capability=capability,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SandboxEventTopics.REVOKED,
            payload={
                "ext_name": ext_name,
                "capability": capability,
                "actor_id": actor_id,
                "reason": reason,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = _grant_to_view(row=row)
    return rtnval


def reload_authority_from_db(
        *,
        db_session: DbSession
    ) -> CapabilityAuthority:
    """
        Load every active grant from the ledger and replace
        the in-memory authority's per-extension active sets.
        Called at service start; the M2 hot-reload path
        re-invokes on ``extension.reloaded``.
    """
    rows = repository.list_active_grants(db_session=db_session)
    bucket: Dict[str, Set[str]] = {}
    for row in rows:
        ext_bucket = bucket.setdefault(row.ext_name, set())
        ext_bucket.add(row.capability)

    authority = get_capability_authority()
    seen_extensions: List[str] = []
    for ext_name, capabilities in bucket.items():
        seen_extensions.append(ext_name)
        authority.replace_active_for_extension(
            ext_name=ext_name, capabilities=capabilities,
        )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=SandboxEventTopics.AUTHORITY_RELOADED,
            payload={
                "extensions_loaded": len(seen_extensions),
                "active_grants": len(rows),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return authority


def list_grants_for_extension(
        *,
        db_session: DbSession,
        ext_name: str,
        active_only: bool = False
    ) -> List[CapabilityGrantView]:
    """
        List ledger rows for an extension. ``active_only`` drops
        revoked rows.
    """
    if active_only is True:
        rows = repository.list_active_for_extension(
            db_session=db_session, ext_name=ext_name,
        )
    else:
        rows = repository.list_all_grants(
            db_session=db_session, ext_name=ext_name,
        )
    rtnval = [_grant_to_view(row=r) for r in rows]
    return rtnval


def _grant_to_view(*, row: ExtensionCapabilityGrant) -> CapabilityGrantView:
    rtnval = CapabilityGrantView(
        ext_name=row.ext_name,
        capability=row.capability,
        source=row.source,
        granted_at=row.granted_at,
        granted_by=str(row.granted_by) if row.granted_by is not None else None,
        revoked_at=row.revoked_at,
        revoked_by=str(row.revoked_by) if row.revoked_by is not None else None,
        revoked_reason=row.revoked_reason,
        is_active=row.revoked_at is None,
    )
    return rtnval
