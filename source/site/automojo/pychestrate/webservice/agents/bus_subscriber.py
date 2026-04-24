"""
.. module:: agents.bus_subscriber
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus subscribers for Layer-3 agent features (M2).

.. moduleauthor:: Automation Mojo LLC

Wires:

- ``entity.client.heartbeat`` / ``entity.client.liveness_changed`` /
  ``entity.client.capabilities_applied`` → inventory change log.
- ``entity.client.heartbeat`` → post-upgrade version detection for
  outstanding rollout offers.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Callable

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.agents.inventory_service import (
    log_inventory_change,
)
from automojo.pychestrate.webservice.agents.models import (
    AgentUpgradeOffer,
    UpgradeOfferOutcome,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe


SessionFactory = Callable[[], DbSession]


def wire_bus_subscribers(*, session_factory: SessionFactory) -> None:
    """
        Register every Layer-3 agent subscriber.
    """
    subscribe(
        topic="entity.client.heartbeat",
        subscriber=_build_inventory_handler(session_factory=session_factory, change_kind="heartbeat"),
    )
    subscribe(
        topic="entity.client.liveness_changed",
        subscriber=_build_inventory_handler(session_factory=session_factory, change_kind="liveness"),
    )
    subscribe(
        topic="entity.client.capabilities_applied",
        subscriber=_build_inventory_handler(session_factory=session_factory, change_kind="capabilities"),
    )
    subscribe(
        topic="entity.client.heartbeat",
        subscriber=_build_upgrade_heartbeat_handler(session_factory=session_factory),
    )
    return


def _build_inventory_handler(*, session_factory: SessionFactory, change_kind: str):
    """
        Append-only :class:`ClientInventoryChangeLog` emitter.
    """
    def _handler(event: EntityEvent) -> None:
        payload = event.payload or {}
        client_id = payload.get("client_id", None)
        if client_id is None:
            return
        session = session_factory()
        try:
            log_inventory_change(
                db_session=session,
                client_id=client_id,
                project_id=payload.get("project_id", None),
                change_kind=change_kind,
                payload_summary=dict(payload),
            )
        finally:
            session.close()
        return
    return _handler


def _build_upgrade_heartbeat_handler(*, session_factory: SessionFactory):
    """
        On a heartbeat whose ``agent_version`` matches an OFFERED rollout
        version, mark the offer SUCCEEDED.
    """
    def _handler(event: EntityEvent) -> None:
        payload = event.payload or {}
        client_id = payload.get("client_id", None)
        agent_version = payload.get("agent_version", None)
        if client_id is None or agent_version is None:
            return
        session = session_factory()
        try:
            offers = session.query(AgentUpgradeOffer).filter(
                AgentUpgradeOffer.client_id == client_id,
            ).filter(
                AgentUpgradeOffer.outcome == UpgradeOfferOutcome.OFFERED,
            ).all()
            for offer in offers:
                if offer.version != agent_version:
                    continue
                from automojo.pychestrate.webservice.agents.upgrade_service import (
                    record_upgrade_outcome,
                )
                record_upgrade_outcome(
                    db_session=session, offer_id=str(offer.offer_id),
                    outcome=UpgradeOfferOutcome.SUCCEEDED,
                    detail="detected via heartbeat",
                )
        finally:
            session.close()
        return
    return _handler
