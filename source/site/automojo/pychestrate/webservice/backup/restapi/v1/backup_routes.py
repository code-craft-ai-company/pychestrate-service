"""
.. module:: backup.restapi.v1.backup_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the backups tag.

.. moduleauthor:: Automation Mojo LLC

Implements the backup / disaster-recovery operations from
``specs/openapi/pychestrate.yaml``:

* ``POST /api/v1/backups`` -- trigger a manual backup.
* ``GET  /api/v1/backups`` -- list backup records (paginated).
* ``GET  /api/v1/backups/{backup_id}`` -- read status / manifest.
* ``POST /api/v1/backups/{backup_id}:restore`` -- request a
  restore. Restore execution is a documented follow-on for the
  p21d milestone -- this route validates the target backup and
  answers ``501 Not Implemented`` until the restore executor
  ships.

All routes are cookie / RBAC gated (``system:backups.read`` /
``system:backups.write``) and emit RFC 7807 problem documents via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.backup import service as backup_service
from automojo.pychestrate.webservice.backup.errors import (
    BackupBackendUnavailableError,
    BackupRecordNotFoundError,
    BackupRequestInvalidError,
    BackupRestoreNotImplementedError,
)
from automojo.pychestrate.webservice.backup.models import BackupStatus
from automojo.pychestrate.webservice.backup.service import (
    BackupAspects,
    BackupRecordView,
)
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


BACKUPS_PATH = "/backups"

BACKUPS_READ_PERMISSION_KEY = "system:backups.read"
BACKUPS_WRITE_PERMISSION_KEY = "system:backups.write"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.backup.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks
        problem response.
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
        middleware, or ``None`` for anonymous requests.

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


def _decode_optional_json_object(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, treating an
        empty body as an empty object. Aborts 422 only on a
        present-but-malformed body.

        :param request: Incoming webworks request.

        :returns: Decoded dict (possibly empty).
    """
    raw = request.body
    if raw is None or len(raw) == 0:
        rtnval: Dict[str, Any] = {}
        return rtnval

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


def _parse_status_filter(*, request: Request) -> Optional[BackupStatus]:
    """
        Coerce the optional ``status`` query param into a
        :class:`BackupStatus`, aborting 400 on an unknown value.

        :param request: Incoming webworks request.

        :returns: A :class:`BackupStatus` or None.
    """
    raw = request.query_params.get("status", None)
    if raw is None or len(raw) == 0:
        rtnval: Optional[BackupStatus] = None
        return rtnval

    try:
        rtnval = BackupStatus(raw)
    except ValueError:
        allowed = [member.value for member in BackupStatus]
        _abort_problem(
            request=request,
            status=400,
            detail="Query param 'status' must be one of {}.".format(allowed),
            extensions={"query_param": "status", "raw_value": raw},
        )
        rtnval = None  # unreachable
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


def _view_to_dict(view: BackupRecordView) -> Dict[str, Any]:
    """
        Serialize a :class:`BackupRecordView` to the OpenAPI
        ``BackupRecord`` schema.

        :param view: Backup record read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "backup_id": view.backup_id,
        "status": view.status,
        "backend": view.backend,
        "archive_uri": view.archive_uri,
        "archive_sha256": view.archive_sha256,
        "size_bytes": view.size_bytes,
        "manifest": dict(view.manifest or {}),
        "error_detail": view.error_detail,
        "note": view.note,
        "created_by": view.created_by,
        "created_at": _iso_or_none(view.created_at),
        "completed_at": _iso_or_none(view.completed_at),
    }
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/backups
# ---------------------------------------------------------------------------


def handle_create_backup(request: Request) -> Response:
    """
        ``POST /api/v1/backups``

        Triggers a manual backup. Snapshots the database,
        object-store references, and secrets metadata into an
        archive written through the configured
        ``backup_storage_backend``.

        :param request: Incoming webworks request.

        :returns: JSON response (201) carrying the completed backup
                  record, or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=BACKUPS_WRITE_PERMISSION_KEY,
        )

        body = _decode_optional_json_object(request=request)

        include_database = body.get("include_database", True)
        include_object_store = body.get("include_object_store", True)
        include_secrets = body.get("include_secrets", True)
        for field_name, field_value in (
                ("include_database", include_database),
                ("include_object_store", include_object_store),
                ("include_secrets", include_secrets),
            ):
            if isinstance(field_value, bool) is False:
                _abort_problem(
                    request=request,
                    status=422,
                    detail="Field '{}' must be a boolean.".format(
                        field_name,
                    ),
                )

        note = body.get("note", "")
        if isinstance(note, str) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'note' must be a string.",
            )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        aspects = BackupAspects(
            include_database=include_database,
            include_object_store=include_object_store,
            include_secrets=include_secrets,
            note=note,
        )

        try:
            view = backup_service.trigger_backup(
                db_session=db_session,
                aspects=aspects,
                actor_id=actor_id,
            )
        except BackupRequestInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
            )
            view = None  # unreachable
        except BackupBackendUnavailableError as xcpt:
            _abort_problem(
                request=request,
                status=503,
                detail=str(xcpt),
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.backup.routes.created backup_id=%s status=%s",
            view.backup_id,
            view.status,
        )

        body_dict = _view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/backups
# ---------------------------------------------------------------------------


def handle_list_backups(request: Request) -> Response:
    """
        ``GET /api/v1/backups``

        Query params: ``status``, ``page``, ``per_page``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=BACKUPS_READ_PERMISSION_KEY,
        )

        status_filter = _parse_status_filter(request=request)
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

        page_result = backup_service.list_backups(
            db_session=db_session,
            status=status_filter,
            page=page,
            per_page=per_page,
        )

        items = []
        for view in page_result["items"]:
            items.append(_view_to_dict(view=view))

        body = {
            "items": items,
            "meta": {
                "page": page,
                "per_page": per_page,
                "total": page_result["total"],
                "next_cursor": None,
            },
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/backups/{backup_id}
# ---------------------------------------------------------------------------


def handle_read_backup(request: Request) -> Response:
    """
        ``GET /api/v1/backups/{backup_id}``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the backup record or a
                  problem response.
    """
    backup_id = request.path_params.get("backup_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=BACKUPS_READ_PERMISSION_KEY,
        )

        try:
            view = backup_service.get_backup(
                db_session=db_session,
                backup_id=backup_id,
            )
        except BackupRecordNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"backup_id": backup_id},
            )
            view = None  # unreachable

        body = _view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/backups/{backup_id}:restore
# ---------------------------------------------------------------------------


def handle_restore_backup(request: Request) -> Response:
    """
        ``POST /api/v1/backups/{backup_id}:restore``

        Requests a restore from a backup. The restore executor is
        a documented follow-on for the p21d milestone -- this
        route validates the target backup, records the request,
        then answers ``501 Not Implemented``.

        :param request: Incoming webworks request.

        :returns: A ``501`` problem response, or ``404`` when the
                  target backup is unknown.
    """
    backup_id = request.path_params.get("backup_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=BACKUPS_WRITE_PERMISSION_KEY,
        )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        try:
            backup_service.request_restore(
                db_session=db_session,
                backup_id=backup_id,
                actor_id=actor_id,
            )
        except BackupRecordNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"backup_id": backup_id},
            )
        except BackupRestoreNotImplementedError as xcpt:
            _abort_problem(
                request=request,
                status=501,
                detail=str(xcpt),
                extensions={"backup_id": backup_id},
            )

        # request_restore always raises -- this line is unreachable.
        rtnval: Response = JSONResponse(
            content={"backup_id": backup_id, "status": "accepted"},
            status_code=202,
        )
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_backup_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the backup / disaster-recovery REST routes to a
        webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + BACKUPS_PATH

    app.attach_route(base, methods=["GET"])(handle_list_backups)
    app.attach_route(base, methods=["POST"])(handle_create_backup)
    app.attach_route(
        base + "/{backup_id}", methods=["GET"],
    )(handle_read_backup)
    app.attach_route(
        base + "/{backup_id}:restore", methods=["POST"],
    )(handle_restore_backup)

    _LOGGER.info(
        "pychestrate.backup.routes.wired: backup trigger + list +"
        " status read + restore-request (501 follow-on) surface."
    )
    return


__all__ = [
    "BACKUPS_PATH",
    "BACKUPS_READ_PERMISSION_KEY",
    "BACKUPS_WRITE_PERMISSION_KEY",
    "register_backup_routes",
    "handle_create_backup",
    "handle_list_backups",
    "handle_read_backup",
    "handle_restore_backup",
]
