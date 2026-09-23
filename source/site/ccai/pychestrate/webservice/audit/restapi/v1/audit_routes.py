"""
.. module:: audit.restapi.v1.audit_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/audit.

.. moduleauthor:: Code Craft AI LLC

The production webservice runs on ``ccai.webworks`` (see
:mod:`app_pychestrate_main`). This module is the webworks-native
REST surface for the M1 audit-record query endpoints.

Two routes:

* ``GET    /api/v1/audit``                          — list records
* ``GET    /api/v1/audit/{sequence_number}``        — read one record

Error responses are RFC 7807 problem documents per the convention
in :mod:`api.problem_json_webworks`. Request-scoped values
(``db_session``) are populated by
:class:`PychestrateSessionMiddleware` from
:mod:`webservice.middleware_webworks`. The ``actor_user_id``
attribute is read by audit *writers* elsewhere; the read endpoints
in this module do not require an authenticated actor — listing
audit records is operator-readable.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.rest_authz import require_rest_permission
from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.audit.models import AuditRecord


AUDIT_PATH = "/audit"

DEFAULT_LIMIT = 50
MIN_LIMIT = 1
MAX_LIMIT = 500


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition once
        and the handler can convert it to a return at the boundary.

        Never escapes this module.
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
        sequence_number: Optional[int] = None
    ) -> None:
    """
        Build a problem response from the request context and raise
        :class:`_ProblemAbort` so the handler returns the response.

        :param request: Incoming webworks request (used for the
                        ``instance`` URI).
        :param status: HTTP status code.
        :param detail: Occurrence-specific explanation.
        :param sequence_number: Optional sequence number to attach
                                as an extension member when
                                referencing a specific record.

        :returns: Never returns; raises :class:`_ProblemAbort`.
        :raises: :class:`_ProblemAbort` always.
    """
    extensions: Optional[dict] = None
    if sequence_number is not None:
        extensions = {"sequence_number": sequence_number}

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
        :class:`PychestrateSessionMiddleware`, or ``None`` when no
        middleware has populated it.

        Module-level so tests can patch this rather than constructing
        a full middleware stack.

        :param request: Incoming webworks request.

        :returns: Session or None.
    """
    rtnval = getattr(request, "db_session", None)
    return rtnval


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort with a 503
        problem document carrying the
        ``"Request-scoped db_session not configured"`` detail on
        misconfigured deployments.

        :param request: Incoming webworks request.

        :returns: Session.
        :raises: :class:`_ProblemAbort` (503) when no session is
                 attached.
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


def _parse_limit_or_abort(*, request: Request) -> int:
    """
        Read the ``limit`` query parameter, coerce to int, and clamp
        to ``[MIN_LIMIT, MAX_LIMIT]``. A non-integer value aborts
        with a 400 problem document.

        :param request: Incoming webworks request.

        :returns: Clamped integer limit.
        :raises: :class:`_ProblemAbort` (400) on non-integer input.
    """
    limit_raw = request.query_params.get("limit", str(DEFAULT_LIMIT))
    try:
        limit = int(limit_raw)
    except (TypeError, ValueError):
        _abort_problem(
            request=request, status=400, detail="Invalid 'limit' argument"
        )

    if limit < MIN_LIMIT:
        limit = MIN_LIMIT
    if limit > MAX_LIMIT:
        limit = MAX_LIMIT

    rtnval = limit
    return rtnval


def _record_to_dict(record: AuditRecord) -> dict:
    """
        Serialize an :class:`AuditRecord` ORM row to its wire-form
        dict.

        :param record: ORM record instance.

        :returns: JSON-friendly dict.
    """
    rtnval = {
        "sequence_number": int(record.sequence_number),
        "record_id": str(record.record_id),
        "kind": record.kind,
        "source_topic": record.source_topic,
        "actor_user_id": (
            str(record.actor_user_id) if record.actor_user_id is not None else None
        ),
        "target_ref": record.target_ref,
        "payload_json": record.payload_json,
        "record_hash_hex": (
            bytes(record.record_hash).hex() if record.record_hash is not None else None
        ),
        "written_at": (
            record.written_at.isoformat() if record.written_at is not None else None
        ),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_list_audit_records(request: Request) -> Response:
    """
        ``GET /api/v1/audit`` — page the audit-record stream newest
        first, capped to ``limit`` (default 50, clamped 1..500).

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a list of record
                  dicts, or a problem response on failure.
    """
    try:
        db_session = _require_session(request=request)
        limit = _parse_limit_or_abort(request=request)

        rows = (
            db_session.query(AuditRecord)
            .order_by(AuditRecord.sequence_number.desc())
            .limit(limit)
            .all()
        )
        body = [_record_to_dict(row) for row in rows]
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


def handle_read_audit_record(request: Request) -> Response:
    """
        ``GET /api/v1/audit/{sequence_number}`` — fetch one audit
        record by its monotonic sequence number. Returns 404 with
        the sequence number as an extension member when the record
        does not exist.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the record dict, or a
                  problem response on failure.
    """
    sequence_number_raw = request.path_params.get("sequence_number", 0)
    sequence_number = int(sequence_number_raw)
    try:
        db_session = _require_session(request=request)

        row = (
            db_session.query(AuditRecord)
            .filter(AuditRecord.sequence_number == sequence_number)
            .first()
        )
        if row is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Audit record not found: {}".format(sequence_number),
                sequence_number=sequence_number,
            )

        body = _record_to_dict(row)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response

    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_audit_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the audit query routes to a webworks application.

        Called from :func:`pychestrate_website_main` -
        :func:`register_service_extensions` before
        ``app.startup``. Routes are queued until the
        infrastructure-ready phase and flushed there.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + AUDIT_PATH

    app.attach_route(base, methods=["GET"])(require_rest_permission(handle_list_audit_records, permission_key="system:audit.read"))
    app.attach_route(
        base + "/{sequence_number:int}", methods=["GET"]
    )(require_rest_permission(handle_read_audit_record, permission_key="system:audit.read"))

    return


__all__ = [
    "AUDIT_PATH",
    "DEFAULT_LIMIT",
    "MIN_LIMIT",
    "MAX_LIMIT",
    "register_audit_routes",
    "handle_list_audit_records",
    "handle_read_audit_record",
]
