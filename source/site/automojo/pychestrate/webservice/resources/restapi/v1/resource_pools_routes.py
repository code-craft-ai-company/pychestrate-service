"""
.. module:: resources.restapi.v1.resource_pools_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the resource-pools surface.

.. moduleauthor:: Automation Mojo LLC

Exposes the resource-pool, pool-membership, and reservation
operations from the resources domain
(:mod:`webservice.resources.pools`, :mod:`...resources.inventory`,
:mod:`...resources.checkout`).

Routes attached by :func:`register_resource_pools_routes`:

* ``GET    /api/v1/resource-pools`` -- paginated ``Page<ResourcePool>``
* ``POST   /api/v1/resource-pools`` -- create a pool
* ``GET    /api/v1/resource-pools/{pool_id}`` -- read one pool
* ``DELETE /api/v1/resource-pools/{pool_id}`` -- delete a pool
* ``GET    /api/v1/resource-pools/{pool_id}/resources`` -- list members
* ``POST   /api/v1/resource-pools/{pool_id}/resources`` -- add a member
* ``DELETE /api/v1/resource-pools/{pool_id}/resources/{resource_id}``
  -- remove a member
* ``GET    /api/v1/resource-pools/{pool_id}/reservations`` -- list
  reservations across the pool's member resources
* ``POST   /api/v1/resource-pools/{pool_id}/reservations`` -- reserve
  (checkout) an eligible pool member
* ``DELETE /api/v1/resource-pools/{pool_id}/reservations/{reservation_id}``
  -- release a reservation

The resources domain models **reservations** (the checkout facade),
not free-form "allocations" -- this module uses the domain's
vocabulary. A pool reservation runs the FIFO ``pick_candidate``
allocation strategy, then opens an EXCLUSIVE / SHARED reservation
against the chosen member through the conflict evaluator.

The pool-listing and member-listing services are project-scoped, so
``GET /resource-pools`` requires a ``project_id`` query parameter.

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.resources.checkout import (
    service as checkout_service,
)
from automojo.pychestrate.webservice.resources.checkout.errors import (
    ReservationConflictError,
    ReservationNotFoundError,
)
from automojo.pychestrate.webservice.resources.checkout.models import (
    ReservationMode,
)
from automojo.pychestrate.webservice.resources.pools import (
    service as pools_service,
)
from automojo.pychestrate.webservice.resources.pools import (
    repository as pools_repository,
)
from automojo.pychestrate.webservice.resources.pools.errors import (
    PoolEmptyError,
    PoolMemberConflictError,
    PoolNotFoundError,
)
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


RESOURCE_POOLS_PATH = "/resource-pools"

RESOURCE_POOLS_READ_PERMISSION_KEY = "system:resource_pools.read"
RESOURCE_POOLS_WRITE_PERMISSION_KEY = "system:resource_pools.write"
RESOURCES_READ_PERMISSION_KEY = "system:resources.read"
RESOURCES_WRITE_PERMISSION_KEY = "system:resources.write"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.resources.pools.routes")


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


def _require_project_id_query(*, request: Request) -> str:
    """
        Resolve the required ``project_id`` query param or abort 400.

        :param request: Incoming webworks request.

        :returns: Project UUID string.
    """
    raw = request.query_params.get("project_id", None)
    if raw is None or len(raw) == 0:
        _abort_problem(
            request=request,
            status=400,
            detail="Query param 'project_id' is required.",
            extensions={"query_param": "project_id"},
        )
    rtnval = raw
    return rtnval


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------


def _iso_or_none(value: Any) -> Optional[str]:
    """
        ISO-8601 serialize a datetime or return ``None``.

        :param value: Datetime or None.

        :returns: ISO-formatted string or None.
    """
    if value is None:
        rtnval = None
        return rtnval
    if isinstance(value, datetime):
        rtnval = value.isoformat()
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


def _pool_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`PoolView` to the OpenAPI ``ResourcePool``
        schema.

        :param view: Pool read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "pool_id": str(view.pool_id),
        "project_id": str(view.project_id),
        "name": view.name,
        "description": view.description,
        "capability_tags": list(view.capability_tags or ()),
        "member_count": int(view.member_count),
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


def _member_row_to_dict(row: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`ResourcePoolMember` ORM row.

        :param row: Pool-membership ORM row.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "membership_id": str(row.membership_id),
        "pool_id": str(row.pool_id),
        "resource_id": str(row.resource_id),
        "added_at": _iso_or_none(row.added_at),
    }
    return rtnval


def _reservation_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`ReservationView` to the OpenAPI
        ``Reservation`` schema.

        :param view: Reservation read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "reservation_id": str(view.reservation_id),
        "project_id": str(view.project_id),
        "resource_id": str(view.resource_id),
        "requested_by": view.requested_by,
        "mode": _enum_value_or_str(view.mode),
        "state": _enum_value_or_str(view.state),
        "note": view.note,
        "requested_at": _iso_or_none(view.requested_at),
        "granted_at": _iso_or_none(view.granted_at),
        "released_at": _iso_or_none(view.released_at),
        "rejection_reason": view.rejection_reason,
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/resource-pools
# ---------------------------------------------------------------------------


def handle_list_resource_pools(request: Request) -> Response:
    """
        ``GET /api/v1/resource-pools`` -- list pools for a project.

        The pool-listing service is project-scoped, so a
        ``project_id`` query parameter is required. Returns a
        paginated ``Page<ResourcePool>`` (``{items, meta}``).

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``{items, meta}`` page,
                  or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_READ_PERMISSION_KEY,
        )
        project_id = _require_project_id_query(request=request)

        page = _parse_positive_int(
            request=request,
            name="page",
            raw=request.query_params.get("page", None),
            default=1,
            minimum=1,
        )
        per_page = _parse_positive_int(
            request=request,
            name="per_page",
            raw=request.query_params.get("per_page", None),
            default=DEFAULT_PAGE_SIZE,
            minimum=MIN_PAGE_SIZE,
            maximum=MAX_PAGE_SIZE,
        )

        all_views = pools_service.list_pools(
            db_session=db_session,
            project_id=project_id,
        )
        total = len(all_views)
        offset = (page - 1) * per_page
        window = all_views[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for view in window:
            items.append(_pool_view_to_dict(view=view))

        body = {
            "items": items,
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": int(total),
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_create_resource_pool(request: Request) -> Response:
    """
        ``POST /api/v1/resource-pools`` -- create a resource pool.

        Body: ``project_id`` (required), ``name`` (required),
        ``description`` (optional), ``capability_tags`` (optional
        array of strings).

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the ``ResourcePool`` dict,
                  or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_WRITE_PERMISSION_KEY,
        )
        body = _decode_json_object_or_abort(request=request)

        project_id = _require_string_field(
            request=request, body=body, field_name="project_id",
        )
        name = _require_string_field(
            request=request, body=body, field_name="name",
        )
        description = body.get("description", "")
        if isinstance(description, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'description' must be a string.",
            )
        capability_tags_raw = body.get("capability_tags", [])
        if isinstance(capability_tags_raw, list) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'capability_tags' must be an array.",
            )
        capability_tags = tuple(str(tag) for tag in capability_tags_raw)

        try:
            view = pools_service.create_pool(
                db_session=db_session,
                project_id=project_id,
                name=name,
                description=description,
                capability_tags=capability_tags,
            )
        except PoolMemberConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"project_id": project_id, "name": name},
            )
            view = None  # unreachable

        body_dict = _pool_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_read_resource_pool(request: Request) -> Response:
    """
        ``GET /api/v1/resource-pools/{pool_id}`` -- read one pool.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the ``ResourcePool`` dict,
                  or a problem response.
    """
    pool_id = request.path_params.get("pool_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_READ_PERMISSION_KEY,
        )

        try:
            view = pools_service.get_pool(
                db_session=db_session, pool_id=pool_id,
            )
        except PoolNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"pool_id": pool_id},
            )
            view = None  # unreachable

        body_dict = _pool_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_delete_resource_pool(request: Request) -> Response:
    """
        ``DELETE /api/v1/resource-pools/{pool_id}`` -- delete a pool.

        Membership rows cascade through the
        ``resources_resource_pool_member`` foreign key.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    pool_id = request.path_params.get("pool_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_WRITE_PERMISSION_KEY,
        )

        row = pools_repository.find_pool_by_id(
            db_session=db_session, pool_id=pool_id,
        )
        if row is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Pool not found.",
                extensions={"pool_id": pool_id},
            )

        pools_repository.delete_pool(db_session=db_session, row=row)
        db_session.commit()

        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# /api/v1/resource-pools/{pool_id}/resources
# ---------------------------------------------------------------------------


def handle_list_pool_resources(request: Request) -> Response:
    """
        ``GET /api/v1/resource-pools/{pool_id}/resources`` -- list the
        resource members of a pool.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``{items, meta}`` page,
                  or a problem response.
    """
    pool_id = request.path_params.get("pool_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_READ_PERMISSION_KEY,
        )

        try:
            pools_service.get_pool(db_session=db_session, pool_id=pool_id)
        except PoolNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"pool_id": pool_id},
            )

        member_rows = pools_repository.list_members(
            db_session=db_session, pool_id=pool_id,
        )
        items: List[Dict[str, Any]] = []
        for row in member_rows:
            items.append(_member_row_to_dict(row=row))

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


def handle_add_pool_resource(request: Request) -> Response:
    """
        ``POST /api/v1/resource-pools/{pool_id}/resources`` -- add a
        resource to a pool. Idempotent on an already-attached
        resource.

        Body: ``resource_id`` (required).

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the membership dict, or a
                  problem response.
    """
    pool_id = request.path_params.get("pool_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_WRITE_PERMISSION_KEY,
        )
        body = _decode_json_object_or_abort(request=request)
        resource_id = _require_string_field(
            request=request, body=body, field_name="resource_id",
        )

        try:
            row = pools_service.add_member(
                db_session=db_session,
                pool_id=pool_id,
                resource_id=resource_id,
            )
        except PoolNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"pool_id": pool_id},
            )
            row = None  # unreachable

        body_dict = _member_row_to_dict(row=row)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_remove_pool_resource(request: Request) -> Response:
    """
        ``DELETE /api/v1/resource-pools/{pool_id}/resources/{resource_id}``
        -- remove a resource from a pool. Idempotent on a missing
        membership.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    pool_id = request.path_params.get("pool_id", "")
    resource_id = request.path_params.get("resource_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_WRITE_PERMISSION_KEY,
        )

        pools_service.remove_member(
            db_session=db_session,
            pool_id=pool_id,
            resource_id=resource_id,
        )

        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# /api/v1/resource-pools/{pool_id}/reservations
# ---------------------------------------------------------------------------


def handle_list_pool_reservations(request: Request) -> Response:
    """
        ``GET /api/v1/resource-pools/{pool_id}/reservations`` -- list
        every reservation against the pool's member resources.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``{items, meta}`` page,
                  or a problem response.
    """
    pool_id = request.path_params.get("pool_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_READ_PERMISSION_KEY,
        )

        try:
            pools_service.get_pool(db_session=db_session, pool_id=pool_id)
        except PoolNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"pool_id": pool_id},
            )

        member_rows = pools_repository.list_members(
            db_session=db_session, pool_id=pool_id,
        )

        items: List[Dict[str, Any]] = []
        for member in member_rows:
            resource_id = str(member.resource_id)
            reservation_views = checkout_service.list_reservations_for_resource(
                db_session=db_session, resource_id=resource_id,
            )
            for reservation_view in reservation_views:
                items.append(_reservation_view_to_dict(view=reservation_view))

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


def handle_create_pool_reservation(request: Request) -> Response:
    """
        ``POST /api/v1/resource-pools/{pool_id}/reservations`` -- open
        a reservation (checkout) against an eligible pool member.

        The FIFO ``pick_candidate`` allocation strategy chooses the
        member unless the body supplies ``resource_id`` (a direct
        target) or ``preferred_member`` (a hint honored when
        eligible). The chosen resource is then reserved through the
        conflict evaluator.

        Body: ``project_id`` (required), ``mode``
        (``exclusive`` / ``shared``, default ``exclusive``),
        ``requested_by`` (optional), ``note`` (optional),
        ``resource_id`` (optional direct target),
        ``preferred_member`` (optional pick hint).

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the ``Reservation`` dict,
                  or a problem response.
    """
    pool_id = request.path_params.get("pool_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_WRITE_PERMISSION_KEY,
        )
        body = _decode_json_object_or_abort(request=request)
        project_id = _require_string_field(
            request=request, body=body, field_name="project_id",
        )

        mode_raw = body.get("mode", "exclusive")
        try:
            mode = ReservationMode(str(mode_raw).strip().lower())
        except ValueError:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'mode' must be 'exclusive' or 'shared'.",
                extensions={"raw_value": mode_raw},
            )
            mode = ReservationMode.EXCLUSIVE  # unreachable

        requested_by = body.get("requested_by", None)
        note = body.get("note", "")
        if isinstance(note, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'note' must be a string.",
            )

        resource_id = body.get("resource_id", None)
        if resource_id is None:
            preferred_member = body.get("preferred_member", None)
            aspects = pools_service.AllocationAspects(
                preferred_member=preferred_member,
            )
            try:
                candidate = pools_service.pick_candidate(
                    db_session=db_session,
                    pool_id=pool_id,
                    aspects=aspects,
                )
            except PoolNotFoundError as xcpt:
                _abort_problem(
                    request=request,
                    status=404,
                    detail=str(xcpt),
                    extensions={"pool_id": pool_id},
                )
                candidate = None  # unreachable
            except PoolEmptyError as xcpt:
                _abort_problem(
                    request=request,
                    status=409,
                    detail=str(xcpt),
                    extensions={"pool_id": pool_id, "reason": "pool_empty"},
                )
                candidate = None  # unreachable
            resource_id = candidate.resource_id
        else:
            if isinstance(resource_id, str) is False or len(resource_id) == 0:
                _abort_problem(
                    request=request,
                    status=422,
                    detail="Field 'resource_id' must be a non-empty string.",
                )

        try:
            view = checkout_service.reserve(
                db_session=db_session,
                project_id=project_id,
                resource_id=resource_id,
                requested_by=requested_by,
                mode=mode,
                aspects=checkout_service.ReservationAspects(note=note),
            )
        except ReservationConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={
                    "pool_id": pool_id,
                    "resource_id": resource_id,
                    "reason": "conflict_rejected",
                },
            )
            view = None  # unreachable

        body_dict = _reservation_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_release_pool_reservation(request: Request) -> Response:
    """
        ``DELETE /api/v1/resource-pools/{pool_id}/reservations/{reservation_id}``
        -- release a reservation. Idempotent on already-released
        rows.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    reservation_id = request.path_params.get("reservation_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=RESOURCE_POOLS_WRITE_PERMISSION_KEY,
        )

        try:
            checkout_service.release(
                db_session=db_session,
                reservation_id=reservation_id,
            )
        except ReservationNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"reservation_id": reservation_id},
            )

        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_resource_pools_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the resource-pools REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + RESOURCE_POOLS_PATH

    app.attach_route(base, methods=["GET"])(handle_list_resource_pools)
    app.attach_route(base, methods=["POST"])(handle_create_resource_pool)

    app.attach_route(
        base + "/{pool_id}", methods=["GET"],
    )(handle_read_resource_pool)
    app.attach_route(
        base + "/{pool_id}", methods=["DELETE"],
    )(handle_delete_resource_pool)

    app.attach_route(
        base + "/{pool_id}/resources", methods=["GET"],
    )(handle_list_pool_resources)
    app.attach_route(
        base + "/{pool_id}/resources", methods=["POST"],
    )(handle_add_pool_resource)
    app.attach_route(
        base + "/{pool_id}/resources/{resource_id}", methods=["DELETE"],
    )(handle_remove_pool_resource)

    app.attach_route(
        base + "/{pool_id}/reservations", methods=["GET"],
    )(handle_list_pool_reservations)
    app.attach_route(
        base + "/{pool_id}/reservations", methods=["POST"],
    )(handle_create_pool_reservation)
    app.attach_route(
        base + "/{pool_id}/reservations/{reservation_id}", methods=["DELETE"],
    )(handle_release_pool_reservation)

    _LOGGER.info(
        "pychestrate.resources.pools.routes registered: 10 routes under %s",
        base,
    )
    return


__all__ = [
    "RESOURCE_POOLS_PATH",
    "RESOURCE_POOLS_READ_PERMISSION_KEY",
    "RESOURCE_POOLS_WRITE_PERMISSION_KEY",
    "RESOURCES_READ_PERMISSION_KEY",
    "RESOURCES_WRITE_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_resource_pools_routes",
    "handle_list_resource_pools",
    "handle_create_resource_pool",
    "handle_read_resource_pool",
    "handle_delete_resource_pool",
    "handle_list_pool_resources",
    "handle_add_pool_resource",
    "handle_remove_pool_resource",
    "handle_list_pool_reservations",
    "handle_create_pool_reservation",
    "handle_release_pool_reservation",
]
