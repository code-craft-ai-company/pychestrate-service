"""
.. module:: pods.scoped_config_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-pod-scoped-config service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event
from automojo.pychestrate.webservice.pods.events import PodScopedConfigEventTopics
from automojo.pychestrate.webservice.pods.models import PodRunVariable, PodScopedBearer


def set_scoped_variable(
        *,
        db_session: DbSession,
        run_id: str,
        pod_id: str,
        name: str,
        value: Any,
        value_schema: Optional[Mapping[str, Any]],
        locked: bool,
        actor_user_id: Optional[str]
    ) -> PodRunVariable:
    """
        Upsert a run-scoped variable binding.
    """
    if name is None or len(name.strip()) == 0:
        raise SemanticError("set_scoped_variable requires a non-empty name")

    existing = (
        db_session.query(PodRunVariable)
        .filter(PodRunVariable.run_id == run_id)
        .filter(PodRunVariable.pod_id == pod_id)
        .filter(PodRunVariable.name == name.strip())
        .first()
    )
    now = utc_now()

    if existing is not None:
        if bool(existing.locked) is True:
            err_msg_lines = ["Cannot overwrite a locked pod-run variable."]
            err_msg_lines.append("RUN: {}".format(run_id))
            err_msg_lines.append("POD: {}".format(pod_id))
            err_msg_lines.append("NAME: {}".format(name))
            err_msg = os.linesep.join(err_msg_lines)
            raise SemanticError(err_msg)

        existing.value_json = {"value": value}
        existing.value_schema = dict(value_schema) if value_schema is not None else None
        existing.locked = bool(locked)
        existing.set_by = actor_user_id
        existing.set_at = now
        db_session.add(existing)
        persisted = existing
    else:
        persisted = PodRunVariable(
            variable_id=new_uuid(),
            run_id=run_id,
            pod_id=pod_id,
            name=name.strip(),
            value_json={"value": value},
            value_schema=dict(value_schema) if value_schema is not None else None,
            locked=bool(locked),
            set_by=actor_user_id,
            set_at=now,
        )
        db_session.add(persisted)

    db_session.flush()

    event_payload = {
        "variable_id": str(persisted.variable_id),
        "run_id": str(run_id),
        "pod_id": str(pod_id),
        "name": persisted.name,
        "actor_user_id": actor_user_id,
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PodScopedConfigEventTopics.SCOPED_VARIABLE_SET,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    rtnval = persisted
    return rtnval


def delete_scoped_variable(
        *,
        db_session: DbSession,
        run_id: str,
        pod_id: str,
        name: str,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Delete a single run-scoped variable.
    """
    row = (
        db_session.query(PodRunVariable)
        .filter(PodRunVariable.run_id == run_id)
        .filter(PodRunVariable.pod_id == pod_id)
        .filter(PodRunVariable.name == name)
        .first()
    )
    if row is None:
        return

    db_session.delete(row)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PodScopedConfigEventTopics.SCOPED_VARIABLE_DELETED,
            payload={
                "run_id": str(run_id), "pod_id": str(pod_id),
                "name": name, "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def purge_for_run(*, db_session: DbSession, run_id: str) -> int:
    """
        Remove every scoped variable tied to ``run_id``. Subscriber to
        ``entity.pod.state_changed{to=released}``.

        :returns: Count of removed rows.
    """
    query = db_session.query(PodRunVariable).filter(PodRunVariable.run_id == run_id)
    removed = query.delete(synchronize_session=False)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=PodScopedConfigEventTopics.SCOPED_PURGED,
            payload={"run_id": str(run_id), "removed_count": int(removed)},
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return int(removed)


def issue_bearer(
        *,
        db_session: DbSession,
        run_id: str,
        pod_id: str,
        secret_ref: str,
        policy: Mapping[str, Any],
        expires_at=None
    ) -> PodScopedBearer:
    """
        Issue a :class:`PodScopedBearer` attesting that the target run
        is allowed to dereference a secret via the pod-scoped grant
        policy.
    """
    if secret_ref is None or len(secret_ref.strip()) == 0:
        raise SemanticError("issue_bearer requires a non-empty secret_ref")

    row = PodScopedBearer(
        bearer_id=new_uuid(),
        run_id=run_id,
        pod_id=pod_id,
        secret_ref=secret_ref.strip(),
        policy=dict(policy or {}),
        issued_at=utc_now(),
        expires_at=expires_at,
        consumed=False,
    )
    db_session.add(row)
    db_session.flush()
    db_session.commit()
    return row


def resolve_pod_run_variable(
        *,
        db_session: DbSession,
        run_id: str,
        pod_id: str,
        name: str
    ) -> Any:
    """
        Resolver-chain hook: prefer pod-run values, fall back to the
        Layer-2 variable resolver.
    """
    row = (
        db_session.query(PodRunVariable)
        .filter(PodRunVariable.run_id == run_id)
        .filter(PodRunVariable.pod_id == pod_id)
        .filter(PodRunVariable.name == name)
        .first()
    )
    if row is not None and isinstance(row.value_json, Mapping) is True:
        rtnval = row.value_json.get("value", None)
        return rtnval

    from automojo.pychestrate.webservice.variables import service as variable_service

    rtnval = variable_service.resolve_effective(
        db_session=db_session,
        name=name,
        project_id=None,
        pipeline_id=None,
        job_id=None,
        dereference_secrets=False,
    )
    return rtnval


def list_scoped_variables(
        *,
        db_session: DbSession,
        run_id: str,
        pod_id: Optional[str]
    ) -> List[PodRunVariable]:
    """
        List all scoped variables for a run (optionally per pod).
    """
    query = db_session.query(PodRunVariable).filter(PodRunVariable.run_id == run_id)
    if pod_id is not None:
        query = query.filter(PodRunVariable.pod_id == pod_id)
    query = query.order_by(PodRunVariable.name.asc())
    rtnval = query.all()
    return rtnval
