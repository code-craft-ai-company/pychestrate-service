"""
.. module:: clients.restapi.v1.clients_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/clients.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks. Pattern follows
the worked example documented in
:mod:`automojo.pychestrate.webservice.security.auth.restapi.v1.auth_controller`.

Endpoints (unchanged URLs):

* ``GET    /api/v1/clients`` — list with optional filters.
* ``GET    /api/v1/clients/{client_id}`` — single client view.
* ``POST   /api/v1/clients/{client_id}/revoke`` — admin revoke.
* ``PUT    /api/v1/clients/{client_id}/attributes`` — admin attribute upsert.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, Optional

from automojo.errors.exceptions import SemanticError

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.clients.enrollment.service import (
    revoke_client,
)
from automojo.pychestrate.webservice.clients.enums import (
    ClientStatus,
    LivenessState,
    RevocationReason,
)
from automojo.pychestrate.webservice.clients.exceptions import (
    ClientNotFoundError,
    InvalidAttributeValueError,
    UnknownAttributeKindError,
)
from automojo.pychestrate.webservice.clients.registry.service import (
    AttributeUpdate,
    ClientView,
    get_client,
    list_clients,
    update_attributes,
)
from automojo.pychestrate.webservice.dbsessionmiddleware import (
    get_request_actor_user_id,
)


CLIENTS_BASE_PATH = "/api/v1/clients"


def _view_to_dict(view: ClientView) -> Dict[str, Any]:
    """
        Render a :class:`ClientView` as the REST response dict.

        :param view: The view object.

        :returns: A plain dict suitable for JSON serialization.
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


def _parse_client_status(*, raw: Optional[str]) -> Optional[ClientStatus]:
    """
        Coerce a query-param string to a :class:`ClientStatus`.

        :param raw: Raw query-string value, possibly None.

        :returns: The matching enum, or None when ``raw`` is empty.

        :raises HTTPException: 400 when ``raw`` is non-empty and unknown.
    """
    if raw is None:
        return None
    if len(raw) == 0:
        return None
    try:
        rtnval = ClientStatus(raw)
    except ValueError as exc:
        err_msg = "Unknown status: {}".format(raw)
        raise HTTPException(status_code=400, detail=err_msg) from exc
    return rtnval


def _parse_liveness_state(*, raw: Optional[str]) -> Optional[LivenessState]:
    """
        Coerce a query-param string to a :class:`LivenessState`.

        :param raw: Raw query-string value, possibly None.

        :returns: The matching enum, or None when ``raw`` is empty.

        :raises HTTPException: 400 when ``raw`` is non-empty and unknown.
    """
    if raw is None:
        return None
    if len(raw) == 0:
        return None
    try:
        rtnval = LivenessState(raw)
    except ValueError as exc:
        err_msg = "Unknown liveness_state: {}".format(raw)
        raise HTTPException(status_code=400, detail=err_msg) from exc
    return rtnval


def _parse_revocation_reason(*, raw: str) -> RevocationReason:
    """
        Coerce a string to a :class:`RevocationReason`.

        :param raw: Raw string value.

        :returns: The matching enum.

        :raises SemanticError: When ``raw`` is unknown.
    """
    try:
        rtnval = RevocationReason(raw)
    except ValueError as exc:
        err_msg = "Unknown revocation reason: {}".format(raw)
        raise SemanticError(err_msg) from exc
    return rtnval


def _require_db_session(*, request: Request) -> Any:
    """
        Pull the request-scoped ``db_session`` set by
        :class:`DbSessionMiddleware`, or 503.
    """
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
    """
        Parse the request body as a JSON object.
    """
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


class ClientsBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/clients`` admin endpoints.
    """

    base_path = CLIENTS_BASE_PATH
    tags = ["clients", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/clients",
        methods=["GET"],
        doc=Doc(
            summary="List clients",
            description=(
                "List registered clients. Supports project_id, status, "
                "and liveness_state query-string filters."
            ),
        ),
    )
    def list_clients_endpoint(request: Request) -> JSONResponse:
        """
            List clients with optional filters.

            :param request: The incoming HTTP request.

            :returns: 200 with a JSON list of client views.
        """
        db_session = _require_db_session(request=request)
        project_id = request.query_params.get("project_id", None)
        status_raw = request.query_params.get("status", "")
        liveness_raw = request.query_params.get("liveness_state", "")
        status = _parse_client_status(raw=status_raw)
        liveness_state = _parse_liveness_state(raw=liveness_raw)

        views = list_clients(
            db_session=db_session,
            project_id=project_id,
            status=status,
            liveness_state=liveness_state,
        )
        body = [_view_to_dict(view=v) for v in views]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/clients/{client_id}",
        methods=["GET"],
        doc=Doc(
            summary="Read client",
            description="Return a single client view.",
        ),
    )
    def get_client_endpoint(request: Request) -> JSONResponse:
        """
            Read a single client view.

            :param request: The incoming HTTP request.

            :returns: 200 with the client view.
        """
        db_session = _require_db_session(request=request)
        client_id = request.path_params.get("client_id", "")

        try:
            view = get_client(db_session=db_session, client_id=client_id)
        except ClientNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = _view_to_dict(view=view)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/clients/{client_id}/revoke",
        methods=["POST"],
        doc=Doc(
            summary="Revoke a client",
            description="Admin revoke of a client identity.",
        ),
    )
    def revoke_client_endpoint(request: Request) -> JSONResponse:
        """
            Revoke a client identity.

            :param request: The incoming HTTP request.

            :returns: 200 with ``{"client_id": ..., "status":
                      "revoked"}``.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        client_id = request.path_params.get("client_id", "")
        actor_user_id = get_request_actor_user_id(request=request)

        try:
            reason = _parse_revocation_reason(
                raw=payload.get("reason", ""),
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        try:
            revoke_client(
                db_session=db_session,
                client_id=client_id,
                reason=reason,
                revoked_by=actor_user_id,
                note=payload.get("note", ""),
            )
        except ClientNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = {"client_id": client_id, "status": "revoked"}
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/clients/{client_id}/attributes",
        methods=["PUT"],
        doc=Doc(
            summary="Upsert client attributes",
            description=(
                "Apply a batch of attribute kind/value updates to a "
                "client. Supports optimistic concurrency via "
                "expected_revision_token."
            ),
        ),
    )
    def update_attributes_endpoint(request: Request) -> JSONResponse:
        """
            Apply a batch of attribute updates.

            :param request: The incoming HTTP request.

            :returns: 200 with ``{"client_id": ..., "kinds_written":
                      [...]}``.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        client_id = request.path_params.get("client_id", "")

        raw_updates = payload.get("updates", [])
        if not isinstance(raw_updates, list):
            err_msg = "'updates' must be a list of {kind, value} objects"
            raise HTTPException(status_code=400, detail=err_msg)

        updates = []
        for item in raw_updates:
            if not isinstance(item, dict):
                raise HTTPException(
                    status_code=400, detail="Each update must be an object",
                )
            kind = item.get("kind", "")
            if not isinstance(kind, str):
                raise HTTPException(
                    status_code=400,
                    detail="Each update must include a non-empty 'kind'",
                )
            if len(kind) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="Each update must include a non-empty 'kind'",
                )
            update = AttributeUpdate(
                kind=kind, value=item.get("value", None),
            )
            updates.append(update)

        expected_token = payload.get("expected_revision_token", None)

        try:
            written = update_attributes(
                db_session=db_session,
                client_id=client_id,
                updates=updates,
                expected_revision_token=expected_token,
            )
        except ClientNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        except UnknownAttributeKindError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc
        except InvalidAttributeValueError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        body = {"client_id": client_id, "kinds_written": list(written)}
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
