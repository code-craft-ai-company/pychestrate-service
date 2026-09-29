"""
.. module:: resources.restapi.v1.resources_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the per-resource surface.

.. moduleauthor:: Code Craft AI LLC

Exposes the per-resource read operations from the resources domain
(:mod:`webservice.resources.inventory`,
:mod:`...resources.health`, :mod:`...resources.usage_history`).

Routes attached by :func:`register_resources_routes`:

* ``POST /api/v1/resources`` -- register a resource (RES-04: nothing
  could, so no pool could have a member)
* ``GET /api/v1/resources?project_id=`` -- list a project's resources
* ``GET /api/v1/resources/{resource_id}`` -- read one resource
* ``POST /api/v1/resources/{resource_id}/state`` -- transition the
  resource lifecycle state (quarantine / maintenance / available /
  retire)
* ``GET /api/v1/resources/{resource_id}/health`` -- current health
  record
* ``GET /api/v1/resources/{resource_id}/usage-history`` -- the
  resource usage timeline (newest first)

The health record is seeded on ``entity.resource.registered`` by the
M2 bus subscriber -- a resource that has never been probed answers
``404`` from the health endpoint.

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import uuid

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai.errors.exceptions import SemanticError
from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.core.defaults import ensure_utc
from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.resources.health import (
    service as health_service,
)
from ccai.pychestrate.webservice.resources.health.errors import (
    HealthRecordNotFoundError,
)
from ccai.pychestrate.webservice.resources.inventory import (
    service as inventory_service,
)
from ccai.pychestrate.webservice.resources.inventory.errors import (
    ResourceIdentityConflictError,
    ResourceKindUnknownError,
    ResourceNotFoundError,
    ResourceStateTransitionError,
)
from ccai.pychestrate.webservice.resources.inventory.models import (
    ResourceState,
)
from ccai.pychestrate.webservice.resources.usage_history import (
    service as usage_history_service,
)
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


RESOURCES_PATH = "/resources"

RESOURCES_READ_PERMISSION_KEY = "system:resources.read"
RESOURCES_WRITE_PERMISSION_KEY = "system:resources.write"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

DEFAULT_TIMELINE_LIMIT = 200
MIN_TIMELINE_LIMIT = 1
MAX_TIMELINE_LIMIT = 1000

_LOGGER = logging.getLogger("pychestrate.resources.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition
        once and the top-level handler can convert it to a return
        value at the boundary.
    """

    def __init__(self, response: Response) -> None:
        super().__init__("problem abort")
        self.response: Response = response
        return


def _abort_problem(
        *,
        request: Request,
        status: int,
        detail: str,
        extensions: Optional[Dict[str, Any]] = None
    ) -> None:
    """
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional namespaced extension members.

        :returns: Never returns.
    """
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _resolve_db_session(request: Request) -> Optional[Any]:
    """
        Return the request-scoped db session or ``None``.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
    """
    db_session = _resolve_db_session(request=request)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _resolve_auth_principal(request: Request) -> Optional[Any]:
    """
        Return the ``AuthPrincipal`` attached by the session
        middleware, or ``None`` when the request is anonymous.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _require_permission(
        *,
        request: Request,
        db_session: Any,
        permission_key: str
    ) -> Any:
    """
        Require the calling principal to hold ``permission_key``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param permission_key: Required ``system:*`` permission key.

        :returns: The :class:`AuthPrincipal`.
    """
    principal = _resolve_auth_principal(request=request)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )

    now = datetime.now(timezone.utc)
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=permission_key,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(permission_key),
            extensions={"required_permission": permission_key},
        )
    rtnval = principal
    return rtnval


def _decode_json_object_or_abort(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, aborting with
        422 on missing / malformed / non-dict bodies.

        :param request: Incoming webworks request.

        :returns: Decoded dict.
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request,
            status=422,
            detail="Request body must be JSON.",
        )
    if isinstance(payload, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Request body must be a JSON object.",
        )

    rtnval = payload
    return rtnval


def _require_string_field(
        *,
        request: Request,
        body: Dict[str, Any],
        field_name: str
    ) -> str:
    """
        Pull a required non-empty string field from a JSON body.

        :param request: Incoming webworks request.
        :param body: Decoded JSON object body.
        :param field_name: Required field name.

        :returns: The field value.
    """
    value = body.get(field_name, None)
    if not isinstance(value, str) or len(value) == 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Field '{}' is required.".format(field_name),
            extensions={"missing_fields": [field_name]},
        )
    rtnval = value
    return rtnval


def _parse_positive_int(
        *,
        request: Request,
        name: str,
        raw: Optional[str],
        default: int,
        minimum: int,
        maximum: Optional[int] = None
    ) -> int:
    """
        Coerce a positive-integer query param with bounds checking.

        :param request: Incoming webworks request.
        :param name: Query-param name (for error context).
        :param raw: Raw query value or None.
        :param default: Fallback when the param is absent.
        :param minimum: Lower bound (inclusive).
        :param maximum: Optional upper bound (inclusive).

        :returns: Coerced integer.
    """
    if raw is None or len(raw) == 0:
        rtnval = default
        return rtnval

    try:
        candidate = int(raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be an integer.".format(name),
            extensions={"query_param": name, "raw_value": raw},
        )
        candidate = default  # unreachable

    if candidate < minimum:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be >= {}.".format(name, minimum),
            extensions={"query_param": name, "raw_value": raw},
        )
    if maximum is not None and candidate > maximum:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param '{}' must be <= {}.".format(name, maximum),
            extensions={"query_param": name, "raw_value": raw},
        )

    rtnval = candidate
    return rtnval


def _require_resource_id(*, request: Request) -> str:
    """
        Read the ``resource_id`` path parameter. Resource ids are
        UUIDs; a value that is not one cannot name a resource, so it
        is answered ``404`` like any unknown id (the database layer
        used to raise on it and the request failed with a ``500``).

        :param request: Incoming webworks request.

        :returns: The canonical UUID text.
    """
    raw = request.path_params.get("resource_id", "")
    try:
        rtnval = str(uuid.UUID(str(raw)))
    except (TypeError, ValueError, AttributeError):
        _abort_problem(
            request=request,
            status=404,
            detail="Resource not found: '{}' is not a resource id.".format(raw),
            extensions={"resource_id": raw},
        )
        rtnval = ""  # unreachable
    return rtnval


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _iso_or_none(value: Any) -> Optional[str]:
    """
        Serialize a datetime as RFC 3339 with an explicit UTC offset
        (``2026-09-22T23:34:26+00:00``), or return ``None``. The
        database stores UTC; a naive value (SQLite hands those back)
        is UTC, and sending it without an offset made browsers read it
        as local time, shifting every time by the viewer's UTC offset
        (audit finding RES-20).

        :param value: Datetime or None.

        :returns: RFC 3339 string or None.
    """
    if value is None:
        rtnval = None
        return rtnval
    if isinstance(value, datetime):
        rtnval = ensure_utc(value).isoformat()
        return rtnval
    rtnval = str(value)
    return rtnval


def _enum_value_or_str(value: Any) -> Optional[str]:
    """
        Return the ``.value`` of a string-enum or its ``str``.

        :param value: Enum instance or scalar.

        :returns: String value or None.
    """
    if value is None:
        rtnval = None
        return rtnval
    extracted = getattr(value, "value", None)
    if extracted is not None:
        rtnval = str(extracted)
        return rtnval
    rtnval = str(value)
    return rtnval


def _resource_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`ResourceView` to the OpenAPI ``Resource``
        schema.

        :param view: Resource read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "resource_id": str(view.resource_id),
        "project_id": str(view.project_id),
        "kind": view.kind,
        "display_name": view.display_name,
        "description": view.description,
        "identity_hash": view.identity_hash,
        "state": _enum_value_or_str(view.state),
        "tags": list(view.tags or ()),
        "attributes": dict(view.attributes or {}),
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


def _health_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`HealthView` to the OpenAPI
        ``ResourceHealth`` schema.

        :param view: Health read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "health_id": str(view.health_id),
        "resource_id": str(view.resource_id),
        "project_id": str(view.project_id),
        "probe_name": view.probe_name,
        "probe_period_seconds": int(view.probe_period_seconds),
        "last_outcome": _enum_value_or_str(view.last_outcome),
        "last_probe_at": _iso_or_none(view.last_probe_at),
        "last_pass_at": _iso_or_none(view.last_pass_at),
        "last_fail_at": _iso_or_none(view.last_fail_at),
        "next_probe_at": _iso_or_none(view.next_probe_at),
        "pass_count": int(view.pass_count),
        "fail_count": int(view.fail_count),
        "consecutive_failures": int(view.consecutive_failures),
        "last_error": view.last_error,
        "last_payload": dict(view.last_payload or {}),
    }
    return rtnval


def _usage_record_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`TimelineEventView` to the OpenAPI
        ``UsageRecord`` schema.

        :param view: Timeline-event read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "event_id": str(view.event_id),
        "source_event_id": str(view.source_event_id),
        "resource_id": str(view.resource_id),
        "project_id": str(view.project_id),
        "event_type": _enum_value_or_str(view.event_type),
        "actor_id": view.actor_id,
        "pod_event_group_id": view.pod_event_group_id,
        "at_ts": _iso_or_none(view.at_ts),
        "payload": dict(view.payload or {}),
        "annotations": dict(view.annotations or {}),
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/resources and POST /api/v1/resources
# ---------------------------------------------------------------------------


def _require_project_id_query(*, request: Request) -> str:
    """
        Resolve the required ``project_id`` query param (a UUID) or abort 400.

        :param request: Incoming webworks request.

        :returns: The canonical UUID text.
    """
    raw = request.query_params.get("project_id", None)
    if raw is None or len(raw) == 0:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param 'project_id' is required.",
            extensions={"query_param": "project_id"},
        )
    try:
        rtnval = str(uuid.UUID(str(raw)))
    except (TypeError, ValueError, AttributeError):
        _abort_problem(
            request=request,
            status=400,
            detail="Query param 'project_id' must be a UUID.",
            extensions={"query_param": "project_id", "raw_value": raw},
        )
        rtnval = ""  # unreachable
    return rtnval


def handle_list_resources(request: Request) -> Response:
    """
        ``GET /api/v1/resources`` -- list a project's resources.

        Query: ``project_id`` (required), ``kind``, ``state`` and ``tag``
        (each optional), ``include_retired`` (``true`` to list retired
        resources too), ``page`` and ``per_page``. Returns a paginated
        ``Page<Resource>`` (``{items, meta}``), oldest registration first.

        :param request: Incoming webworks request.

        :returns: JSON response (200) or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request, db_session=db_session,
            permission_key=RESOURCES_READ_PERMISSION_KEY,
        )
        project_id = _require_project_id_query(request=request)
        kind = request.query_params.get("kind", None) or None
        state_filter = request.query_params.get("state", None) or None
        tag_filter = request.query_params.get("tag", None) or None
        include_retired = str(request.query_params.get("include_retired", "")).lower() in ("1", "true", "yes")
        if state_filter is not None:
            valid_states = [member.value for member in ResourceState]
            if state_filter not in valid_states:
                _abort_problem(
                    request=request, status=400,
                    detail="Query param 'state' must be one of: {}.".format(", ".join(valid_states)),
                    extensions={"query_param": "state", "raw_value": state_filter},
                )
            if state_filter == ResourceState.RETIRED.value:
                include_retired = True
        page = _parse_positive_int(
            request=request, name="page", raw=request.query_params.get("page", None),
            default=1, minimum=1,
        )
        per_page = _parse_positive_int(
            request=request, name="per_page", raw=request.query_params.get("per_page", None),
            default=DEFAULT_PAGE_SIZE, minimum=MIN_PAGE_SIZE, maximum=MAX_PAGE_SIZE,
        )

        views = inventory_service.list_resources(
            db_session=db_session, project_id=project_id, kind=kind, include_retired=include_retired,
        )
        if state_filter is not None:
            views = [view for view in views if _enum_value_or_str(view.state) == state_filter]
        if tag_filter is not None:
            views = [view for view in views if tag_filter in (view.tags or ())]
        total = len(views)
        offset = (page - 1) * per_page
        body = {
            "items": [_resource_view_to_dict(view=view) for view in views[offset:offset + per_page]],
            "meta": {"page": page, "per_page": per_page, "total": int(total), "next_cursor": None},
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_register_resource(request: Request) -> Response:
    """
        ``POST /api/v1/resources`` -- register a resource.

        Body: ``project_id`` (a UUID), ``kind`` and ``display_name``
        (required), ``attributes`` (an object the kind validates),
        ``description`` and ``tags`` (optional). ``201`` with the
        ``Resource``; ``400`` for a kind that is not loaded (the detail names
        it and lists the loaded kinds); ``409`` when the same identity is
        already registered; ``422`` when the kind refuses the attributes.

        :param request: Incoming webworks request.

        :returns: JSON response (201) or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request, db_session=db_session,
            permission_key=RESOURCES_WRITE_PERMISSION_KEY,
        )
        body = _decode_json_object_or_abort(request=request)
        raw_project_id = _require_string_field(request=request, body=body, field_name="project_id")
        try:
            project_id = str(uuid.UUID(raw_project_id))
        except (TypeError, ValueError, AttributeError):
            _abort_problem(
                request=request, status=422, detail="Field 'project_id' must be a UUID.",
                extensions={"invalid_fields": ["project_id"], "raw_value": raw_project_id},
            )
            project_id = ""  # unreachable
        kind = _require_string_field(request=request, body=body, field_name="kind")
        display_name = _require_string_field(request=request, body=body, field_name="display_name").strip()
        if len(display_name) == 0:
            _abort_problem(
                request=request, status=422, detail="Field 'display_name' is required.",
                extensions={"missing_fields": ["display_name"]},
            )
        description = body.get("description", "")
        if isinstance(description, str) is False:
            _abort_problem(request=request, status=422, detail="Field 'description' must be a string.")
        attributes = body.get("attributes", {})
        if isinstance(attributes, dict) is False:
            _abort_problem(request=request, status=422, detail="Field 'attributes' must be an object.")
        tags_raw = body.get("tags", [])
        if isinstance(tags_raw, list) is False or all(isinstance(tag, str) for tag in tags_raw) is False:
            _abort_problem(request=request, status=422, detail="Field 'tags' must be an array of strings.")
        tags = tuple(dict.fromkeys(tag.strip() for tag in tags_raw if len(tag.strip()) > 0))

        try:
            view = inventory_service.register_resource(
                db_session=db_session, project_id=project_id, kind=kind,
                display_name=display_name, attributes=attributes,
                description=description, tags=tags,
            )
        except ResourceKindUnknownError as xcpt:
            _abort_problem(
                request=request, status=400,
                detail="Resource kind '{}' is not loaded. Loaded kinds: {}.".format(
                    kind, ", ".join(inventory_service.list_kind_names()) or "none"),
                extensions={"kind": kind, "loaded_kinds": inventory_service.list_kind_names(), "reason": str(xcpt).splitlines()[0]},
            )
            view = None  # unreachable
        except ResourceIdentityConflictError as xcpt:
            _abort_problem(
                request=request, status=409,
                detail="A {} with this identity is already registered.".format(kind),
                extensions={"kind": kind, "reason": str(xcpt).splitlines()[0]},
            )
            view = None  # unreachable
        except SemanticError as xcpt:
            # ccai errors derive from BaseException, so ``except Exception`` would miss this.
            _abort_problem(
                request=request, status=422,
                detail=str(xcpt).splitlines()[0] if len(str(xcpt)) > 0 else "The attributes are not valid for this kind.",
                extensions={"kind": kind, "reason": str(xcpt)},
            )
            view = None  # unreachable

        rtnval = JSONResponse(content=_resource_view_to_dict(view=view), status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/resources/{resource_id}
# ---------------------------------------------------------------------------


def handle_read_resource(request: Request) -> Response:
    """
        ``GET /api/v1/resources/{resource_id}`` -- read one resource.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the ``Resource`` dict, or
                  a problem response.
    """
    resource_id = request.path_params.get("resource_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCES_READ_PERMISSION_KEY,
        )
        resource_id = _require_resource_id(request=request)

        try:
            view = inventory_service.get_resource(
                db_session=db_session, resource_id=resource_id,
            )
        except ResourceNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"resource_id": resource_id},
            )
            view = None  # unreachable

        body_dict = _resource_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/resources/{resource_id}/state
# ---------------------------------------------------------------------------


def handle_transition_resource_state(request: Request) -> Response:
    """
        ``POST /api/v1/resources/{resource_id}/state`` -- apply a
        lifecycle state transition to a resource.

        Body: ``state`` (required -- one of ``available``,
        ``leased``, ``quarantined``, ``maintenance``, ``retired``),
        ``reason`` (optional free-text, recorded on the
        state-changed event).

        Legal transitions are validated by the inventory service --
        an impermissible move (e.g. un-retiring) returns ``409``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the updated ``Resource``
                  dict, or a problem response.
    """
    resource_id = request.path_params.get("resource_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCES_WRITE_PERMISSION_KEY,
        )
        resource_id = _require_resource_id(request=request)

        body = _decode_json_object_or_abort(request=request)
        state_raw = _require_string_field(
            request=request, body=body, field_name="state",
        )
        try:
            new_state = ResourceState(state_raw.strip().lower())
        except ValueError:
            valid_states = [member.value for member in ResourceState]
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'state' must be one of: {}.".format(
                    ", ".join(valid_states)
                ),
                extensions={"raw_value": state_raw},
            )
            new_state = ResourceState.AVAILABLE  # unreachable

        reason = body.get("reason", "")
        if isinstance(reason, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'reason' must be a string.",
            )

        actor = "user:{}".format(principal.user_id)
        try:
            view = inventory_service.transition_state(
                db_session=db_session,
                resource_id=resource_id,
                new_state=new_state,
                actor=actor,
                reason=reason,
            )
        except ResourceNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"resource_id": resource_id},
            )
            view = None  # unreachable
        except ResourceStateTransitionError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={
                    "resource_id": resource_id,
                    "requested_state": new_state.value,
                    "reason": "transition_not_permitted",
                },
            )
            view = None  # unreachable

        body_dict = _resource_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/resources/{resource_id}/health
# ---------------------------------------------------------------------------


def handle_read_resource_health(request: Request) -> Response:
    """
        ``GET /api/v1/resources/{resource_id}/health`` -- read the
        current health record for a resource.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the ``ResourceHealth``
                  dict, or a problem response.
    """
    resource_id = request.path_params.get("resource_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCES_READ_PERMISSION_KEY,
        )
        resource_id = _require_resource_id(request=request)

        try:
            view = health_service.get_health_record(
                db_session=db_session, resource_id=resource_id,
            )
        except HealthRecordNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"resource_id": resource_id},
            )
            view = None  # unreachable

        body_dict = _health_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/resources/{resource_id}/usage-history
# ---------------------------------------------------------------------------


def handle_list_resource_usage_history(request: Request) -> Response:
    """
        ``GET /api/v1/resources/{resource_id}/usage-history`` -- list
        the usage timeline for a resource (newest first).

        Query param: ``limit`` (1..1000, default 200).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``{items, meta}`` page,
                  or a problem response.
    """
    resource_id = request.path_params.get("resource_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCES_READ_PERMISSION_KEY,
        )
        resource_id = _require_resource_id(request=request)

        limit = _parse_positive_int(
            request=request,
            name="limit",
            raw=request.query_params.get("limit", None),
            default=DEFAULT_TIMELINE_LIMIT,
            minimum=MIN_TIMELINE_LIMIT,
            maximum=MAX_TIMELINE_LIMIT,
        )

        views = usage_history_service.list_timeline(
            db_session=db_session,
            resource_id=resource_id,
            limit=limit,
        )
        items: List[Dict[str, Any]] = []
        for view in views:
            items.append(_usage_record_view_to_dict(view=view))

        body = {
            "items": items,
            "meta": {
                "page": 1,
                "per_page": len(items),
                "total": len(items),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_resources_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the per-resource REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + RESOURCES_PATH

    app.attach_route(base, methods=["GET"])(handle_list_resources)
    app.attach_route(base, methods=["POST"])(handle_register_resource)
    app.attach_route(
        base + "/{resource_id}", methods=["GET"],
    )(handle_read_resource)
    app.attach_route(
        base + "/{resource_id}/state", methods=["POST"],
    )(handle_transition_resource_state)
    app.attach_route(
        base + "/{resource_id}/health", methods=["GET"],
    )(handle_read_resource_health)
    app.attach_route(
        base + "/{resource_id}/usage-history", methods=["GET"],
    )(handle_list_resource_usage_history)

    _LOGGER.info(
        "pychestrate.resources.routes registered: 6 routes under %s",
        base,
    )
    return


__all__ = [
    "RESOURCES_PATH",
    "RESOURCES_READ_PERMISSION_KEY",
    "RESOURCES_WRITE_PERMISSION_KEY",
    "DEFAULT_TIMELINE_LIMIT",
    "MAX_TIMELINE_LIMIT",
    "register_resources_routes",
    "handle_list_resources",
    "handle_register_resource",
    "handle_read_resource",
    "handle_transition_resource_state",
    "handle_read_resource_health",
    "handle_list_resource_usage_history",
]
