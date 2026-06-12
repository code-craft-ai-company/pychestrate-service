"""
.. module:: pods.dynamic_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: 3-dynamic-pods template + materialization service.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, List, Mapping, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import list_factory_implementations
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.pods.definitions_service import create_pod_definition
from ccai.pychestrate.webservice.pods.events import DynamicPodEventTopics
from ccai.pychestrate.webservice.pods.exceptions import (
    MaterializationError,
    PodTemplateNotFoundError,
)
from ccai.pychestrate.webservice.pods.factories.provisioner import (
    PodProvisionerProtocol,
)
from ccai.pychestrate.webservice.pods.models import (
    DynamicPodMaterialization,
    MaterializationState,
    PodTemplate,
)


def create_pod_template(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        template_kind: str,
        source_json: Mapping[str, Any],
        parameter_schema: Optional[Mapping[str, Any]],
        actor_user_id: Optional[str]
    ) -> PodTemplate:
    """
        Create a new :class:`PodTemplate`.
    """
    if name is None or len(name.strip()) == 0:
        raise SemanticError("create_pod_template requires a non-empty name")
    if template_kind is None or len(template_kind.strip()) == 0:
        raise SemanticError("create_pod_template requires a non-empty template_kind")

    template = PodTemplate(
        template_id=new_uuid(),
        project_id=project_id,
        name=name.strip(),
        template_kind=template_kind.strip(),
        source_version=1,
        source_json=dict(source_json or {}),
        parameter_schema=dict(parameter_schema or {}),
        created_by=actor_user_id,
        created_at=utc_now(),
    )
    try:
        db_session.add(template)
        db_session.flush()
    except IntegrityError:
        err_msg_lines = ["Pod template name already exists in project."]
        err_msg_lines.append("PROJECT: {}".format(project_id))
        err_msg_lines.append("NAME: {}".format(name.strip()))
        err_msg = os.linesep.join(err_msg_lines)
        raise SemanticError(err_msg) from None

    db_session.commit()
    return template


def list_pod_templates(
        *,
        db_session: DbSession,
        project_id: str
    ) -> List[PodTemplate]:
    """
        List templates in a project.
    """
    query = db_session.query(PodTemplate).filter(PodTemplate.project_id == project_id)
    query = query.order_by(PodTemplate.name.asc())
    rtnval = query.all()
    return rtnval


def read_pod_template(
        *,
        db_session: DbSession,
        template_id: str
    ) -> PodTemplate:
    """
        Look up a template by id.
    """
    row = db_session.query(PodTemplate).filter(PodTemplate.template_id == template_id).first()
    if row is None:
        err_msg_lines = ["Pod template not found."]
        err_msg_lines.append("TEMPLATE_ID: {}".format(template_id))
        err_msg = os.linesep.join(err_msg_lines)
        raise PodTemplateNotFoundError(err_msg) from None
    rtnval = row
    return rtnval


def start_materialization(
        *,
        db_session: DbSession,
        template_id: str,
        parameters: Mapping[str, Any],
        actor_user_id: Optional[str]
    ) -> DynamicPodMaterialization:
    """
        Start a new materialization run. The M1 worker path runs inline:
        render → provision → create pod definition → mark READY.
    """
    template = read_pod_template(db_session=db_session, template_id=template_id)
    now = utc_now()

    materialization = DynamicPodMaterialization(
        materialization_id=new_uuid(),
        template_id=template.template_id,
        template_source_version=int(template.source_version),
        parameters_json=dict(parameters or {}),
        rendered_spec_json={},
        pod_id=None,
        state=MaterializationState.PENDING,
        current_step="queued",
        error_summary=None,
        reservation_ids=[],
        requested_by=actor_user_id,
        requested_at=now,
        ready_at=None,
        orphaned_reason=None,
    )
    db_session.add(materialization)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DynamicPodEventTopics.MATERIALIZATION_STARTED,
            payload={
                "materialization_id": str(materialization.materialization_id),
                "template_id": str(template.template_id),
                "actor_user_id": actor_user_id,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()

    try:
        _drive_inline_materialization(
            db_session=db_session,
            materialization=materialization,
            template=template,
            actor_user_id=actor_user_id,
        )
    except Exception as xcpt:  # noqa: BLE001 — purposeful: mark failed
        materialization.state = MaterializationState.FAILED
        materialization.error_summary = str(xcpt)
        db_session.add(materialization)
        db_session.flush()
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=DynamicPodEventTopics.MATERIALIZATION_FAILED,
                payload={
                    "materialization_id": str(materialization.materialization_id),
                    "error": str(xcpt),
                },
                source_event_id=new_uuid(),
            ),
        )
        db_session.commit()
        raise MaterializationError(str(xcpt)) from None

    return materialization


def _drive_inline_materialization(
        *,
        db_session: DbSession,
        materialization: DynamicPodMaterialization,
        template: PodTemplate,
        actor_user_id: Optional[str]
    ) -> None:
    """
        Minimal rendering + provisioning. M2 swaps this for a worker
        loop with proper reservation ordering.
    """
    materialization.state = MaterializationState.RENDERING
    materialization.current_step = "render"
    db_session.add(materialization)
    db_session.flush()

    rendered_spec = _render_spec(
        source=template.source_json if template.source_json is not None else {},
        parameters=materialization.parameters_json if materialization.parameters_json is not None else {},
    )
    materialization.rendered_spec_json = rendered_spec

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DynamicPodEventTopics.MATERIALIZATION_RENDER_OK,
            payload={
                "materialization_id": str(materialization.materialization_id),
                "rendered_member_count": len(rendered_spec.get("members", []) or []),
            },
            source_event_id=new_uuid(),
        ),
    )

    materialization.state = MaterializationState.PROVISIONING
    materialization.current_step = "provision"
    db_session.add(materialization)
    db_session.flush()

    provisioner = _first_registered_provisioner()
    if provisioner is not None:
        provisioner.provision(rendered_spec=rendered_spec)

    definition = create_pod_definition(
        db_session=db_session,
        project_id=template.project_id,
        pod_name="{}-{}".format(template.name, str(materialization.materialization_id)[:8]),
        spec=rendered_spec,
        actor_user_id=actor_user_id,
    )
    materialization.pod_id = definition.pod_id
    materialization.state = MaterializationState.READY
    materialization.current_step = "ready"
    materialization.ready_at = utc_now()
    db_session.add(materialization)
    db_session.flush()

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=DynamicPodEventTopics.MATERIALIZATION_READY,
            payload={
                "materialization_id": str(materialization.materialization_id),
                "pod_id": str(definition.pod_id),
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def _render_spec(
        *,
        source: Mapping[str, Any],
        parameters: Mapping[str, Any]
    ) -> Mapping[str, Any]:
    """
        M1 rendering: recursively substitute ``$param.name`` placeholders
        with matching parameter values. Jinja2 lands in M2.
    """

    def _substitute(node: Any) -> Any:
        if isinstance(node, Mapping) is True:
            rtnval_node = {k: _substitute(v) for k, v in node.items()}
            return rtnval_node
        if isinstance(node, list) is True:
            rtnval_node = [_substitute(v) for v in node]
            return rtnval_node
        if isinstance(node, str) is True and node.startswith("$param.") is True:
            key = node[len("$param."):]
            if key in parameters:
                return parameters[key]
        return node

    rendered = _substitute(dict(source) if source is not None else {})
    rtnval = rendered if isinstance(rendered, Mapping) is True else {}
    return rtnval


def _first_registered_provisioner():
    """
        Return the highest-priority registered provisioner or None.
    """
    impls = list_factory_implementations(factory_protocol_name="pod_provisioner")
    if len(impls) == 0:
        return None
    rtnval = impls[0]
    return rtnval
