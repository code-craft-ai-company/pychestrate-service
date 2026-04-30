"""
.. module:: pods.restapi.v1.podsblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for Layer-3 pod endpoints.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks. The legacy
colon-action URL ``/pod-templates/{template_id}:materialize`` is
normalized to ``/pod-templates/{template_id}/materialize`` since
webworks does not split path-params on colon-suffixes.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict

from automojo.errors.exceptions import SemanticError

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response
from automojo.webworks.security.accesspolicy import AccessPolicy


_ADMIN_POLICY = AccessPolicy(roles=("system-admin",))
_PROJECT_WRITE = AccessPolicy(
    roles=("system-admin", "project-owner", "project-editor"),
)

from automojo.pychestrate.webservice.dbsessionmiddleware import (
    get_request_actor_user_id,
)
from automojo.pychestrate.webservice.pods.definitions_service import (
    create_pod_definition,
    list_pod_definitions,
    read_pod_definition,
    read_pod_definition_version,
)
from automojo.pychestrate.webservice.pods.dynamic_service import (
    create_pod_template,
    list_pod_templates,
    start_materialization,
)
from automojo.pychestrate.webservice.pods.exceptions import (
    MaterializationError,
    MemberKindNotRegisteredError,
    PodDefinitionAlreadyExistsError,
    PodDefinitionNotFoundError,
    PodSpecValidationError,
    PodTemplateNotFoundError,
)
from automojo.pychestrate.webservice.pods.lifecycle_service import (
    read_state,
    read_state_history,
)
from automojo.pychestrate.webservice.pods.scoped_config_service import (
    delete_scoped_variable,
    set_scoped_variable,
)
from automojo.pychestrate.webservice.pods.static_service import (
    list_registration_history,
    read_active_registration,
)
from automojo.pychestrate.webservice.pods.topology_service import (
    compose_topology,
    topology_as_dict,
)


PODS_BASE_PATH = "/api/v1/projects"


def _require_db_session(*, request: Request) -> Any:
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


def _read_json_body(*, request: Request) -> Dict[str, Any]:
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")
    try:
        decoded = request.json()
    except Exception as exc:
        err_msg = "request body must be valid JSON"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object",
        )
    rtnval = decoded
    return rtnval


def _definition_to_dict(*, definition, version) -> Dict[str, Any]:
    if version is not None:
        spec_field = version.spec_json
        spec_hash_field = version.spec_hash
    else:
        spec_field = None
        spec_hash_field = None
    if definition.created_at is not None:
        created_at_field = definition.created_at.isoformat()
    else:
        created_at_field = None
    rtnval = {
        "pod_id": str(definition.pod_id),
        "project_id": str(definition.project_id),
        "pod_name": definition.pod_name,
        "current_version": int(definition.current_version),
        "spec": spec_field,
        "spec_hash": spec_hash_field,
        "created_at": created_at_field,
    }
    return rtnval


class PodsBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 Layer-3 pod endpoints (definitions,
        registration, lifecycle state, topology, dynamic templates,
        scoped run variables).
    """

    base_path = PODS_BASE_PATH
    tags = ["pods", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pod-definitions",
        methods=["POST"],
        doc=Doc(summary="Create pod definition"),
        access_policy=_PROJECT_WRITE,
    )
    def create_pod_definition_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        project_id = request.path_params.get("project_id", "")

        try:
            definition = create_pod_definition(
                db_session=db_session,
                project_id=project_id,
                pod_name=payload.get("pod_name", ""),
                spec=payload.get("spec", {}),
                actor_user_id=actor_user_id,
            )
        except SemanticError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PodSpecValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MemberKindNotRegisteredError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except PodDefinitionAlreadyExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        version = read_pod_definition_version(
            db_session=db_session,
            pod_id=str(definition.pod_id),
            version=int(definition.current_version),
        )
        body = _definition_to_dict(definition=definition, version=version)
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pod-definitions",
        methods=["GET"],
        doc=Doc(summary="List pod definitions"),
    )
    def list_pod_definitions_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        project_id = request.path_params.get("project_id", "")

        definitions = list_pod_definitions(
            db_session=db_session, project_id=project_id,
        )
        entries = []
        for definition in definitions:
            version = read_pod_definition_version(
                db_session=db_session,
                pod_id=str(definition.pod_id),
                version=int(definition.current_version),
            )
            entries.append(
                _definition_to_dict(definition=definition, version=version),
            )
        rtnval = JSONResponse(content=entries, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pod-definitions/{pod_id}",
        methods=["GET"],
        doc=Doc(summary="Read pod definition"),
    )
    def read_pod_definition_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        pod_id = request.path_params.get("pod_id", "")

        try:
            definition = read_pod_definition(
                db_session=db_session, pod_id=pod_id,
            )
            version = read_pod_definition_version(
                db_session=db_session,
                pod_id=pod_id,
                version=int(definition.current_version),
            )
        except PodDefinitionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        body = _definition_to_dict(definition=definition, version=version)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pods/{pod_id}/state",
        methods=["GET"],
        doc=Doc(summary="Read pod state"),
    )
    def read_pod_state(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        pod_id = request.path_params.get("pod_id", "")

        try:
            row = read_state(db_session=db_session, pod_id=pod_id)
        except PodDefinitionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        if row.previous_state is not None:
            previous_field = row.previous_state.value
        else:
            previous_field = None
        if row.last_transition_at is not None:
            last_transition_field = row.last_transition_at.isoformat()
        else:
            last_transition_field = None
        if row.transition_cursor is not None:
            cursor_value = int(row.transition_cursor)
        else:
            cursor_value = 0
        body = {
            "pod_id": str(row.pod_id),
            "state": row.state.value,
            "previous_state": previous_field,
            "last_transition_at": last_transition_field,
            "last_transition_event": row.last_transition_event,
            "transition_cursor": cursor_value,
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pods/{pod_id}/state/history",
        methods=["GET"],
        doc=Doc(summary="List pod state history"),
    )
    def read_pod_state_history(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        pod_id = request.path_params.get("pod_id", "")
        offset = int(request.query_params.get("offset", "0"))
        limit = int(request.query_params.get("limit", "100"))

        rows = read_state_history(
            db_session=db_session, pod_id=pod_id,
            offset=offset, limit=limit,
        )
        entries = []
        for row in rows:
            if row.from_state is not None:
                from_state_field = row.from_state.value
            else:
                from_state_field = None
            if row.applied_at is not None:
                applied_field = row.applied_at.isoformat()
            else:
                applied_field = None
            entries.append({
                "log_id": str(row.log_id),
                "from_state": from_state_field,
                "to_state": row.to_state.value,
                "event_kind": row.event_kind,
                "actor": row.actor,
                "applied_at": applied_field,
            })
        rtnval = JSONResponse(content=entries, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pods/{pod_id}/registration",
        methods=["GET"],
        doc=Doc(summary="Read active pod registration"),
    )
    def read_active_pod_registration(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        pod_id = request.path_params.get("pod_id", "")

        row = read_active_registration(db_session=db_session, pod_id=pod_id)
        if row is None:
            raise HTTPException(
                status_code=404, detail="No active registration",
            )

        if row.client_id is not None:
            client_id_field = str(row.client_id)
        else:
            client_id_field = None
        if row.registered_at is not None:
            registered_field = row.registered_at.isoformat()
        else:
            registered_field = None
        body = {
            "registration_id": str(row.registration_id),
            "pod_id": str(row.pod_id),
            "pod_definition_version": int(row.pod_definition_version),
            "client_id": client_id_field,
            "state": row.state.value,
            "report_hash": row.report_hash,
            "registered_at": registered_field,
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pods/{pod_id}/registrations",
        methods=["GET"],
        doc=Doc(summary="List pod registration history"),
    )
    def list_pod_registrations(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        pod_id = request.path_params.get("pod_id", "")

        rows = list_registration_history(
            db_session=db_session, pod_id=pod_id,
        )
        entries = []
        for row in rows:
            if row.registered_at is not None:
                registered_field = row.registered_at.isoformat()
            else:
                registered_field = None
            if row.deregistered_at is not None:
                deregistered_field = row.deregistered_at.isoformat()
            else:
                deregistered_field = None
            entries.append({
                "registration_id": str(row.registration_id),
                "state": row.state.value,
                "pod_definition_version": int(row.pod_definition_version),
                "registered_at": registered_field,
                "deregistered_at": deregistered_field,
                "deregister_reason": row.deregister_reason,
            })
        rtnval = JSONResponse(content=entries, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pods/{pod_id}/topology",
        methods=["GET"],
        doc=Doc(summary="Read pod topology"),
    )
    def read_pod_topology(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        pod_id = request.path_params.get("pod_id", "")

        try:
            graph = compose_topology(db_session=db_session, pod_id=pod_id)
        except PodDefinitionNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        body = topology_as_dict(graph=graph)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pod-templates",
        methods=["POST"],
        doc=Doc(summary="Create pod template"),
        access_policy=_PROJECT_WRITE,
    )
    def create_pod_template_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        project_id = request.path_params.get("project_id", "")

        try:
            template = create_pod_template(
                db_session=db_session,
                project_id=project_id,
                name=payload.get("name", ""),
                template_kind=payload.get("template_kind", ""),
                source_json=payload.get("source_json", {}),
                parameter_schema=payload.get("parameter_schema", None),
                actor_user_id=actor_user_id,
            )
        except SemanticError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        body = {
            "template_id": str(template.template_id),
            "project_id": str(template.project_id),
            "name": template.name,
            "template_kind": template.template_kind,
            "source_version": int(template.source_version),
        }
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pod-templates",
        methods=["GET"],
        doc=Doc(summary="List pod templates"),
    )
    def list_pod_templates_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        project_id = request.path_params.get("project_id", "")

        rows = list_pod_templates(db_session=db_session, project_id=project_id)
        entries = []
        for row in rows:
            entries.append({
                "template_id": str(row.template_id),
                "name": row.name,
                "template_kind": row.template_kind,
                "source_version": int(row.source_version),
            })
        rtnval = JSONResponse(content=entries, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/pod-templates/{template_id}/materialize",
        methods=["POST"],
        doc=Doc(
            summary="Materialize a pod template",
            description=(
                "Migration note: legacy URL was "
                "``/pod-templates/{template_id}:materialize`` (colon "
                "action verb). Webworks path matching does not split "
                "on colon, so the path is normalized to a slash."
            ),
        ),
        access_policy=_PROJECT_WRITE,
    )
    def materialize_pod_template(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        template_id = request.path_params.get("template_id", "")

        parameters_raw = payload.get("parameters", {})
        if parameters_raw is None:
            parameters_value = {}
        else:
            parameters_value = parameters_raw

        try:
            materialization = start_materialization(
                db_session=db_session,
                template_id=template_id,
                parameters=parameters_value,
                actor_user_id=actor_user_id,
            )
        except PodTemplateNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except MaterializationError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        if materialization.pod_id is not None:
            pod_id_field = str(materialization.pod_id)
        else:
            pod_id_field = None
        body = {
            "materialization_id": str(materialization.materialization_id),
            "template_id": str(materialization.template_id),
            "state": materialization.state.value,
            "pod_id": pod_id_field,
        }
        rtnval = JSONResponse(content=body, status_code=202)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/runs/{run_id}/variables/{name}",
        methods=["PUT"],
        doc=Doc(summary="Set scoped run variable"),
        access_policy=_PROJECT_WRITE,
    )
    def set_run_variable(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        run_id = request.path_params.get("run_id", "")
        name = request.path_params.get("name", "")
        pod_id = request.query_params.get("pod_id", "")

        if len(pod_id.strip()) == 0:
            raise HTTPException(
                status_code=400, detail="Query param 'pod_id' is required",
            )

        try:
            row = set_scoped_variable(
                db_session=db_session,
                run_id=run_id,
                pod_id=pod_id,
                name=name,
                value=payload.get("value", None),
                value_schema=payload.get("value_schema", None),
                locked=bool(payload.get("locked", False)),
                actor_user_id=actor_user_id,
            )
        except SemanticError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        body = {
            "variable_id": str(row.variable_id),
            "run_id": str(row.run_id),
            "pod_id": str(row.pod_id),
            "name": row.name,
            "locked": bool(row.locked),
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/projects/{project_id}/runs/{run_id}/variables/{name}",
        methods=["DELETE"],
        doc=Doc(summary="Delete scoped run variable"),
        access_policy=_PROJECT_WRITE,
    )
    def delete_run_variable(request: Request) -> Response:
        db_session = _require_db_session(request=request)
        actor_user_id = get_request_actor_user_id(request=request)
        run_id = request.path_params.get("run_id", "")
        name = request.path_params.get("name", "")
        pod_id = request.query_params.get("pod_id", "")

        if len(pod_id.strip()) == 0:
            raise HTTPException(
                status_code=400, detail="Query param 'pod_id' is required",
            )

        delete_scoped_variable(
            db_session=db_session,
            run_id=run_id,
            pod_id=pod_id,
            name=name,
            actor_user_id=actor_user_id,
        )
        rtnval = Response(status_code=204, body=b"")
        return rtnval
