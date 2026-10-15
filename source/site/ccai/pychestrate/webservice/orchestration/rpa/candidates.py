"""
.. module:: orchestration.rpa.candidates
    :synopsis: Eligible-pod selection for RPA dispatch.

.. moduleauthor:: Code Craft AI LLC

RPA specifications may live under a consumer-UI project (integer id)
or an orchestration project (UUID). Pods are enrolled against
orchestration projects only, so candidate selection works in three
tiers:

1. ``target_pod_id`` set on the specification -- that pod's REGISTERED
   client registrations.
2. A UUID-shaped project -- every REGISTERED registration on a pod
   enrolled in that project (the build orchestrator's rule).
3. Otherwise -- every REGISTERED registration in the deployment; the
   dispatch strategy and the job type's ``capability_requirements``
   narrow the choice.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, List, Optional

from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.agents.models import ClientCapability
from ccai.pychestrate.webservice.pods.models import (
    PodDefinition,
    PodRegistration,
    RegistrationState,
)


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def capability_tags_for_client(*, db_session: Any, client_id: str) -> tuple:
    """
        Flatten a client's advertised capabilities into matcher tags:
        every capability ``kind`` plus, for the ``rpa`` kind, one
        ``rpa:<job_type>`` tag per advertised job type and any free-form
        ``tags`` the client listed.
    """
    tags: List[str] = []
    try:
        rows = (
            db_session.query(ClientCapability)
            .filter(ClientCapability.client_id == str(client_id))
            .all()
        )
    except Exception:
        rows = []
    for row in rows:
        kind = str(getattr(row, "kind", "") or "")
        if len(kind) > 0 and kind not in tags:
            tags.append(kind)
        value_json = getattr(row, "value_json", None)
        value = value_json.get("value") if isinstance(value_json, dict) else None
        if kind == "rpa" and isinstance(value, dict):
            for job_type in value.get("job_types", []) or []:
                label = "rpa:{}".format(job_type)
                if label not in tags:
                    tags.append(label)
            for tag in value.get("tags", []) or []:
                if str(tag) not in tags:
                    tags.append(str(tag))
    rtnval = tuple(tags)
    return rtnval


def _candidates_from_registrations(registrations: List[Any], *, db_session: Any = None) -> List[DispatchCandidate]:
    rtnval: List[DispatchCandidate] = []
    for reg in registrations:
        client_id = getattr(reg, "client_id", None)
        pod_id = getattr(reg, "pod_id", None)
        if client_id is None or pod_id is None:
            continue
        if db_session is not None:
            from ccai.pychestrate.webservice.pods.lifecycle_service import accepts_new_work  # noqa: E402

            if accepts_new_work(db_session=db_session, pod_id=str(pod_id)) is False:
                continue
        tags: tuple = tuple()
        raw_tags = getattr(reg, "capability_tags", None)
        if isinstance(raw_tags, (list, tuple)):
            tags = tuple(str(t) for t in raw_tags)
        elif db_session is not None:
            tags = capability_tags_for_client(db_session=db_session, client_id=str(client_id))
        rtnval.append(
            DispatchCandidate(
                client_id=str(client_id),
                pod_id=str(pod_id),
                capability_tags=tags,
                inflight_dispatch_count=0,
                last_dispatched_at_iso="",
            )
        )
    return rtnval


def resolve_dispatch_candidates(
        *,
        db_session: Any,
        project_id: str,
        target_pod_id: Optional[str] = None
    ) -> List[DispatchCandidate]:
    """
        Enumerate eligible dispatch candidates for an RPA job.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Project reference (int or UUID string).
        :param target_pod_id: Optional pod pin from the specification.

        :returns: Possibly-empty candidate list.
    """
    if target_pod_id is not None and len(str(target_pod_id)) > 0 and _is_uuid(target_pod_id):
        registrations = (
            db_session.query(PodRegistration)
            .filter(PodRegistration.pod_id == str(target_pod_id))
            .filter(PodRegistration.state == RegistrationState.REGISTERED)
            .all()
        )
        rtnval = _candidates_from_registrations(list(registrations), db_session=db_session)
        return rtnval

    if _is_uuid(project_id):
        pod_rows = (
            db_session.query(PodDefinition)
            .filter(PodDefinition.project_id == str(project_id))
            .all()
        )
        registrations: List[Any] = []
        for pod_row in pod_rows:
            rows = (
                db_session.query(PodRegistration)
                .filter(PodRegistration.pod_id == str(pod_row.pod_id))
                .filter(PodRegistration.state == RegistrationState.REGISTERED)
                .all()
            )
            registrations.extend(list(rows))
        if len(registrations) > 0:
            rtnval = _candidates_from_registrations(registrations, db_session=db_session)
            return rtnval

    registrations = (
        db_session.query(PodRegistration)
        .filter(PodRegistration.state == RegistrationState.REGISTERED)
        .all()
    )
    rtnval = _candidates_from_registrations(list(registrations), db_session=db_session)
    return rtnval
