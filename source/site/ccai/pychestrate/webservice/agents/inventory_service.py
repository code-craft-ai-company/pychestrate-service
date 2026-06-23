"""
.. module:: agents.inventory_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-client-inventory-ui service surface.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, List, Mapping, Optional, Tuple

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.agents.models import (
    ClientCapability,
    ClientInventoryChangeLog,
)


@dataclass(frozen=True)
class ClientInventoryRow:
    """
        One row in an inventory listing.
    """
    client_id: str
    project_id: Optional[str]
    pod_name: Optional[str]
    liveness_state: Optional[str]
    agent_version: Optional[str]
    last_seen: Optional[str]
    capability_kinds: Tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class InventoryPage:
    """
        Paginated inventory response.
    """
    rows: Tuple[ClientInventoryRow, ...]
    total: int
    offset: int
    limit: int


def read_inventory(
        *,
        db_session: DbSession,
        project_id: Optional[str],
        liveness_state: Optional[str],
        offset: int,
        limit: int
    ) -> InventoryPage:
    """
        Return a paginated inventory view. At M1 this joins the existing
        ``clients_clients`` rows with per-client :class:`ClientCapability`
        rows; transport/liveness integration lands in M2.
    """
    # Import here to avoid a circular dependency between layers.
    from ccai.pychestrate.webservice.clients.models import Client

    query = db_session.query(Client)
    if project_id is not None and len(str(project_id).strip()) > 0:
        query = query.filter(Client.project_id == project_id)
    if liveness_state is not None and len(str(liveness_state).strip()) > 0:
        query = query.filter(Client.liveness_state == liveness_state)

    total = query.count()
    clients = query.order_by(Client.enrolled_at.asc()).offset(offset).limit(limit).all()

    rows: List[ClientInventoryRow] = []
    for client in clients:
        cap_kinds_query = db_session.query(ClientCapability.kind).filter(
            ClientCapability.client_id == client.client_id,
        )
        kinds = tuple(sorted({k for (k,) in cap_kinds_query.all()}))

        rows.append(ClientInventoryRow(
            client_id=str(client.client_id),
            project_id=str(client.project_id) if client.project_id is not None else None,
            pod_name=client.pod_name,
            liveness_state=client.liveness_state.value if client.liveness_state is not None else None,
            agent_version=client.last_agent_version,
            last_seen=client.last_seen.isoformat() if client.last_seen is not None else None,
            capability_kinds=kinds,
        ))

    rtnval = InventoryPage(
        rows=tuple(rows),
        total=int(total),
        offset=int(offset),
        limit=int(limit),
    )
    return rtnval


def log_inventory_change(
        *,
        db_session: DbSession,
        client_id: str,
        project_id: Optional[str],
        change_kind: str,
        payload_summary: Mapping[str, Any]
    ) -> ClientInventoryChangeLog:
    """
        Append-only inventory change record.
    """
    row = ClientInventoryChangeLog(
        change_id=new_uuid(),
        client_id=client_id,
        project_id=project_id,
        change_kind=change_kind,
        payload_summary=dict(payload_summary or {}),
        logged_at=utc_now(),
    )
    db_session.add(row)
    db_session.flush()
    db_session.commit()
    return row
