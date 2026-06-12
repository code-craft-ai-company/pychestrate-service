"""
.. module:: clients.restapi.v1.clients_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/clients.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module provides the
webworks-native ``clients`` controller.

Four routes:

* ``GET  /api/v1/clients``
  — list with optional ``project_id`` / ``status`` /
  ``liveness_state`` filters.
* ``GET  /api/v1/clients/{client_id}``
  — single client view.
* ``POST /api/v1/clients/{client_id}/revoke``
  — admin revoke (with documented reason + optional note).
* ``PUT  /api/v1/clients/{client_id}/attributes``
  — admin attribute batch upsert with optimistic concurrency
  via ``expected_revision_token``.

The agents port (#125) registers ``/api/v1/clients:inventory``
and ``/api/v1/clients/{client_id}/capabilities``; those do not
overlap with this module's routes — the colon-action
``clients:inventory`` segment is a different literal from
``clients``, and ``capabilities`` is a different fixed last
segment than ``revoke`` / ``attributes``.

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Optional

from ccai.errors.exceptions import SemanticError
from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.clients.enrollment.service import (
    revoke_client,
)
from ccai.pychestrate.webservice.clients.enums import (
    ClientStatus,
    LivenessState,
    RevocationReason,
)
from ccai.pychestrate.webservice.clients.exceptions import (
    ClientNotFoundError,
    InvalidAttributeValueError,
    UnknownAttributeKindError,
)
from ccai.pychestrate.webservice.clients.registry.service import (
    AttributeUpdate,
    ClientView,
    get_client,
    list_clients,
    update_attributes,
)


CLIENTS_PATH = "/clients"


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
        Build a problem response and raise :class:`_ProblemAbort`.

        :param request: Incoming webworks request.
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param extensions: Optional extension members.

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
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _resolve_actor_user_id(request: Request) -> Optional[str]:
    rtnval = getattr(request, "actor_user_id", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.
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
        Decode the request body as JSON, aborting 400 on missing /
        non-dict.
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


def _parse_client_status_or_abort(
        *, request: Request, raw: Optional[str]
    ) -> Optional[ClientStatus]:
    """
        Coerce a ``status`` query string to a :class:`ClientStatus`.
        Empty / None returns None (no filter). Unknown raises
        400 problem+json with the raw value carried as the
        ``requested_status`` extension key.

        :param request: Incoming webworks request.
        :param raw: Raw query value or None.

        :returns: :class:`ClientStatus` or None.
    """
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = ClientStatus(raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=400,
            detail="Unknown status: {}".format(raw),
            extensions={"requested_status": raw},
        )
    return rtnval


def _parse_liveness_state_or_abort(
        *, request: Request, raw: Optional[str]
    ) -> Optional[LivenessState]:
    """
        Coerce a ``liveness_state`` query string. Same shape as
        :func:`_parse_client_status_or_abort`.

        :param request: Incoming webworks request.
        :param raw: Raw query value or None.

        :returns: :class:`LivenessState` or None.
    """
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = LivenessState(raw)
    except ValueError:
        _abort_problem(
            request=request,
            status=400,
            detail="Unknown liveness_state: {}".format(raw),
            extensions={"requested_liveness_state": raw},
        )
    return rtnval


def _parse_revocation_reason(*, raw: str) -> RevocationReason:
    """
        Coerce a ``reason`` body string to
        :class:`RevocationReason`. Raises :class:`SemanticError`
        rather than aborting so the caller chooses how to map it.

        :param raw: Raw value.

        :returns: :class:`RevocationReason`.
        :raises: SemanticError on unknown values.
    """
    try:
        rtnval = RevocationReason(raw)
    except ValueError:
        raise SemanticError("Unknown revocation reason: {}".format(raw))
    return rtnval


def _view_to_dict(view: ClientView) -> dict:
    """
        Render a :class:`ClientView` as the REST response dict.

        :param view: View object from the registry service.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "client_id": view.client_id,
        "project_id": view.project_id,
        "pod_name": view.pod_name,
        "status": view.status.value,
        "liveness_state": view.liveness_state.value,
        "enrolled_at": view.enrolled_at_iso,
        "last_seen": view.last_seen_iso,
        "last_agent_version": view.last_agent_version,
        "transport_name": view.transport_name,
        "degraded_at": view.degraded_at_iso,
        "revision_token": view.revision_token,
        "attributes": dict(view.attributes),
    }
    return rtnval


def _build_attribute_updates_or_abort(
        *,
        request: Request,
        client_id: str,
        raw_updates: Any
    ) -> List[AttributeUpdate]:
    """
        Validate the ``updates`` array and build a list of
        :class:`AttributeUpdate`. Aborts 400 with the client_id as
        an extension member on any shape error.

        :param request: Incoming webworks request.
        :param client_id: The client id (for error context).
        :param raw_updates: The ``updates`` field from the body.

        :returns: List of :class:`AttributeUpdate`.
        :raises: :class:`_ProblemAbort` on shape errors.
    """
    if isinstance(raw_updates, list) is False:
        _abort_problem(
            request=request,
            status=400,
            detail="'updates' must be a list of {kind, value} objects",
            extensions={"client_id": client_id},
        )

    rtnval: List[AttributeUpdate] = []
    for item in raw_updates:
        if isinstance(item, dict) is False:
            _abort_problem(
                request=request,
                status=400,
                detail="Each update must be an object",
                extensions={"client_id": client_id},
            )
        kind = item.get("kind", "")
        if isinstance(kind, str) is False or len(kind) == 0:
            _abort_problem(
                request=request,
                status=400,
                detail="Each update must include a non-empty 'kind'",
                extensions={"client_id": client_id},
            )
        rtnval.append(
            AttributeUpdate(kind=kind, value=item.get("value", None))
        )

    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_list_clients(request: Request) -> Response:
    """
        ``GET /api/v1/clients`` — list clients with optional
        ``project_id`` / ``status`` / ``liveness_state`` filters.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of view
                  dicts, or problem response on failure.
    """
    try:
        db_session = _require_session(request=request)
        project_id = request.query_params.get("project_id", None)
        status = _parse_client_status_or_abort(
            request=request,
            raw=request.query_params.get("status", ""),
        )
        liveness_state = _parse_liveness_state_or_abort(
            request=request,
            raw=request.query_params.get("liveness_state", ""),
        )

        views = list_clients(
            db_session=db_session,
            project_id=project_id,
            status=status,
            liveness_state=liveness_state,
        )
        body = [_view_to_dict(view) for view in views]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_client(request: Request) -> Response:
    """
        ``GET /api/v1/clients/{client_id}`` — single client view.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the view dict, or
                  problem response on failure.
    """
    client_id = request.path_params.get("client_id", "")
    try:
        db_session = _require_session(request=request)

        try:
            view = get_client(db_session=db_session, client_id=client_id)
        except ClientNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"client_id": client_id},
            )

        body = _view_to_dict(view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_revoke_client(request: Request) -> Response:
    """
        ``POST /api/v1/clients/{client_id}/revoke`` — admin
        revoke. Returns ``{client_id, status: "revoked"}``.

        :param request: Incoming webworks request.

        :returns: JSON response (200), or problem response.
    """
    client_id = request.path_params.get("client_id", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)
        actor = _resolve_actor_user_id(request=request)

        try:
            reason = _parse_revocation_reason(
                raw=payload.get("reason", "")
            )
        except SemanticError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"client_id": client_id},
            )

        try:
            revoke_client(
                db_session=db_session,
                client_id=client_id,
                reason=reason,
                revoked_by=actor,
                note=payload.get("note", ""),
            )
        except ClientNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"client_id": client_id},
            )

        body = {"client_id": client_id, "status": "revoked"}
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_update_client_attributes(request: Request) -> Response:
    """
        ``PUT /api/v1/clients/{client_id}/attributes`` — admin
        attribute batch upsert with optional optimistic concurrency.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with
                  ``{client_id, kinds_written}``, or problem
                  response on failure.
    """
    client_id = request.path_params.get("client_id", "")
    try:
        payload = _decode_json_or_abort(request=request)
        db_session = _require_session(request=request)

        updates = _build_attribute_updates_or_abort(
            request=request,
            client_id=client_id,
            raw_updates=payload.get("updates", []),
        )
        expected_token = payload.get("expected_revision_token", None)

        try:
            written = update_attributes(
                db_session=db_session,
                client_id=client_id,
                updates=updates,
                expected_revision_token=expected_token,
            )
        except ClientNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"client_id": client_id},
            )
        except UnknownAttributeKindError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"client_id": client_id},
            )
        except InvalidAttributeValueError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"client_id": client_id},
            )

        body = {"client_id": client_id, "kinds_written": list(written)}
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_clients_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the clients-admin routes to a webworks application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix.

        :returns: None.
    """
    base = version_prefix + CLIENTS_PATH

    app.attach_route(base, methods=["GET"])(handle_list_clients)
    app.attach_route(
        base + "/{client_id}", methods=["GET"]
    )(handle_read_client)
    app.attach_route(
        base + "/{client_id}/revoke", methods=["POST"]
    )(handle_revoke_client)
    app.attach_route(
        base + "/{client_id}/attributes", methods=["PUT"]
    )(handle_update_client_attributes)

    return


__all__ = [
    "CLIENTS_PATH",
    "register_clients_routes",
    "handle_list_clients",
    "handle_read_client",
    "handle_revoke_client",
    "handle_update_client_attributes",
]
