"""
.. module:: agents.capability_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-client-capability-advertisement service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json
import os

from typing import Any, Dict, List, Mapping, Optional, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.agents.events import CapabilityEventTopics
from automojo.pychestrate.webservice.agents.exceptions import (
    CapabilityRejectedError,
    UnknownCapabilityKindError,
)
from automojo.pychestrate.webservice.agents.extensions.capability_kind import (
    CapabilityKindExtension,
)
from automojo.pychestrate.webservice.agents.models import ClientCapability
from automojo.pychestrate.webservice.extensions.registry import list_resource_extensions
from automojo.pychestrate.webservice.hardening.collisions import check_unique_identifiers
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


def apply_advertisement(
        *,
        db_session: DbSession,
        client_id: str,
        advertisements: List[Mapping[str, Any]],
        actor_user_id: Optional[str]
    ) -> List[ClientCapability]:
    """
        Replace a client's capability rows with ``advertisements``.

        Each entry must be of shape ``{"kind": str, "value": Any}``.

        :raises: UnknownCapabilityKindError, CapabilityRejectedError
    """
    registry = _load_kind_registry()

    validated: List[Dict[str, Any]] = []
    for index, entry in enumerate(advertisements or []):
        if isinstance(entry, Mapping) is False:
            err_msg = "advertisements[{}] must be a mapping".format(index)
            raise CapabilityRejectedError(err_msg)
        kind = entry.get("kind", "")
        value = entry.get("value", None)
        pack = registry.get(kind, None)
        if pack is None:
            err_msg_lines = ["Unknown capability kind."]
            err_msg_lines.append("KIND: {}".format(kind))
            err_msg = os.linesep.join(err_msg_lines)
            raise UnknownCapabilityKindError(err_msg) from None

        validated.append({"kind": kind, "value": value, "sensitive": bool(getattr(pack, "sensitive", False))})

    # Full-replace semantics: delete existing rows first.
    db_session.query(ClientCapability).filter(
        ClientCapability.client_id == client_id,
    ).delete(synchronize_session=False)
    db_session.flush()

    now = utc_now()
    revision_seed = json.dumps(validated, sort_keys=True, default=str).encode("utf-8")
    revision_token = hashlib.sha256(revision_seed).hexdigest()

    persisted: List[ClientCapability] = []
    for entry in validated:
        row = ClientCapability(
            capability_id=new_uuid(),
            client_id=client_id,
            kind=entry["kind"],
            value_json={"value": entry["value"]},
            sensitive_ref=None,
            revision_token=revision_token,
            updated_at=now,
        )
        db_session.add(row)
        persisted.append(row)

    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=CapabilityEventTopics.CAPABILITIES_APPLIED,
            payload={
                "client_id": str(client_id),
                "revision_token": revision_token,
                "kind_count": len(validated),
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return persisted


def list_capabilities_for_client(
        *,
        db_session: DbSession,
        client_id: str,
        include_sensitive: bool
    ) -> List[ClientCapability]:
    """
        Return capabilities for a client, excluding sensitive rows by default.
    """
    registry = _load_kind_registry()

    query = db_session.query(ClientCapability).filter(ClientCapability.client_id == client_id)
    query = query.order_by(ClientCapability.kind.asc())
    rows = query.all()

    rtnval: List[ClientCapability] = []
    for row in rows:
        pack = registry.get(row.kind, None)
        sensitive = bool(getattr(pack, "sensitive", False)) if pack is not None else False
        if sensitive is True and include_sensitive is False:
            continue
        rtnval.append(row)
    return rtnval


def _load_kind_registry() -> Dict[str, Type[CapabilityKindExtension]]:
    """
        Return a ``kind_name → class`` map, verifying uniqueness.
    """
    packs = list_resource_extensions(base_class=CapabilityKindExtension)
    rtnval = check_unique_identifiers(
        packs=packs,
        identifier_attribute="kind_name",
        category_label="CapabilityKindExtension",
    )
    return rtnval
