"""
.. module:: pods.static_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-static-pods register/deregister service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json
import os

from typing import Any, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.pods.definitions_service import (
    read_pod_definition,
    read_pod_definition_version,
)
from automojo.pychestrate.webservice.pods.events import StaticPodEventTopics
from automojo.pychestrate.webservice.pods.exceptions import (
    PodRegistrationRejectedError,
)
from automojo.pychestrate.webservice.pods.models import (
    PodRegistration,
    RegistrationState,
)


def register_static_pod(
        *,
        db_session: DbSession,
        pod_id: str,
        client_id: Optional[str],
        member_reports: List[Mapping[str, Any]],
        actor: Optional[str]
    ) -> PodRegistration:
    """
        Register a static pod against its current definition version.

        :raises: PodDefinitionNotFoundError, PodRegistrationRejectedError
    """
    definition = read_pod_definition(db_session=db_session, pod_id=pod_id)
    version = read_pod_definition_version(
        db_session=db_session, pod_id=pod_id, version=int(definition.current_version),
    )

    spec_member_names = []
    spec_members = version.spec_json.get("members", []) if version.spec_json else []
    for entry in spec_members:
        if isinstance(entry, Mapping) is True:
            spec_member_names.append(entry.get("name", None))

    report_member_names = []
    for member in member_reports or []:
        if isinstance(member, Mapping) is True:
            report_member_names.append(member.get("name", None))

    if sorted([n for n in spec_member_names if n is not None]) != sorted(
            [n for n in report_member_names if n is not None],
        ):
        event_payload = {
            "pod_id": str(pod_id),
            "reason": "member_set_mismatch",
            "spec_members": spec_member_names,
            "reported_members": report_member_names,
        }
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=StaticPodEventTopics.POD_REGISTRATION_REJECTED,
                payload=event_payload,
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()

        err_msg_lines = ["Static-pod registration rejected — member set mismatch."]
        err_msg_lines.append("SPEC: {}".format(spec_member_names))
        err_msg_lines.append("REPORT: {}".format(report_member_names))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodRegistrationRejectedError(err_msg) from None

    now = utc_now()
    report_bytes = json.dumps(list(member_reports or []), sort_keys=True, default=str).encode("utf-8")
    report_hash = hashlib.sha256(report_bytes).hexdigest()

    registration = PodRegistration(
        registration_id=new_uuid(),
        pod_id=pod_id,
        pod_definition_version=int(definition.current_version),
        client_id=client_id,
        state=RegistrationState.REGISTERED,
        report_hash=report_hash,
        report_json={"members": list(member_reports or [])},
        registered_at=now,
        last_report_at=now,
        deregistered_at=None,
        deregister_reason=None,
        client_lost_at=None,
    )
    db_session.add(registration)
    db_session.flush()

    event_payload = {
        "pod_id": str(pod_id),
        "registration_id": str(registration.registration_id),
        "pod_definition_version": registration.pod_definition_version,
        "client_id": str(client_id) if client_id is not None else None,
        "report_hash": report_hash,
        "actor": actor,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=StaticPodEventTopics.POD_REGISTERED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    rtnval = registration
    return rtnval


def deregister_static_pod(
        *,
        db_session: DbSession,
        pod_id: str,
        reason: str,
        actor: Optional[str]
    ) -> None:
    """
        Mark the active registration for a pod as ``DEREGISTERED``.
    """
    active = (
        db_session.query(PodRegistration)
        .filter(PodRegistration.pod_id == pod_id)
        .filter(PodRegistration.state == RegistrationState.REGISTERED)
        .order_by(PodRegistration.registered_at.desc())
        .first()
    )
    if active is None:
        return

    active.state = RegistrationState.DEREGISTERED
    active.deregistered_at = utc_now()
    active.deregister_reason = reason if reason is not None else ""
    db_session.add(active)
    db_session.flush()

    event_payload = {
        "pod_id": str(pod_id),
        "registration_id": str(active.registration_id),
        "reason": reason,
        "actor": actor,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=StaticPodEventTopics.POD_DEREGISTERED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def mark_client_lost(*, db_session: DbSession, pod_id: str) -> None:
    """
        Transition the active registration for ``pod_id`` to ``CLIENT_LOST``.
    """
    active = (
        db_session.query(PodRegistration)
        .filter(PodRegistration.pod_id == pod_id)
        .filter(PodRegistration.state == RegistrationState.REGISTERED)
        .order_by(PodRegistration.registered_at.desc())
        .first()
    )
    if active is None:
        return
    active.state = RegistrationState.CLIENT_LOST
    active.client_lost_at = utc_now()
    db_session.add(active)
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=StaticPodEventTopics.POD_REGISTERED_CLIENT_LOST,
            payload={"pod_id": str(pod_id), "registration_id": str(active.registration_id)},
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def mark_client_recovered(*, db_session: DbSession, pod_id: str) -> None:
    """
        Transition a ``CLIENT_LOST`` registration back to ``REGISTERED``.
    """
    active = (
        db_session.query(PodRegistration)
        .filter(PodRegistration.pod_id == pod_id)
        .filter(PodRegistration.state == RegistrationState.CLIENT_LOST)
        .order_by(PodRegistration.registered_at.desc())
        .first()
    )
    if active is None:
        return
    active.state = RegistrationState.REGISTERED
    active.client_lost_at = None
    active.last_report_at = utc_now()
    db_session.add(active)
    db_session.flush()
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=StaticPodEventTopics.POD_REGISTERED_CLIENT_RECOVERED,
            payload={"pod_id": str(pod_id), "registration_id": str(active.registration_id)},
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def read_active_registration(
        *,
        db_session: DbSession,
        pod_id: str
    ) -> Optional[PodRegistration]:
    """
        Return the currently-active registration row for a pod or None.
    """
    rtnval = (
        db_session.query(PodRegistration)
        .filter(PodRegistration.pod_id == pod_id)
        .filter(PodRegistration.state == RegistrationState.REGISTERED)
        .order_by(PodRegistration.registered_at.desc())
        .first()
    )
    return rtnval


def list_registration_history(
        *,
        db_session: DbSession,
        pod_id: str
    ) -> List[PodRegistration]:
    """
        Return every registration row for a pod, newest first.
    """
    query = db_session.query(PodRegistration).filter(PodRegistration.pod_id == pod_id)
    query = query.order_by(PodRegistration.registered_at.desc())
    rtnval = query.all()
    return rtnval
