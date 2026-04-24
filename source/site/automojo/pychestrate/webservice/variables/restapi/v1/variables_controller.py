"""
.. module:: variables.restapi.v1.variables_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/variables.

.. moduleauthor:: Automation Mojo LLC

Implements the 2-global-variables M1 endpoints:

* ``PUT    /api/v1/variables/{scope}/{scope_id}/{name}`` — set.
* ``DELETE /api/v1/variables/{scope}/{scope_id}/{name}`` — unset.
* ``GET    /api/v1/variables/{scope}/{scope_id}/{name}`` — read.
* ``GET    /api/v1/variables/{scope}/{scope_id}`` — list.

Pipeline / job scopes and the effective-resolution endpoint land in M2.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from flask import request
from flask_restx import Namespace, Resource, fields

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.variables import service as variable_service
from automojo.pychestrate.webservice.variables.exceptions import (
    InvalidVariableScopeError,
    InvalidVariableValueError,
    VariableNotFoundError,
)
from automojo.pychestrate.webservice.variables.models import (
    VariableScope,
    VariableValueType,
)


VARIABLES_NAMESPACE_PATH = "/variables"


variables_ns = Namespace(
    "Variables v1",
    description="Typed variable bindings (2-global-variables).",
)


variable_set_model = variables_ns.model(
    "VariableSet",
    {
        "value": fields.Raw(required=True, description="Value payload"),
        "value_type": fields.String(
            required=True,
            description="STRING | INTEGER | FLOAT | BOOLEAN | JSON | SECRET_REF",
        ),
    },
)


variable_response_model = variables_ns.model(
    "VariableResponse",
    {
        "binding_id": fields.String(description="Server-generated UUID"),
        "scope": fields.String(description="SYSTEM | PROJECT"),
        "scope_id": fields.String(description="Scope-local identifier"),
        "name": fields.String(description="Variable name"),
        "value_type": fields.String(description="Declared type"),
        "value": fields.Raw(description="Decoded value"),
        "set_at": fields.String(description="ISO-8601 timestamp"),
    },
)


def _binding_to_dict(binding) -> dict:
    """
        Render a :class:`VariableBinding` as the REST response dict.
    """
    rtnval = {
        "binding_id": str(binding.binding_id),
        "scope": binding.scope.value,
        "scope_id": binding.scope_id,
        "name": binding.name,
        "value_type": binding.value_type.value,
        "value": variable_service.decode_binding_value(binding=binding),
        "set_at": binding.set_at.isoformat() if binding.set_at is not None else None,
    }
    return rtnval


def _parse_scope(*, raw_scope: str) -> VariableScope:
    """
        Parse a URL scope segment into :class:`VariableScope`.

        :param raw_scope: Raw segment.

        :returns: The matching enum value.
        :raises: Flask abort(400) on unknown.
    """
    normalized = raw_scope.strip().upper()
    try:
        rtnval = VariableScope[normalized]
    except KeyError:
        variables_ns.abort(400, "Unknown scope: {}".format(raw_scope))
    return rtnval


def _parse_value_type(*, raw: str) -> VariableValueType:
    """
        Parse a value_type string.

        :param raw: Raw value.

        :returns: The matching enum value.
    """
    normalized = raw.strip().upper()
    try:
        rtnval = VariableValueType[normalized]
    except KeyError:
        variables_ns.abort(400, "Unknown value_type: {}".format(raw))
    return rtnval


@variables_ns.route("/<string:scope>/<string:scope_id>/<string:name>")
@variables_ns.param("scope", "Scope (``system`` | ``project``)")
@variables_ns.param("scope_id", "Scope-local identifier")
@variables_ns.param("name", "Variable name")
class VariableDetail(Resource):
    """
        Resource for set/unset/read on a single variable triple.
    """

    @variables_ns.expect(variable_set_model, validate=True)
    @variables_ns.marshal_with(variable_response_model)
    def put(self, scope: str, scope_id: str, name: str):
        """
            Set or replace a variable binding.
        """
        payload = request.get_json(force=True, silent=False)
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()

        scope_enum = _parse_scope(raw_scope=scope)
        value_type = _parse_value_type(raw=payload.get("value_type", ""))

        try:
            binding = variable_service.set_variable(
                db_session=db_session,
                scope=scope_enum,
                scope_id=scope_id,
                name=name,
                value=payload.get("value", None),
                value_type=value_type,
                actor_user_id=actor_user_id,
            )
        except InvalidVariableScopeError as xcpt:
            variables_ns.abort(400, str(xcpt))
        except InvalidVariableValueError as xcpt:
            variables_ns.abort(400, str(xcpt))
        except SemanticError as xcpt:
            variables_ns.abort(400, str(xcpt))

        rtnval = _binding_to_dict(binding)
        return rtnval

    @variables_ns.marshal_with(variable_response_model)
    def get(self, scope: str, scope_id: str, name: str):
        """
            Return a single binding.
        """
        db_session = _get_request_db_session()
        scope_enum = _parse_scope(raw_scope=scope)

        try:
            binding = variable_service.get_variable(
                db_session=db_session,
                scope=scope_enum,
                scope_id=scope_id,
                name=name,
            )
        except InvalidVariableScopeError as xcpt:
            variables_ns.abort(400, str(xcpt))
        except VariableNotFoundError as xcpt:
            variables_ns.abort(404, str(xcpt))

        rtnval = _binding_to_dict(binding)
        return rtnval

    def delete(self, scope: str, scope_id: str, name: str):
        """
            Remove a binding.
        """
        db_session = _get_request_db_session()
        actor_user_id = _get_request_actor_user_id()
        scope_enum = _parse_scope(raw_scope=scope)

        try:
            variable_service.unset_variable(
                db_session=db_session,
                scope=scope_enum,
                scope_id=scope_id,
                name=name,
                actor_user_id=actor_user_id,
            )
        except InvalidVariableScopeError as xcpt:
            variables_ns.abort(400, str(xcpt))
        except VariableNotFoundError as xcpt:
            variables_ns.abort(404, str(xcpt))

        return "", 204


@variables_ns.route("/<string:scope>/<string:scope_id>")
@variables_ns.param("scope", "Scope (``system`` | ``project``)")
@variables_ns.param("scope_id", "Scope-local identifier")
class VariableScopeList(Resource):
    """
        Resource that exposes listing bindings at a given scope.
    """

    @variables_ns.marshal_list_with(variable_response_model)
    def get(self, scope: str, scope_id: str):
        """
            List all bindings at the given scope.
        """
        db_session = _get_request_db_session()
        scope_enum = _parse_scope(raw_scope=scope)

        try:
            rows = variable_service.list_for_scope(
                db_session=db_session,
                scope=scope_enum,
                scope_id=scope_id,
            )
        except InvalidVariableScopeError as xcpt:
            variables_ns.abort(400, str(xcpt))

        rtnval = [_binding_to_dict(row) for row in rows]
        return rtnval


@variables_ns.route("/effective")
class VariableEffective(Resource):
    """
        GET ``/api/v1/variables/effective`` — resolve a variable through
        the scope chain.
    """

    def get(self):
        """
            Return the effective value (and optional trace).
        """
        db_session = _get_request_db_session()
        name = request.args.get("name", "")
        project_id = request.args.get("project", None)
        pipeline_id = request.args.get("pipeline", None)
        job_id = request.args.get("job", None)
        include_trace = str(request.args.get("include_trace", "")).lower() in ("1", "true", "yes")
        dereference = str(request.args.get("dereference_secrets", "")).lower() in ("1", "true", "yes")

        if name is None or len(name.strip()) == 0:
            variables_ns.abort(400, "Query parameter 'name' is required")

        value = variable_service.resolve_effective(
            db_session=db_session,
            name=name,
            project_id=project_id,
            pipeline_id=pipeline_id,
            job_id=job_id,
            dereference_secrets=dereference,
        )

        rtnval = {"name": name, "value": value}
        if include_trace is True:
            entries = variable_service.build_trace(
                db_session=db_session,
                name=name,
                project_id=project_id,
                pipeline_id=pipeline_id,
                job_id=job_id,
            )
            trace = []
            for entry in entries:
                binding = entry["binding"]
                trace_row = {
                    "scope": entry["scope"],
                    "scope_id": entry["scope_id"],
                    "present": binding is not None,
                    "value_type": binding.value_type.value if binding is not None else None,
                    "set_by_user_id": str(binding.set_by_user_id) if binding is not None and binding.set_by_user_id is not None else None,
                    "set_at": binding.set_at.isoformat() if binding is not None and binding.set_at is not None else None,
                }
                trace.append(trace_row)
            rtnval["trace"] = trace

        return rtnval


def _get_request_db_session():
    """
        Resolve the request-scoped SQLAlchemy session.
    """
    from flask import g
    db_session = getattr(g, "db_session", None)
    if db_session is None:
        variables_ns.abort(503, "Request-scoped db_session not configured")
    return db_session


def _get_request_actor_user_id():
    """
        Resolve the acting principal's user id.
    """
    from flask import g
    actor = getattr(g, "actor_user_id", None)
    return actor


def publish_namespaces(version_prefix: str):
    """
        Return namespace registrations for v1 wiring.

        :param version_prefix: Version prefix (``/1``).

        :returns: List of (namespace, path) tuples.
    """
    rtnval = [(variables_ns, version_prefix + VARIABLES_NAMESPACE_PATH)]
    return rtnval
