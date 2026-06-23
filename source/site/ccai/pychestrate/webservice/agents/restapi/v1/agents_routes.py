"""
.. module:: agents.restapi.v1.agents_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for Layer-3 agent endpoints.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module provides the
webworks-native ``agents`` controller.

Four routes — note that the agents namespace publishes routes
across two top-level URL prefixes (``/clients`` and
``/agent-rollouts``), reflecting the namespace as a logical
grouping rather than a path prefix:

* ``GET  /api/v1/clients/{client_id}/capabilities``
  — list capabilities advertised by a client.
* ``GET  /api/v1/clients:inventory``
  — paged inventory list (Google AIP-style colon action verb).
* ``POST /api/v1/agent-rollouts``
  — draft a new agent rollout.
* ``POST /api/v1/agent-rollouts/{rollout_id}:start``
  — start a previously-drafted rollout.

Path-syntax note: the AIP-style ``:inventory`` and ``:start``
suffixes are static text, not webworks converters. The router
matches them via regex backtracking on the
``StringConverter`` regex (``[^/]+``) — for ``rollout_id`` values
that themselves contain a ``:``, callers must encode it; UUIDs
do not, so this is a non-issue in practice.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from ccai.errors.exceptions import SemanticError
from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.agents.capability_service import (
    list_capabilities_for_client,
)
from ccai.pychestrate.webservice.agents.exceptions import (
    RolloutNotFoundError,
    RolloutStateTransitionError,
)
from ccai.pychestrate.webservice.agents.inventory_service import (
    read_inventory,
)
from ccai.pychestrate.webservice.agents.upgrade_service import (
    draft_rollout,
    start_rollout,
)
from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)


CLIENTS_BASE_PATH = "/clients"
AGENT_ROLLOUTS_BASE_PATH = "/agent-rollouts"

DEFAULT_INVENTORY_OFFSET = 0
DEFAULT_INVENTORY_LIMIT = 100
DEFAULT_ROLLOUT_TARGET_SIZE = 10


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
        Return the authenticated actor's user id from the request.

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


def _parse_int_or_abort(
        *, request: Request, raw: str, field_name: str
    ) -> int:
    """
        Coerce a query parameter to an integer, aborting with 400
        problem+json on non-integer input.

        :param request: Incoming webworks request.
        :param raw: Raw string value (already known to be non-None).
        :param field_name: Name of the query field for the error
                           detail.

        :returns: Integer value.
        :raises: :class:`_ProblemAbort` (400) on bad input.
    """
    try:
        value = int(raw)
    except (TypeError, ValueError):
        _abort_problem(
            request=request,
            status=400,
            detail="Invalid {!r} argument".format(field_name),
            extensions={field_name: raw},
        )
    rtnval = value
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_list_client_capabilities(request: Request) -> Response:
    """
        ``GET /api/v1/clients/{client_id}/capabilities`` — list
        capabilities advertised by a client. Sensitive values are
        excluded.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of capability
                  dicts, or problem response on failure.
    """
    client_id = request.path_params.get("client_id", "")
    try:
        db_session = _require_session(request=request)
        rows = list_capabilities_for_client(
            db_session=db_session,
            client_id=client_id,
            include_sensitive=False,
        )
        body = []
        for row in rows:
            value: Any = None
            if isinstance(row.value_json, dict):
                value = row.value_json.get("value")
            entry = {
                "kind": row.kind,
                "value": value,
                "revision_token": row.revision_token,
                "updated_at": (
                    row.updated_at.isoformat()
                    if row.updated_at is not None else None
                ),
            }
            body.append(entry)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_list_client_inventory(request: Request) -> Response:
    """
        ``GET /api/v1/clients:inventory`` — paged client inventory.
        Optional query params: ``project_id``, ``liveness``,
        ``offset``, ``limit``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the inventory page, or
                  problem response on failure.
    """
    try:
        db_session = _require_session(request=request)

        project_id = request.query_params.get("project_id", None)
        liveness = request.query_params.get("liveness", None)

        offset_raw = request.query_params.get(
            "offset", str(DEFAULT_INVENTORY_OFFSET)
        )
        offset = _parse_int_or_abort(
            request=request, raw=offset_raw, field_name="offset"
        )

        limit_raw = request.query_params.get(
            "limit", str(DEFAULT_INVENTORY_LIMIT)
        )
        limit = _parse_int_or_abort(
            request=request, raw=limit_raw, field_name="limit"
        )

        page = read_inventory(
            db_session=db_session,
            project_id=project_id,
            liveness_state=liveness,
            offset=offset,
            limit=limit,
        )

        body = {
            "total": int(page.total),
            "offset": int(page.offset),
            "limit": int(page.limit),
            "rows": [
                {
                    "client_id": row.client_id,
                    "project_id": row.project_id,
                    "pod_name": row.pod_name,
                    "liveness_state": row.liveness_state,
                    "agent_version": row.agent_version,
                    "last_seen": row.last_seen,
                    "capability_kinds": list(row.capability_kinds),
                }
                for row in page.rows
            ],
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_draft_agent_rollout(request: Request) -> Response:
    """
        ``POST /api/v1/agent-rollouts`` — draft a new agent rollout.
        Returns 201 with the rollout id, version, and state.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the rollout summary, or
                  problem response on failure.
    """
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        try:
            rollout = draft_rollout(
                db_session=db_session,
                version=payload.get("version", ""),
                artifact_source=payload.get("artifact_source", ""),
                artifact_ref=payload.get("artifact_ref", ""),
                signature=None,
                actor_user_id=actor,
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request, status=400, detail=str(xcpt)
            )

        body = {
            "rollout_id": str(rollout.rollout_id),
            "version": rollout.version,
            "state": rollout.state.value,
        }
        rtnval: Response = JSONResponse(content=body, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_start_agent_rollout(request: Request) -> Response:
    """
        ``POST /api/v1/agent-rollouts/{rollout_id}:start`` — start a
        drafted rollout. Returns 202 with the offer count and the
        list of offers issued.

        :param request: Incoming webworks request.

        :returns: JSON response (202) with the offer manifest, or
                  problem response on failure.
    """
    rollout_id = request.path_params.get("rollout_id", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        candidate_ids_raw = payload.get("candidate_client_ids", None)
        if candidate_ids_raw is None:
            candidate_ids_raw = []
        candidate_ids = list(candidate_ids_raw)

        target_raw = payload.get(
            "target_size", DEFAULT_ROLLOUT_TARGET_SIZE
        )
        try:
            target_size = int(target_raw)
        except (TypeError, ValueError):
            _abort_problem(
                request=request,
                status=400,
                detail="target_size must be an integer",
                extensions={"target_size": str(target_raw)},
            )

        try:
            offers = start_rollout(
                db_session=db_session,
                rollout_id=rollout_id,
                candidate_client_ids=candidate_ids,
                target_size=target_size,
                actor_user_id=actor,
            )
        except RolloutNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"rollout_id": rollout_id},
            )
        except RolloutStateTransitionError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"rollout_id": rollout_id},
            )

        body = {
            "rollout_id": rollout_id,
            "offer_count": len(offers),
            "offers": [
                {
                    "offer_id": str(offer.offer_id),
                    "client_id": str(offer.client_id),
                }
                for offer in offers
            ],
        }
        rtnval: Response = JSONResponse(content=body, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_agents_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the Layer-3 agent routes to a webworks application.

        Note that the agents namespace publishes routes across the
        ``/clients`` and ``/agent-rollouts`` URL prefixes — the
        namespace is a logical grouping, not a path prefix. The
        ``:inventory`` and ``:start`` AIP-style action verbs match
        as static suffixes via regex backtracking.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    clients_base = version_prefix + CLIENTS_BASE_PATH
    rollouts_base = version_prefix + AGENT_ROLLOUTS_BASE_PATH

    app.attach_route(
        clients_base + ":inventory", methods=["GET"]
    )(handle_list_client_inventory)
    app.attach_route(
        clients_base + "/{client_id}/capabilities", methods=["GET"]
    )(handle_list_client_capabilities)

    app.attach_route(
        rollouts_base, methods=["POST"]
    )(handle_draft_agent_rollout)
    app.attach_route(
        rollouts_base + "/{rollout_id}:start", methods=["POST"]
    )(handle_start_agent_rollout)

    return


__all__ = [
    "CLIENTS_BASE_PATH",
    "AGENT_ROLLOUTS_BASE_PATH",
    "DEFAULT_INVENTORY_OFFSET",
    "DEFAULT_INVENTORY_LIMIT",
    "DEFAULT_ROLLOUT_TARGET_SIZE",
    "register_agents_routes",
    "handle_list_client_capabilities",
    "handle_list_client_inventory",
    "handle_draft_agent_rollout",
    "handle_start_agent_rollout",
]
