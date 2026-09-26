"""
.. module:: pods.static_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-static-pods register/deregister service surface.

.. moduleauthor:: Code Craft AI LLC

A pod becomes a dispatch candidate only while it has a ``REGISTERED``
:class:`PodRegistration` naming its client. The enrollment service
creates that registration when a client redeems its enrollment token
(:func:`bind_enrolled_client`): the token names the pod, so a freshly
enrolled client is eligible for work without any further step. A pod
the operator never defined is created as a static pod with no members.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import json
import os

from typing import Any, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.pods.definitions_service import (
    create_pod_definition,
    read_pod_definition,
    read_pod_definition_version,
)
from ccai.pychestrate.webservice.pods.events import StaticPodEventTopics
from ccai.pychestrate.webservice.pods.exceptions import (
    PodRegistrationRejectedError,
)
from ccai.pychestrate.webservice.pods.models import (
    PodDefinition,
    PodRegistration,
    RegistrationState,
)


#: Actor recorded on the registrations client enrollment creates.
ENROLLMENT_REGISTRATION_ACTOR: str = "client-enrollment"

#: Spec of the static pod created when a client enrolls for a pod
#: name no pod definition carries yet.
ENROLLMENT_POD_SPEC: Mapping[str, Any] = {"members": []}

#: Registration states that bind a pod to a client (a lost client
#: still owns its pod until it recovers or is replaced).
_ACTIVE_REGISTRATION_STATES = (RegistrationState.REGISTERED, RegistrationState.CLIENT_LOST)


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


def bind_enrolled_client(
        *,
        db_session: DbSession,
        project_id: str,
        pod_name: str,
        client_id: str,
        actor: Optional[str] = ENROLLMENT_REGISTRATION_ACTOR
    ) -> PodRegistration:
    """
        Register a freshly enrolled client as the client of the pod its
        enrollment token names, so the pod becomes a dispatch
        candidate.

        * The pod is the definition named ``pod_name`` in
          ``project_id``. When the operator never defined it, a static
          pod with no members is created; a soft-deleted definition of
          that name is restored, because the operator minted a token
          for it.
        * A pod has one client: any other client's active registration
          on the pod (``REGISTERED`` or ``CLIENT_LOST``) is
          deregistered.
        * The client gets a ``REGISTERED`` registration against the
          pod's current definition version. Enrollment carries no
          member report, so the definition's declared members are
          recorded as the report.

        Nothing is committed: the caller commits (the enrollment
        service commits the client, its certificate and this binding
        together). The ``entity.pod.registered`` event publishes on
        that commit and drives the pod lifecycle to ``READY``.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Project the enrollment token is scoped to.
        :param pod_name: Pod the enrollment token names.
        :param client_id: The enrolled client's UUID.
        :param actor: Actor recorded on the registration events.

        :returns: The client's active :class:`PodRegistration`.
    """
    definition = _find_or_create_pod_definition(
        db_session=db_session, project_id=project_id, pod_name=pod_name,
    )
    pod_id = str(definition.pod_id)

    active_rows = (
        db_session.query(PodRegistration)
        .filter(PodRegistration.pod_id == pod_id)
        .filter(PodRegistration.state.in_(_ACTIVE_REGISTRATION_STATES))
        .all()
    )

    existing: Optional[PodRegistration] = None
    now = utc_now()
    for row in active_rows:
        if str(row.client_id) == str(client_id) and row.state == RegistrationState.REGISTERED:
            existing = row
            continue
        row.state = RegistrationState.DEREGISTERED
        row.deregistered_at = now
        row.deregister_reason = "superseded by the enrollment of client {}".format(client_id)
        db_session.add(row)
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=StaticPodEventTopics.POD_DEREGISTERED,
                payload={
                    "pod_id": pod_id,
                    "registration_id": str(row.registration_id),
                    "reason": row.deregister_reason,
                    "actor": actor,
                },
                source_event_id=new_uuid(),
            ),
        )

    if existing is not None:
        db_session.flush()
        rtnval = existing
        return rtnval

    version = read_pod_definition_version(
        db_session=db_session, pod_id=pod_id, version=int(definition.current_version),
    )
    declared_members = []
    spec_members = version.spec_json.get("members", []) if version.spec_json else []
    for entry in spec_members or []:
        if isinstance(entry, Mapping) is True:
            declared_members.append(dict(entry))

    report_bytes = json.dumps(declared_members, sort_keys=True, default=str).encode("utf-8")
    report_hash = hashlib.sha256(report_bytes).hexdigest()

    registration = PodRegistration(
        registration_id=new_uuid(),
        pod_id=pod_id,
        pod_definition_version=int(definition.current_version),
        client_id=client_id,
        state=RegistrationState.REGISTERED,
        report_hash=report_hash,
        report_json={"members": declared_members, "source": "enrollment"},
        registered_at=now,
        last_report_at=now,
        deregistered_at=None,
        deregister_reason=None,
        client_lost_at=None,
    )
    db_session.add(registration)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=StaticPodEventTopics.POD_REGISTERED,
            payload={
                "pod_id": pod_id,
                "registration_id": str(registration.registration_id),
                "pod_definition_version": registration.pod_definition_version,
                "client_id": str(client_id),
                "report_hash": report_hash,
                "actor": actor,
            },
            source_event_id=new_uuid(),
        ),
    )

    rtnval = registration
    return rtnval


def _find_or_create_pod_definition(
        *,
        db_session: DbSession,
        project_id: str,
        pod_name: str
    ) -> PodDefinition:
    """
        Return the pod definition named ``pod_name`` in ``project_id``,
        restoring a soft-deleted one, or create an empty static pod
        (flushed, not committed).

        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.
        :param pod_name: Pod name.

        :returns: The :class:`PodDefinition`.
    """
    definition = (
        db_session.query(PodDefinition)
        .filter(PodDefinition.project_id == project_id)
        .filter(PodDefinition.pod_name == pod_name)
        .first()
    )
    if definition is not None:
        if definition.deleted_at is not None:
            definition.deleted_at = None
            db_session.add(definition)
            db_session.flush()
        rtnval = definition
        return rtnval

    rtnval = create_pod_definition(
        db_session=db_session,
        project_id=project_id,
        pod_name=pod_name,
        spec=dict(ENROLLMENT_POD_SPEC),
        actor_user_id=None,
        commit=False,
    )
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


def deregister_client(
        *,
        db_session: DbSession,
        client_id: str,
        reason: str,
        actor: Optional[str]
    ) -> int:
    """
        Deregister every active registration (``REGISTERED`` or
        ``CLIENT_LOST``) the client holds, so it stops being a dispatch
        candidate. Used when a client is revoked: its registration used
        to stay ``REGISTERED``, so the dispatcher kept choosing a pod
        whose certificate is refused.

        Nothing is committed: the caller commits (revocation commits
        the client status, the revocation row and this together).

        :param db_session: Active SQLAlchemy session.
        :param client_id: The client UUID.
        :param reason: Recorded as each registration's deregister reason.
        :param actor: Actor recorded on the ``entity.pod.deregistered``
                      events.

        :returns: How many registrations were deregistered.
    """
    active_rows = (
        db_session.query(PodRegistration)
        .filter(PodRegistration.client_id == str(client_id))
        .filter(PodRegistration.state.in_(_ACTIVE_REGISTRATION_STATES))
        .all()
    )
    now = utc_now()
    for row in active_rows:
        row.state = RegistrationState.DEREGISTERED
        row.deregistered_at = now
        row.deregister_reason = reason
        db_session.add(row)
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=StaticPodEventTopics.POD_DEREGISTERED,
                payload={
                    "pod_id": str(row.pod_id),
                    "registration_id": str(row.registration_id),
                    "reason": reason,
                    "actor": actor,
                },
                source_event_id=new_uuid(),
            ),
        )
    db_session.flush()
    rtnval = len(active_rows)
    return rtnval


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
