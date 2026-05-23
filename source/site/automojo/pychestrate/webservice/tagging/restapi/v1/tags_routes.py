"""
.. module:: tagging.restapi.v1.tags_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/tags.

.. moduleauthor:: Automation Mojo LLC

The production webservice runs on ``automojo.webworks`` (see
:mod:`app_pychestrate_main`). This module provides the
webworks-native ``tags`` controller.

Five routes:

* ``POST   /api/v1/tags/{entity_kind}/{entity_id}``
  — assign a tag to an entity.
* ``GET    /api/v1/tags/{entity_kind}/{entity_id}``
  — list tags on an entity.
* ``DELETE /api/v1/tags/{entity_kind}/{entity_id}/{tag:path}``
  — remove a tag from an entity. The ``:path`` converter lets
  multi-segment ``taxonomy:value`` tags match.
* ``GET    /api/v1/tags/search?kind=...&expr=...``
  — boolean tag-expression search.
* ``GET    /api/v1/tags/taxonomies``
  — list registered taxonomies.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from automojo.errors.exceptions import SemanticError
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.tagging import service as tag_service
from automojo.pychestrate.webservice.tagging.exceptions import (
    TagAssignmentNotFoundError,
    TagValueValidationError,
    TaxonomyNotFoundError,
)


TAGS_PATH = "/tags"


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition once
        and the handler can convert it to a return at the boundary.
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
        extensions: Optional[dict] = None
    ) -> None:
    """
        Build a problem response from the request context and raise
        :class:`_ProblemAbort` so the handler returns the response.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional extension members.

        :returns: Never returns; raises :class:`_ProblemAbort`.
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
        Return the request-scoped db session attached by
        :class:`PychestrateSessionMiddleware`.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    """
        Return the authenticated actor's user id.

        :param request: Incoming webworks request.

        :returns: User id string or None.
    """
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort with a 503
        problem document.

        :param request: Incoming webworks request.

        :returns: Session.
        :raises: :class:`_ProblemAbort` (503).
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


def _decode_json_or_abort(*, request: Request) -> dict:
    """
        Decode the request body as JSON, aborting with a 400 when
        the body is missing or non-dict.

        :param request: Incoming webworks request.

        :returns: Decoded JSON object.
        :raises: :class:`_ProblemAbort` (400).
    """
    try:
        payload = request.json()
    except Exception:
        payload = None

    if payload is None:
        _abort_problem(
            request=request, status=400, detail="Request body must be JSON"
        )
    if not isinstance(payload, dict):
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be a JSON object",
        )

    rtnval = payload
    return rtnval


def _entity_extensions(
        *, entity_kind: str, entity_id: str
    ) -> dict:
    """
        Build the standard ``{entity_kind, entity_id}`` extension
        dict attached to entity-scoped problem documents. Pulled out
        so every error site uses the same shape.

        :param entity_kind: Entity kind (``project``, ...).
        :param entity_id: Entity id.

        :returns: Extension-member dict.
    """
    rtnval = {"entity_kind": entity_kind, "entity_id": entity_id}
    return rtnval


def _assignment_to_dict(assignment: Any) -> dict:
    """
        Render a :class:`TagAssignment` ORM row as the REST response
        dict.

        :param assignment: ORM row.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "assignment_id": str(assignment.assignment_id),
        "entity_kind": assignment.entity_kind,
        "entity_id": str(assignment.entity_id),
        "taxonomy_name": assignment.taxonomy_name,
        "canonical_value": assignment.canonical_value,
        "assigned_at": (
            assignment.assigned_at.isoformat()
            if assignment.assigned_at is not None else None
        ),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_assign_tag(request: Request) -> Response:
    """
        ``POST /api/v1/tags/{entity_kind}/{entity_id}`` — assign a
        tag to an entity. Tag is supplied in the body as
        ``{"tag": "taxonomy:value"}``.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the assignment dict, or
                  problem response on failure.
    """
    entity_kind = request.path_params.get("entity_kind", "")
    entity_id = request.path_params.get("entity_id", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor_user_id = _resolve_actor_user_id(request=request)

        raw_tag = payload.get("tag", "")
        try:
            assignment = tag_service.assign_tag(
                db_session=db_session,
                entity_kind=entity_kind,
                entity_id=entity_id,
                raw_tag=raw_tag,
                actor_user_id=actor_user_id,
            )
        except SemanticError as xcpt:
            extensions = _entity_extensions(
                entity_kind=entity_kind, entity_id=entity_id
            )
            extensions["raw_tag"] = raw_tag
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=extensions,
            )
        except TaxonomyNotFoundError as xcpt:
            extensions = _entity_extensions(
                entity_kind=entity_kind, entity_id=entity_id
            )
            extensions["raw_tag"] = raw_tag
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions=extensions,
            )
        except TagValueValidationError as xcpt:
            extensions = _entity_extensions(
                entity_kind=entity_kind, entity_id=entity_id
            )
            extensions["raw_tag"] = raw_tag
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=extensions,
            )

        body = _assignment_to_dict(assignment)
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_tags(request: Request) -> Response:
    """
        ``GET /api/v1/tags/{entity_kind}/{entity_id}`` — list tags
        currently assigned to an entity.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a list of assignment
                  dicts, or problem response on failure.
    """
    entity_kind = request.path_params.get("entity_kind", "")
    entity_id = request.path_params.get("entity_id", "")
    try:
        db_session = _require_session(request=request)
        try:
            rows = tag_service.list_tags(
                db_session=db_session,
                entity_kind=entity_kind,
                entity_id=entity_id,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=_entity_extensions(
                    entity_kind=entity_kind, entity_id=entity_id
                ),
            )

        body = [_assignment_to_dict(row) for row in rows]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_remove_tag(request: Request) -> Response:
    """
        ``DELETE /api/v1/tags/{entity_kind}/{entity_id}/{tag:path}``
        — remove a tag assignment from an entity.

        :param request: Incoming webworks request.

        :returns: 204 (empty body) on success, problem response on
                  failure.
    """
    entity_kind = request.path_params.get("entity_kind", "")
    entity_id = request.path_params.get("entity_id", "")
    raw_tag = request.path_params.get("tag", "")
    try:
        db_session = _require_session(request=request)

        try:
            tag_service.remove_tag(
                db_session=db_session,
                entity_kind=entity_kind,
                entity_id=entity_id,
                raw_tag=raw_tag,
            )
        except SemanticError as xcpt:
            extensions = _entity_extensions(
                entity_kind=entity_kind, entity_id=entity_id
            )
            extensions["raw_tag"] = raw_tag
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=extensions,
            )
        except TaxonomyNotFoundError as xcpt:
            extensions = _entity_extensions(
                entity_kind=entity_kind, entity_id=entity_id
            )
            extensions["raw_tag"] = raw_tag
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions=extensions,
            )
        except TagValueValidationError as xcpt:
            extensions = _entity_extensions(
                entity_kind=entity_kind, entity_id=entity_id
            )
            extensions["raw_tag"] = raw_tag
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions=extensions,
            )
        except TagAssignmentNotFoundError as xcpt:
            extensions = _entity_extensions(
                entity_kind=entity_kind, entity_id=entity_id
            )
            extensions["raw_tag"] = raw_tag
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions=extensions,
            )

        rtnval: Response = Response(status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_search_tags(request: Request) -> Response:
    """
        ``GET /api/v1/tags/search?kind=...&expr=...`` — search
        entities by boolean tag expression.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with
                  ``{entity_kind, entity_ids}``, or problem response
                  on failure.
    """
    try:
        db_session = _require_session(request=request)

        kind = request.query_params.get("kind", "")
        expr = request.query_params.get("expr", "")

        try:
            entity_ids = tag_service.search_entities(
                db_session=db_session,
                entity_kind=kind,
                expression=expr,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"entity_kind": kind, "expression": expr},
            )
        except TagValueValidationError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"entity_kind": kind, "expression": expr},
            )

        body = {"entity_kind": kind, "entity_ids": entity_ids}
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_taxonomies(request: Request) -> Response:
    """
        ``GET /api/v1/tags/taxonomies`` — list registered
        taxonomies sorted by name.

        :param request: Incoming webworks request (unused).

        :returns: JSON response (200) with a list of taxonomy
                  descriptor dicts.
    """
    from automojo.pychestrate.webservice.tagging.registry import (
        load_registered_taxonomies,
    )
    registry = load_registered_taxonomies()

    body = []
    for name, pack in sorted(registry.items()):
        allowed = getattr(pack, "allowed_values", None)
        body.append({
            "taxonomy_name": name,
            "case_sensitive_value": bool(
                getattr(pack, "case_sensitive_value", False)
            ),
            "allowed_values": (
                sorted(list(allowed)) if allowed is not None else None
            ),
            "color_hex": getattr(pack, "color_hex", "#888888"),
            "description": getattr(pack, "description", ""),
        })
    rtnval = JSONResponse(content=body, status_code=200)
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_tags_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the tag-assignment routes to a webworks application.

        Note that the fixed sub-paths (``/search``, ``/taxonomies``)
        register BEFORE the parameterized
        ``/{entity_kind}/{entity_id}`` route. Although the fixed
        paths only have one segment after ``/tags`` and the
        parameterized has two, declaring the fixed routes first
        keeps the registration order self-documenting and matches
        the pattern from the prior ports.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + TAGS_PATH

    app.attach_route(base + "/search", methods=["GET"])(handle_search_tags)
    app.attach_route(
        base + "/taxonomies", methods=["GET"]
    )(handle_list_taxonomies)

    app.attach_route(
        base + "/{entity_kind}/{entity_id}", methods=["POST"]
    )(handle_assign_tag)
    app.attach_route(
        base + "/{entity_kind}/{entity_id}", methods=["GET"]
    )(handle_list_tags)
    app.attach_route(
        base + "/{entity_kind}/{entity_id}/{tag:path}", methods=["DELETE"]
    )(handle_remove_tag)

    return


__all__ = [
    "TAGS_PATH",
    "register_tags_routes",
    "handle_assign_tag",
    "handle_list_tags",
    "handle_remove_tag",
    "handle_search_tags",
    "handle_list_taxonomies",
]
