"""
.. module:: pods.bus_subscriber
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus subscribers for Layer-3 pod features.

.. moduleauthor:: Automation Mojo LLC

Currently subscribes ``entity.pod.state_changed`` for ``RELEASED`` pods
and purges matching :mod:`pods.scoped_config_service` rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Callable

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, subscribe
from automojo.pychestrate.webservice.pods.events import (
    PodDefinitionEventTopics,
    PodLifecycleEventTopics,
    StaticPodEventTopics,
)
from automojo.pychestrate.webservice.pods import static_service as static_svc
from automojo.pychestrate.webservice.pods.lifecycle_service import (
    LifecycleEventKind,
    apply_transition,
    initialize_pod_state,
)
from automojo.pychestrate.webservice.pods.models import PodState
from automojo.pychestrate.webservice.pods.scoped_config_service import purge_for_run


SessionFactory = Callable[[], DbSession]


def wire_bus_subscribers(*, session_factory: SessionFactory) -> None:
    """
        Register pod-scoped subscribers. M1 only drove scoped-config
        purges; M2 adds lifecycle-wiring from registration / liveness /
        revocation events, and topology-cache invalidation.
    """
    subscribe(
        topic=PodLifecycleEventTopics.POD_STATE_CHANGED,
        subscriber=_build_state_changed_handler(session_factory=session_factory),
    )
    subscribe(
        topic=StaticPodEventTopics.POD_REGISTERED,
        subscriber=_build_pod_registered_handler(session_factory=session_factory),
    )
    subscribe(
        topic=StaticPodEventTopics.POD_DEREGISTERED,
        subscriber=_build_pod_deregistered_handler(session_factory=session_factory),
    )
    subscribe(
        topic="entity.client.liveness_changed",
        subscriber=_build_liveness_handler(session_factory=session_factory),
    )
    subscribe(
        topic="entity.client.revoked",
        subscriber=_build_client_revoked_handler(session_factory=session_factory),
    )
    subscribe(
        topic=PodDefinitionEventTopics.DEFINITION_CREATED,
        subscriber=_build_definition_changed_handler(),
    )
    subscribe(
        topic="entity.pod.definition_deleted",
        subscriber=_build_definition_changed_handler(),
    )
    return


def _build_state_changed_handler(*, session_factory: SessionFactory):
    def _handler(event: EntityEvent) -> None:
        payload = event.payload or {}
        from automojo.pychestrate.webservice.pods.topology_service import (
            invalidate_cache_for_pod,
        )
        pod_id = payload.get("pod_id", None)
        if pod_id is not None:
            invalidate_cache_for_pod(pod_id=pod_id)

        if payload.get("to_state", "") != "RELEASED":
            return
        run_id = payload.get("run_id", None)
        if run_id is None:
            return
        session = session_factory()
        try:
            purge_for_run(db_session=session, run_id=run_id)
        finally:
            session.close()
        return
    return _handler


def _build_pod_registered_handler(*, session_factory: SessionFactory):
    """
        On ``entity.pod.registered``: drive the lifecycle into READY.
    """
    def _handler(event: EntityEvent) -> None:
        payload = event.payload or {}
        pod_id = payload.get("pod_id", None)
        if pod_id is None:
            return
        session = session_factory()
        try:
            initialize_pod_state(db_session=session, pod_id=pod_id)
            try:
                apply_transition(
                    db_session=session, pod_id=pod_id,
                    event_kind=LifecycleEventKind.REGISTERED,
                    event_payload={"registration_id": payload.get("registration_id")},
                    actor=payload.get("actor"),
                )
            except Exception:  # noqa: BLE001 — already-READY pods are fine
                pass
        finally:
            session.close()
        return
    return _handler


def _build_pod_deregistered_handler(*, session_factory: SessionFactory):
    """
        On ``entity.pod.deregistered``: drive DRAIN → DEREGISTER.
    """
    def _handler(event: EntityEvent) -> None:
        payload = event.payload or {}
        pod_id = payload.get("pod_id", None)
        if pod_id is None:
            return
        session = session_factory()
        try:
            for step in (LifecycleEventKind.DRAIN, LifecycleEventKind.DEREGISTER):
                try:
                    apply_transition(
                        db_session=session, pod_id=pod_id,
                        event_kind=step, event_payload={}, actor=payload.get("actor"),
                    )
                except Exception:  # noqa: BLE001 — tolerate non-matching current state
                    continue
        finally:
            session.close()
        return
    return _handler


def _build_liveness_handler(*, session_factory: SessionFactory):
    """
        On ``entity.client.liveness_changed``: mark matching pods
        CLIENT_LOST or recovered.
    """
    def _handler(event: EntityEvent) -> None:
        payload = event.payload or {}
        client_id = payload.get("client_id", None)
        new_state = payload.get("new_state", "")
        if client_id is None:
            return
        session = session_factory()
        try:
            from automojo.pychestrate.webservice.pods.models import (
                PodRegistration,
                RegistrationState,
            )
            affected = session.query(PodRegistration).filter(
                PodRegistration.client_id == client_id,
            ).all()
            for registration in affected:
                pod_id = str(registration.pod_id)
                if new_state == "LOST":
                    static_svc.mark_client_lost(db_session=session, pod_id=pod_id)
                elif new_state == "ALIVE" and registration.state == RegistrationState.CLIENT_LOST:
                    static_svc.mark_client_recovered(db_session=session, pod_id=pod_id)
        finally:
            session.close()
        return
    return _handler


def _build_client_revoked_handler(*, session_factory: SessionFactory):
    """
        On ``entity.client.revoked``: deregister every registration owned
        by the revoked client.
    """
    def _handler(event: EntityEvent) -> None:
        payload = event.payload or {}
        client_id = payload.get("client_id", None)
        if client_id is None:
            return
        session = session_factory()
        try:
            from automojo.pychestrate.webservice.pods.models import PodRegistration
            affected = session.query(PodRegistration).filter(
                PodRegistration.client_id == client_id,
            ).all()
            for registration in affected:
                static_svc.deregister_static_pod(
                    db_session=session, pod_id=str(registration.pod_id),
                    reason="client_revoked", actor=None,
                )
        finally:
            session.close()
        return
    return _handler


def _build_definition_changed_handler():
    """
        Invalidate the topology cache when a definition is created or deleted.
    """
    def _handler(event: EntityEvent) -> None:
        from automojo.pychestrate.webservice.pods.topology_service import (
            invalidate_cache_for_pod,
        )
        payload = event.payload or {}
        pod_id = payload.get("pod_id", None)
        if pod_id is not None:
            invalidate_cache_for_pod(pod_id=pod_id)
        return
    return _handler
