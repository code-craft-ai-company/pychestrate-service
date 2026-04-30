"""
.. module:: identity.flags.restapi.v1.flags_controller
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/flags.

.. moduleauthor:: Automation Mojo LLC

Migrated from Flask + flask-restx to automojo-webworks. Pattern follows
the worked example documented in
:mod:`automojo.pychestrate.webservice.security.auth.restapi.v1.auth_controller`.

Endpoints (unchanged URLs):

* ``POST /api/v1/flags`` — create a flag.
* ``GET  /api/v1/flags/{flag_key}`` — read current view of a flag.
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
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.identity.flags import flag_service
from automojo.pychestrate.webservice.identity.flags.exceptions import (
    FlagAlreadyExistsError,
)
from automojo.pychestrate.webservice.identity.flags.models import (
    FeatureFlag,
    FlagKind,
)
from automojo.pychestrate.webservice.middleware_webworks import (
    get_request_actor_user_id,
)


FLAGS_BASE_PATH = "/api/v1/flags"


def _flag_to_dict(flag: FeatureFlag) -> Dict[str, Any]:
    """
        Render a :class:`FeatureFlag` as the REST response dict.

        :param flag: The persistent model instance.

        :returns: A plain dict suitable for JSON serialization.
    """
    rtnval = {
        "flag_key": flag.flag_key,
        "flag_kind": (
            flag.flag_kind.value if flag.flag_kind is not None else None
        ),
        "current_version": int(flag.current_version),
        "state": flag.state.value if flag.state is not None else None,
        "created_at": (
            flag.created_at.isoformat() if flag.created_at is not None else None
        ),
        "updated_at": (
            flag.updated_at.isoformat() if flag.updated_at is not None else None
        ),
    }
    return rtnval


def _parse_kind(*, flag_kind_raw: str) -> FlagKind:
    """
        Coerce a string to a :class:`FlagKind` member.

        :param flag_kind_raw: Raw string from the request body.

        :returns: The matching :class:`FlagKind`.

        :raises SemanticError: When ``flag_kind_raw`` is unknown.
    """
    try:
        kind = FlagKind(flag_kind_raw)
    except ValueError as exc:
        err_msg = "Unknown flag_kind value: {}".format(flag_kind_raw)
        raise SemanticError(err_msg) from exc
    rtnval = kind
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


class FlagsBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/flags`` endpoints.
    """

    base_path = FLAGS_BASE_PATH
    tags = ["flags", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/flags",
        methods=["POST"],
        doc=Doc(
            summary="Create feature flag",
            description="Register a new feature flag.",
        ),
    )
    def create_flag(request: Request) -> JSONResponse:
        """
            Register a new feature flag.

            :param request: The incoming HTTP request.

            :returns: 201 with the new flag payload.
        """
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)
        actor_user_id = get_request_actor_user_id(request=request)

        try:
            flag_kind = _parse_kind(
                flag_kind_raw=payload.get("flag_kind", ""),
            )
        except SemanticError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        try:
            flag = flag_service.create_flag(
                db_session=db_session,
                flag_key=payload.get("flag_key", ""),
                flag_kind=flag_kind,
                default_value=payload.get("default_value", None),
                rules=payload.get("rules", None),
                actor_user_id=actor_user_id,
            )
        except FlagAlreadyExistsError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc),
            ) from exc

        body = _flag_to_dict(flag)
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/flags/{flag_key}",
        methods=["GET"],
        doc=Doc(
            summary="Read feature flag",
            description="Read the current view of a registered flag.",
        ),
    )
    def read_flag(request: Request) -> JSONResponse:
        """
            Read the current state of a feature flag.

            :param request: The incoming HTTP request.

            :returns: 200 with the flag payload.
        """
        db_session = _require_db_session(request=request)
        flag_key = request.path_params.get("flag_key", "")

        flag = (
            db_session.query(FeatureFlag)
            .filter(FeatureFlag.flag_key == flag_key)
            .first()
        )
        if flag is None:
            err_msg = "Feature flag not found: {}".format(flag_key)
            raise HTTPException(status_code=404, detail=err_msg)

        body = _flag_to_dict(flag)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
