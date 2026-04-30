"""
.. module:: identity.users.restapi.v1.users_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/identity/users.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks. Pattern follows
the worked example documented in
:mod:`automojo.pychestrate.webservice.security.auth.restapi.v1.auth_controller`.

Endpoints (unchanged URLs):

* ``POST /api/v1/identity/users`` — create user.
* ``GET  /api/v1/identity/users/{user_id}`` — fetch user.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.identity.users.exceptions import (
    UserAlreadyExistsError,
    UserNotFoundError,
)
from automojo.pychestrate.webservice.identity.users import user_service
from automojo.pychestrate.webservice.dbsessionmiddleware import (
    get_request_actor_user_id,
)


IDENTITY_USERS_BASE_PATH = "/api/v1/identity/users"


def _model_to_dict(user) -> Dict[str, Any]:
    """
        Render an :class:`IdentityUser` instance as the REST response
        dict.

        :param user: The persistent model instance.

        :returns: A plain dict suitable for JSON serialization.
    """
    rtnval = {
        "user_id": str(user.user_id),
        "login_name": user.login_name,
        "primary_email": user.primary_email,
        "display_name": user.display_name,
        "status": user.status.value if user.status is not None else None,
        "provisioning_source": user.provisioning_source,
        "external_id": user.external_id,
        "timezone": user.timezone,
        "created_at": (
            user.created_at.isoformat() if user.created_at is not None else None
        ),
        "updated_at": (
            user.updated_at.isoformat() if user.updated_at is not None else None
        ),
    }
    return rtnval


def _require_db_session(*, request: Request) -> Any:
    """
        Pull the request-scoped ``db_session`` set by
        :class:`DbSessionMiddleware`, or 503.

        :param request: The incoming HTTP request.

        :returns: The SQLAlchemy session attached by the middleware.

        :raises HTTPException: 503 when the middleware did not run.
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

        :param request: The incoming HTTP request.

        :returns: The decoded JSON object as a dict.

        :raises HTTPException: 400 when the body is missing or not an
                               object.
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


class IdentityUsersBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/identity/users`` endpoints.
    """

    base_path = IDENTITY_USERS_BASE_PATH
    tags = ["identity", "users", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/identity/users",
        methods=["POST"],
        doc=Doc(
            summary="Create identity user",
            description="Create a new canonical identity user record.",
        ),
    )
    def create_user(request: Request) -> JSONResponse:
        """
            Create a new identity user.

            :param request: The incoming HTTP request.

            :returns: 201 with the new user payload.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)

        try:
            user = user_service.create_user(
                db_session=db_session,
                login_name=payload.get("login_name", ""),
                primary_email=payload.get("primary_email", ""),
                display_name=payload.get("display_name", ""),
                timezone=payload.get("timezone", "UTC"),
                provisioning_source=payload.get(
                    "provisioning_source", "local",
                ),
                external_id=payload.get("external_id", None),
                actor_user_id=actor_user_id,
            )
        except UserAlreadyExistsError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc),
            ) from exc

        body = _model_to_dict(user)
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/identity/users/{user_id}",
        methods=["GET"],
        doc=Doc(
            summary="Read identity user",
            description="Fetch a canonical identity user by id.",
        ),
    )
    def read_user(request: Request) -> JSONResponse:
        """
            Fetch a single identity user.

            :param request: The incoming HTTP request.

            :returns: 200 with the user payload.
        """
        db_session = _require_db_session(request=request)
        user_id = request.path_params.get("user_id", "")

        try:
            user = user_service.read_user(
                db_session=db_session, user_id=user_id,
            )
        except UserNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc

        body = _model_to_dict(user)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
