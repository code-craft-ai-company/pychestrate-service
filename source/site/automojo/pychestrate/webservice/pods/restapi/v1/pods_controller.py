"""
.. module:: pods.restapi.v1.pods_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controllers for Layer-3 pod specs.

.. moduleauthor:: Automation Mojo LLC

Collates the read/write surface for every Layer-3 pod spec into one
Flask-RestX namespace. Individual spec endpoints:

* ``POST/GET /api/v1/projects/{pid}/pod-definitions[/{pod_id}]``
* ``GET/POST /api/v1/projects/{pid}/pods/{pod_id}/registration(s)``
* ``GET /api/v1/projects/{pid}/pods/{pod_id}/state[/history]``
* ``GET /api/v1/projects/{pid}/pods/{pod_id}/topology``
* ``POST /api/v1/projects/{pid}/pod-templates``
* ``POST .../pod-templates/{template_id}:materialize``
* ``PUT/DELETE /api/v1/projects/{pid}/runs/{rid}/variables/{name}``
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.api.problem_json_flask import abort_with_problem

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
    PodRegistrationRejectedError,
    PodSpecValidationError,
    PodStateTransitionError,
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


PODS_NAMESPACE_PATH = ""


pods_ns = Namespace(
    "Pods v1",
    description="Layer-3 pod features: definitions, lifecycle, static, "
                "topology, scoped-config, dynamic.",
)


pod_definition_create_model = pods_ns.model(
    "PodDefinitionCreate",
    {
        "pod_name": fields.String(required=True),
        "spec": fields.Raw(required=True, description="Pod spec JSON"),
    },
)

pod_template_create_model = pods_ns.model(
    "PodTemplateCreate",
    {
        "name": fields.String(required=True),
        "template_kind": fields.String(required=True),
        "source_json": fields.Raw(required=True),
        "parameter_schema": fields.Raw(required=False),
    },
)

pod_template_materialize_model = pods_ns.model(
    "PodTemplateMaterialize",
    {"parameters": fields.Raw(required=False)},
)

scoped_variable_set_model = pods_ns.model(
    "ScopedVariableSet",
    {
        "value": fields.Raw(required=True),
        "value_schema": fields.Raw(required=False),
        "locked": fields.Boolean(required=False, default=False),
    },
)


def _get_request_db_session():
    from flask import g
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        abort_with_problem(
            status=503, detail="Request-scoped db_session not configured"
        )
    return db_session


def _get_request_actor_user_id():
    from flask import g
    actor = getattr(g, "actor_user_id", None)
    return actor


def _definition_to_dict(definition, version) -> dict:
    rtnval = {
        "pod_id": str(definition.pod_id),
        "project_id": str(definition.project_id),
        "pod_name": definition.pod_name,
        "current_version": int(definition.current_version),
        "spec": version.spec_json if version is not None else None,
        "spec_hash": version.spec_hash if version is not None else None,
        "created_at": definition.created_at.isoformat() if definition.created_at is not None else None,
    }
    return rtnval


@pods_ns.route("/projects/<string:project_id>/pod-definitions")
@pods_ns.param("project_id", "The project id")
class PodDefinitionsResource(Resource):
    """
        POST / GET on the pod-definitions collection.
    """

    @pods_ns.expect(pod_definition_create_model, validate=True)
    def post(self, project_id: str):
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor = _get_request_actor_user_id()

        try:
            definition = create_pod_definition(
                db_session=db_session, project_id=project_id,
                pod_name=payload.get("pod_name", ""),
                spec=payload.get("spec", {}),
                actor_user_id=actor,
            )
        except SemanticError as xcpt:
            abort_with_problem(
                status=400, detail=str(xcpt), instance=request.path,
                extensions={"project_id": project_id},
            )
        except PodSpecValidationError as xcpt:
            abort_with_problem(
                status=400, detail=str(xcpt), instance=request.path,
                extensions={"project_id": project_id},
            )
        except MemberKindNotRegisteredError as xcpt:
            abort_with_problem(
                status=400, detail=str(xcpt), instance=request.path,
                extensions={"project_id": project_id},
            )
        except PodDefinitionAlreadyExistsError as xcpt:
            abort_with_problem(
                status=409, detail=str(xcpt), instance=request.path,
                extensions={
                    "project_id": project_id,
                    "pod_name": payload.get("pod_name", ""),
                },
            )

        version = read_pod_definition_version(
            db_session=db_session, pod_id=str(definition.pod_id),
            version=int(definition.current_version),
        )
        return _definition_to_dict(definition, version), 201

    def get(self, project_id: str):
        db_session = _get_request_db_session()
        definitions = list_pod_definitions(db_session=db_session, project_id=project_id)
        rtnval = []
        for definition in definitions:
            version = read_pod_definition_version(
                db_session=db_session, pod_id=str(definition.pod_id),
                version=int(definition.current_version),
            )
            rtnval.append(_definition_to_dict(definition, version))
        return rtnval


@pods_ns.route("/projects/<string:project_id>/pod-definitions/<string:pod_id>")
@pods_ns.param("project_id", "The project id")
@pods_ns.param("pod_id", "The pod id")
class PodDefinitionDetail(Resource):
    def get(self, project_id: str, pod_id: str):
        db_session = _get_request_db_session()
        try:
            definition = read_pod_definition(db_session=db_session, pod_id=pod_id)
            version = read_pod_definition_version(
                db_session=db_session, pod_id=pod_id, version=int(definition.current_version),
            )
        except PodDefinitionNotFoundError as xcpt:
            abort_with_problem(
                status=404, detail=str(xcpt), instance=request.path,
                extensions={"pod_id": pod_id, "project_id": project_id},
            )
        return _definition_to_dict(definition, version)


@pods_ns.route("/projects/<string:project_id>/pods/<string:pod_id>/state")
@pods_ns.param("project_id", "The project id")
@pods_ns.param("pod_id", "The pod id")
class PodStateResource(Resource):
    def get(self, project_id: str, pod_id: str):
        db_session = _get_request_db_session()
        try:
            row = read_state(db_session=db_session, pod_id=pod_id)
        except PodDefinitionNotFoundError as xcpt:
            abort_with_problem(
                status=404, detail=str(xcpt), instance=request.path,
                extensions={"pod_id": pod_id, "project_id": project_id},
            )
        rtnval = {
            "pod_id": str(row.pod_id),
            "state": row.state.value,
            "previous_state": row.previous_state.value if row.previous_state is not None else None,
            "last_transition_at": row.last_transition_at.isoformat() if row.last_transition_at is not None else None,
            "last_transition_event": row.last_transition_event,
            "transition_cursor": int(row.transition_cursor or 0),
        }
        return rtnval


@pods_ns.route("/projects/<string:project_id>/pods/<string:pod_id>/state/history")
@pods_ns.param("project_id", "The project id")
@pods_ns.param("pod_id", "The pod id")
class PodStateHistoryResource(Resource):
    def get(self, project_id: str, pod_id: str):
        db_session = _get_request_db_session()
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 100))
        rows = read_state_history(
            db_session=db_session, pod_id=pod_id, offset=offset, limit=limit,
        )
        rtnval = [
            {
                "log_id": str(r.log_id),
                "from_state": r.from_state.value if r.from_state is not None else None,
                "to_state": r.to_state.value,
                "event_kind": r.event_kind,
                "actor": r.actor,
                "applied_at": r.applied_at.isoformat() if r.applied_at is not None else None,
            }
            for r in rows
        ]
        return rtnval


@pods_ns.route("/projects/<string:project_id>/pods/<string:pod_id>/registration")
@pods_ns.param("project_id", "The project id")
@pods_ns.param("pod_id", "The pod id")
class PodRegistrationResource(Resource):
    def get(self, project_id: str, pod_id: str):
        db_session = _get_request_db_session()
        row = read_active_registration(db_session=db_session, pod_id=pod_id)
        if row is None:
            abort_with_problem(
                status=404, detail="No active registration",
                instance=request.path,
                extensions={"pod_id": pod_id, "project_id": project_id},
            )
        rtnval = {
            "registration_id": str(row.registration_id),
            "pod_id": str(row.pod_id),
            "pod_definition_version": int(row.pod_definition_version),
            "client_id": str(row.client_id) if row.client_id is not None else None,
            "state": row.state.value,
            "report_hash": row.report_hash,
            "registered_at": row.registered_at.isoformat() if row.registered_at is not None else None,
        }
        return rtnval


@pods_ns.route("/projects/<string:project_id>/pods/<string:pod_id>/registrations")
@pods_ns.param("project_id", "The project id")
@pods_ns.param("pod_id", "The pod id")
class PodRegistrationsHistoryResource(Resource):
    def get(self, project_id: str, pod_id: str):
        db_session = _get_request_db_session()
        rows = list_registration_history(db_session=db_session, pod_id=pod_id)
        rtnval = [
            {
                "registration_id": str(r.registration_id),
                "state": r.state.value,
                "pod_definition_version": int(r.pod_definition_version),
                "registered_at": r.registered_at.isoformat() if r.registered_at is not None else None,
                "deregistered_at": r.deregistered_at.isoformat() if r.deregistered_at is not None else None,
                "deregister_reason": r.deregister_reason,
            }
            for r in rows
        ]
        return rtnval


@pods_ns.route("/projects/<string:project_id>/pods/<string:pod_id>/topology")
@pods_ns.param("project_id", "The project id")
@pods_ns.param("pod_id", "The pod id")
class PodTopologyResource(Resource):
    def get(self, project_id: str, pod_id: str):
        db_session = _get_request_db_session()
        try:
            graph = compose_topology(db_session=db_session, pod_id=pod_id)
        except PodDefinitionNotFoundError as xcpt:
            abort_with_problem(
                status=404, detail=str(xcpt), instance=request.path,
                extensions={"pod_id": pod_id, "project_id": project_id},
            )
        return topology_as_dict(graph=graph)


@pods_ns.route("/projects/<string:project_id>/pod-templates")
@pods_ns.param("project_id", "The project id")
class PodTemplatesResource(Resource):
    @pods_ns.expect(pod_template_create_model, validate=True)
    def post(self, project_id: str):
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor = _get_request_actor_user_id()
        try:
            template = create_pod_template(
                db_session=db_session, project_id=project_id,
                name=payload.get("name", ""),
                template_kind=payload.get("template_kind", ""),
                source_json=payload.get("source_json", {}),
                parameter_schema=payload.get("parameter_schema", None),
                actor_user_id=actor,
            )
        except SemanticError as xcpt:
            abort_with_problem(
                status=400, detail=str(xcpt), instance=request.path,
                extensions={"project_id": project_id},
            )
        rtnval = {
            "template_id": str(template.template_id),
            "project_id": str(template.project_id),
            "name": template.name,
            "template_kind": template.template_kind,
            "source_version": int(template.source_version),
        }
        return rtnval, 201

    def get(self, project_id: str):
        db_session = _get_request_db_session()
        rows = list_pod_templates(db_session=db_session, project_id=project_id)
        rtnval = [
            {
                "template_id": str(r.template_id),
                "name": r.name,
                "template_kind": r.template_kind,
                "source_version": int(r.source_version),
            }
            for r in rows
        ]
        return rtnval


@pods_ns.route("/projects/<string:project_id>/pod-templates/<string:template_id>:materialize")
@pods_ns.param("project_id", "The project id")
@pods_ns.param("template_id", "The template id")
class PodTemplateMaterializeResource(Resource):
    @pods_ns.expect(pod_template_materialize_model, validate=True)
    def post(self, project_id: str, template_id: str):
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor = _get_request_actor_user_id()
        try:
            materialization = start_materialization(
                db_session=db_session, template_id=template_id,
                parameters=payload.get("parameters", {}) or {},
                actor_user_id=actor,
            )
        except PodTemplateNotFoundError as xcpt:
            abort_with_problem(
                status=404, detail=str(xcpt), instance=request.path,
                extensions={
                    "project_id": project_id,
                    "template_id": template_id,
                },
            )
        except MaterializationError as xcpt:
            abort_with_problem(
                status=409, detail=str(xcpt), instance=request.path,
                extensions={
                    "project_id": project_id,
                    "template_id": template_id,
                },
            )
        rtnval = {
            "materialization_id": str(materialization.materialization_id),
            "template_id": str(materialization.template_id),
            "state": materialization.state.value,
            "pod_id": str(materialization.pod_id) if materialization.pod_id is not None else None,
        }
        return rtnval, 202


@pods_ns.route("/projects/<string:project_id>/runs/<string:run_id>/variables/<string:name>")
@pods_ns.param("project_id", "The project id")
@pods_ns.param("run_id", "The run id")
@pods_ns.param("name", "The variable name")
class PodScopedVariableResource(Resource):
    @pods_ns.expect(scoped_variable_set_model, validate=True)
    def put(self, project_id: str, run_id: str, name: str):
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor = _get_request_actor_user_id()
        pod_id = request.args.get("pod_id", "")
        if len(pod_id.strip()) == 0:
            abort_with_problem(
                status=400,
                detail="Query param 'pod_id' is required",
                instance=request.path,
            )
        try:
            row = set_scoped_variable(
                db_session=db_session, run_id=run_id, pod_id=pod_id,
                name=name, value=payload.get("value", None),
                value_schema=payload.get("value_schema", None),
                locked=bool(payload.get("locked", False)),
                actor_user_id=actor,
            )
        except SemanticError as xcpt:
            abort_with_problem(
                status=400, detail=str(xcpt), instance=request.path,
                extensions={"run_id": run_id, "pod_id": pod_id, "name": name},
            )

        rtnval = {
            "variable_id": str(row.variable_id),
            "run_id": str(row.run_id),
            "pod_id": str(row.pod_id),
            "name": row.name,
            "locked": bool(row.locked),
        }
        return rtnval

    def delete(self, project_id: str, run_id: str, name: str):
        db_session = _get_request_db_session()
        actor = _get_request_actor_user_id()
        pod_id = request.args.get("pod_id", "")
        if len(pod_id.strip()) == 0:
            abort_with_problem(
                status=400,
                detail="Query param 'pod_id' is required",
                instance=request.path,
            )
        delete_scoped_variable(
            db_session=db_session, run_id=run_id, pod_id=pod_id,
            name=name, actor_user_id=actor,
        )
        return "", 204


def publish_namespaces(version_prefix: str):
    """
        Return (namespace, path) tuples for v1 wiring.
    """
    rtnval = [(pods_ns, version_prefix + PODS_NAMESPACE_PATH)]
    return rtnval
