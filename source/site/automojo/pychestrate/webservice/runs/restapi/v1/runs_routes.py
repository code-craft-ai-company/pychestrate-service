"""
.. module:: runs.restapi.v1.runs_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/runs and the agent ingest entry points.

.. moduleauthor:: Automation Mojo LLC

This module hosts five planned operations from
``specs/openapi/pychestrate.yaml``:

* ``GET  /api/v1/runs``                       (tag: runs)
* ``GET  /api/v1/runs/{run_id}``              (tag: runs)
* ``POST /api/v1/runs/{run_id}/dispatch-ack`` (tag: dispatch)
* ``POST /api/v1/runs/{run_id}/progress``    (tag: progress)
* ``POST /api/v1/runs/{run_id}/results/complete`` (tag: results)

The three ``POST`` endpoints are the pod-client-agent surface and
the OpenAPI spec scopes them to ``pychestrate_mtls`` security. The
mTLS handshake itself is terminated at the nginx fronting tier;
nginx then forwards the verified client common-name to the WSGI
worker in the ``SSL_CLIENT_S_DN_CN`` environ variable. The handler
treats the *presence* of that variable as proof of a successful
TLS handshake. Until nginx is wired for ``ssl_verify_client on``
the variable will never be present and every call to these
endpoints will short-circuit to a ``401 Unauthorized`` problem
document. This is the intended behaviour for PR p19c -- the HTTP
endpoints exist, but they are unreachable until the deploy script
mounts the client-CA trust bundle into nginx. Enabling mTLS at
nginx is tracked as a follow-up PR.

The two ``GET`` endpoints are operator-facing and accept either a
cookie session or an API key (the spec's default
``pychestrate_session`` / ``pychestrate_api_key``). They require
the ``system:runs.read`` permission key.

Error responses are RFC 7807 problem documents per the
convention in :mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import os

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.ingest.progress.errors import (
    ProgressClientMismatchError,
    ProgressFormatError,
    ProgressUnknownRunError,
)
from automojo.pychestrate.webservice.ingest.progress import (
    service as progress_service,
)
from automojo.pychestrate.webservice.ingest.result.errors import (
    ResultIngestError,
    ResultTreeNotFoundError,
)
from automojo.pychestrate.webservice.ingest.result import scanner as result_scanner
from automojo.pychestrate.webservice.jobs.dispatch import repository as dispatch_repo
from automojo.pychestrate.webservice.jobs.dispatch.receipt import (
    service as receipt_service,
)
from automojo.pychestrate.webservice.jobs.dispatch.receipt.errors import (
    DuplicateRunReceiptError,
    ReceiptEnvelopeMismatchError,
)
from automojo.pychestrate.webservice.jobs.run.state import repository as run_repo
from automojo.pychestrate.webservice.jobs.run.state.errors import (
    RunNotFoundError,
)
from automojo.pychestrate.webservice.jobs.run.state.models import Run
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


RUNS_PATH = "/runs"

#: WSGI environ key nginx populates with the verified client cert
#: common-name after a successful mTLS handshake. Treated as the
#: PR-p19c placeholder for transport-level auth -- presence means
#: "nginx verified a client certificate"; absence means "no mTLS
#: was performed" and the handler returns 401.
MTLS_CLIENT_CN_ENVIRON_KEY = "SSL_CLIENT_S_DN_CN"

#: Permission key the operator-facing GET endpoints require.
RUNS_READ_PERMISSION_KEY = "system:runs.read"

#: Default + bounds for the page-size query param. Matches the
#: OpenAPI ``PerPageParam`` schema (default 50, max 500).
DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.runs.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing (same shape as clients_routes._ProblemAbort)
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
        Return the request-scoped db session attached by the
        session middleware, or ``None`` when none is bound.

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
        Return the ``AuthPrincipal`` attached to the request by
        the session middleware, or ``None`` when the request is
        anonymous.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _resolve_mtls_client_cn(request: Request) -> Optional[str]:
    """
        Return the verified client common-name nginx forwarded for
        this request, or ``None`` when no mTLS handshake completed.

        The lookup walks two carriers:

        * ``request.environ`` (PEP 3333 WSGI environ dict) when the
          underlying transport exposes it -- this is how gunicorn
          presents the ``SSL_CLIENT_S_DN_CN`` header forwarded by
          nginx.
        * A dedicated ``mtls_client_cn`` attribute on the request
          (test seam + future first-class middleware).

        :param request: Incoming webworks request.

        :returns: Client common-name string or None.
    """
    explicit = getattr(request, "mtls_client_cn", None)
    if isinstance(explicit, str) and len(explicit) > 0:
        rtnval = explicit
        return rtnval

    environ = getattr(request, "environ", None)
    if isinstance(environ, dict):
        candidate = environ.get(MTLS_CLIENT_CN_ENVIRON_KEY, None)
        if isinstance(candidate, str) and len(candidate) > 0:
            rtnval = candidate
            return rtnval

    # webworks Request stores the WSGI environ on ``scope`` --
    # check that too so production requests can carry the value.
    scope = getattr(request, "scope", None)
    if isinstance(scope, dict):
        candidate = scope.get(MTLS_CLIENT_CN_ENVIRON_KEY, None)
        if isinstance(candidate, str) and len(candidate) > 0:
            rtnval = candidate
            return rtnval

    rtnval = None
    return rtnval


def _require_mtls_client_cn(request: Request) -> str:
    """
        Resolve the mTLS-verified client common-name or abort 401.

        :param request: Incoming webworks request.

        :returns: Client common-name string.
    """
    candidate = _resolve_mtls_client_cn(request=request)
    if candidate is None:
        _abort_problem(
            request=request,
            status=401,
            detail=(
                "Mutual-TLS client certificate required (nginx must"
                " forward SSL_CLIENT_S_DN_CN)."
            ),
        )
    rtnval = candidate
    return rtnval


def _require_runs_read_permission(*, request: Request, db_session: Any) -> None:
    """
        Require the calling principal to hold ``system:runs.read``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.

        :returns: None.
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
        permission_key=RUNS_READ_PERMISSION_KEY,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(RUNS_READ_PERMISSION_KEY),
            extensions={"required_permission": RUNS_READ_PERMISSION_KEY},
        )
    return


def _decode_json_object_or_abort(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, aborting 400 on
        missing / malformed / non-dict.

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
            status=400,
            detail="Request body must be JSON.",
        )
    if isinstance(payload, dict) is False:
        _abort_problem(
            request=request,
            status=400,
            detail="Request body must be a JSON object.",
        )

    rtnval = payload
    return rtnval


# ---------------------------------------------------------------------------
# Run serializer
# ---------------------------------------------------------------------------


def _iso_or_none(value: Any) -> Optional[str]:
    """
        ISO-8601 serialize a datetime, or return ``None``.

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


def _enum_value_or_none(value: Any) -> Optional[str]:
    """
        Return the ``.value`` of a string-enum or ``None``.

        :param value: Enum instance or None.

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


def _run_to_dict(row: Run) -> Dict[str, Any]:
    """
        Serialize a :class:`Run` row to the OpenAPI ``Run`` schema.

        The in-tree ``Run`` model carries a strict subset of the
        OpenAPI schema's properties (see the divergence note in
        the PR body). Missing fields are emitted as ``null``;
        downstream extensions / future migrations will fill them
        in once the model grows.

        :param row: Run ORM row.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "run_id": str(row.run_id),
        "project_id": str(row.project_id),
        "pod_id": None,
        "client_id": None,
        "job_id": None,
        "job_name": None,
        "job_type": str(row.job_type) if row.job_type is not None else "",
        "state": _enum_value_or_none(row.state),
        "terminal_outcome": _enum_value_or_none(row.terminal_outcome),
        "current_dispatch_attempt_id": None,
        "progress_summary": None,
        "created_at": _iso_or_none(row.entered_state_at),
        "dispatched_at": None,
        "started_at": None,
        "completed_at": None,
        "labels": {},
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/runs
# ---------------------------------------------------------------------------


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
        Empty / None returns ``default``.

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
        candidate = default  # unreachable -- _abort_problem raises.

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


def handle_list_runs(request: Request) -> Response:
    """
        ``GET /api/v1/runs`` -- list runs with optional filters.

        Query params: ``project_id``, ``pod_id``, ``state``,
        ``page``, ``per_page``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) carrying a
                  ``{items, meta}`` page, or a problem response.
    """
    try:
        db_session = _require_session(request=request)
        _require_runs_read_permission(
            request=request, db_session=db_session,
        )

        project_id = request.query_params.get("project_id", None)
        state_filter = request.query_params.get("state", None)
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

        query = db_session.query(Run)
        if project_id is not None and len(project_id) > 0:
            query = query.filter(Run.project_id == project_id)
        if state_filter is not None and len(state_filter) > 0:
            query = query.filter(Run.state == state_filter)

        total = query.count()
        offset = (page - 1) * per_page
        rows = (
            query.order_by(Run.entered_state_at.desc())
            .offset(offset)
            .limit(per_page)
            .all()
        )

        items: List[Dict[str, Any]] = []
        for row in rows:
            items.append(_run_to_dict(row=row))

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


# ---------------------------------------------------------------------------
# GET /api/v1/runs/{run_id}
# ---------------------------------------------------------------------------


def handle_read_run(request: Request) -> Response:
    """
        ``GET /api/v1/runs/{run_id}`` -- single run view.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the run dict or
                  problem response on failure.
    """
    run_id = request.path_params.get("run_id", "")
    try:
        db_session = _require_session(request=request)
        _require_runs_read_permission(
            request=request, db_session=db_session,
        )

        try:
            row = run_repo.get_run(db_session=db_session, run_id=run_id)
        except RunNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
            row = None  # unreachable

        body = _run_to_dict(row=row)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/runs/{run_id}/dispatch-ack
# ---------------------------------------------------------------------------


def _require_run_exists(*, request: Request, db_session: Any, run_id: str) -> Run:
    """
        Fetch the run row, aborting 404 when missing.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the path.

        :returns: The :class:`Run` row.
    """
    row = run_repo.find_run(db_session=db_session, run_id=run_id)
    if row is None:
        _abort_problem(
            request=request,
            status=404,
            detail="Run not found.",
            extensions={"run_id": run_id},
        )
    rtnval = row
    return rtnval


def handle_dispatch_ack(request: Request) -> Response:
    """
        ``POST /api/v1/runs/{run_id}/dispatch-ack`` -- pod client
        agent acknowledges receipt of a dispatched envelope.

        Idempotent: replaying the same ack returns 202 with the
        same body (matching the receipt service's behaviour).

        :param request: Incoming webworks request.

        :returns: JSON response (202) or problem response.
    """
    run_id = request.path_params.get("run_id", "")
    try:
        client_cn = _require_mtls_client_cn(request=request)
        payload = _decode_json_object_or_abort(request=request)
        db_session = _require_session(request=request)
        run_row = _require_run_exists(
            request=request, db_session=db_session, run_id=run_id,
        )

        envelope_id = payload.get("envelope_id", None)
        dispatch_attempt_id = payload.get("dispatch_attempt_id", None)
        body_client_id = payload.get("client_id", None)
        local_run_id = payload.get("local_run_id", None)
        accepted_at_raw = payload.get("accepted_at", None)

        missing_fields: List[str] = []
        if not isinstance(envelope_id, str) or len(envelope_id) == 0:
            missing_fields.append("envelope_id")
        if not isinstance(dispatch_attempt_id, str) or len(dispatch_attempt_id) == 0:
            missing_fields.append("dispatch_attempt_id")
        if not isinstance(body_client_id, str) or len(body_client_id) == 0:
            missing_fields.append("client_id")
        if not isinstance(local_run_id, str) or len(local_run_id) == 0:
            missing_fields.append("local_run_id")
        if not isinstance(accepted_at_raw, str) or len(accepted_at_raw) == 0:
            missing_fields.append("accepted_at")
        if len(missing_fields) > 0:
            _abort_problem(
                request=request,
                status=400,
                detail="Missing required field(s): {}".format(
                    ", ".join(missing_fields),
                ),
                extensions={"missing_fields": missing_fields},
            )

        try:
            accepted_at = datetime.fromisoformat(accepted_at_raw)
        except ValueError:
            _abort_problem(
                request=request,
                status=400,
                detail="Field 'accepted_at' must be ISO-8601.",
                extensions={"field": "accepted_at"},
            )
            accepted_at = datetime.now(timezone.utc)  # unreachable

        attempt = dispatch_repo.get_attempt(
            db_session=db_session, attempt_id=dispatch_attempt_id,
        )
        if attempt is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Dispatch attempt not found.",
                extensions={
                    "run_id": run_id,
                    "dispatch_attempt_id": dispatch_attempt_id,
                },
            )

        if str(attempt.run_id) != run_id:
            _abort_problem(
                request=request,
                status=400,
                detail="Dispatch attempt does not belong to this run.",
                extensions={
                    "run_id": run_id,
                    "dispatch_attempt_id": dispatch_attempt_id,
                },
            )

        try:
            receipt_service.record(
                db_session=db_session,
                run_id=run_id,
                project_id=str(attempt.project_id),
                client_id=body_client_id,
                attempt_id=dispatch_attempt_id,
                envelope_id=envelope_id,
                client_local_run_id=local_run_id,
                received_at=accepted_at,
            )
        except DuplicateRunReceiptError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
        except ReceiptEnvelopeMismatchError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={
                    "run_id": run_id,
                    "envelope_id": envelope_id,
                },
            )

        _LOGGER.info(
            "pychestrate.runs.dispatch_ack run_id=%s client_cn=%s",
            run_id,
            client_cn,
        )

        body = {
            "run_id": run_id,
            "dispatch_attempt_id": dispatch_attempt_id,
            "status": "acked",
        }
        rtnval: Response = JSONResponse(content=body, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/runs/{run_id}/progress
# ---------------------------------------------------------------------------


def handle_post_progress(request: Request) -> Response:
    """
        ``POST /api/v1/runs/{run_id}/progress`` -- live progress
        frame from the pod client agent.

        :param request: Incoming webworks request.

        :returns: JSON response (202) or problem response.
    """
    run_id = request.path_params.get("run_id", "")
    try:
        client_cn = _require_mtls_client_cn(request=request)
        payload = _decode_json_object_or_abort(request=request)
        db_session = _require_session(request=request)
        _require_run_exists(
            request=request, db_session=db_session, run_id=run_id,
        )

        summary_payload = payload.get("summary", None)
        records_payload = payload.get("records", None)
        if summary_payload is None and records_payload is None:
            _abort_problem(
                request=request,
                status=400,
                detail="ProgressFrame must include 'summary' or 'records'.",
            )
        if records_payload is not None and isinstance(records_payload, list) is False:
            _abort_problem(
                request=request,
                status=400,
                detail="ProgressFrame 'records' must be an array.",
            )

        summaries_accepted = 0
        records_accepted = 0

        try:
            if summary_payload is not None:
                if isinstance(summary_payload, dict) is False:
                    _abort_problem(
                        request=request,
                        status=400,
                        detail="ProgressFrame 'summary' must be an object.",
                    )

                summary_client_id = summary_payload.get("client_id", "")
                format_tag = summary_payload.get("format_tag", "")
                if isinstance(summary_client_id, str) is False or len(summary_client_id) == 0:
                    _abort_problem(
                        request=request,
                        status=400,
                        detail="ProgressFrame summary missing 'client_id'.",
                    )
                if isinstance(format_tag, str) is False or len(format_tag) == 0:
                    _abort_problem(
                        request=request,
                        status=400,
                        detail="ProgressFrame summary missing 'format_tag'.",
                    )

                progress_service.ingest_summary(
                    db_session=db_session,
                    run_id=run_id,
                    authenticated_client_id=summary_client_id,
                    format_tag=format_tag,
                    payload=summary_payload,
                )
                summaries_accepted = 1

            if records_payload is not None:
                for index, record in enumerate(records_payload):
                    if isinstance(record, dict) is False:
                        _abort_problem(
                            request=request,
                            status=400,
                            detail="ProgressFrame record #{} must be an object.".format(index),
                        )
                    record_client_id = record.get("client_id", "")
                    record_index = record.get("record_index", None)
                    record_format_tag = record.get("format_tag", "testbase")
                    if isinstance(record_client_id, str) is False or len(record_client_id) == 0:
                        _abort_problem(
                            request=request,
                            status=400,
                            detail="ProgressFrame record #{} missing 'client_id'.".format(index),
                        )
                    if isinstance(record_index, int) is False:
                        _abort_problem(
                            request=request,
                            status=400,
                            detail="ProgressFrame record #{} 'record_index' must be int.".format(index),
                        )

                    progress_service.ingest_record(
                        db_session=db_session,
                        run_id=run_id,
                        authenticated_client_id=record_client_id,
                        record_index=record_index,
                        format_tag=record_format_tag,
                        payload=record,
                    )
                    records_accepted += 1
        except ProgressUnknownRunError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
        except ProgressClientMismatchError as xcpt:
            _abort_problem(
                request=request,
                status=403,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
        except ProgressFormatError as xcpt:
            _abort_problem(
                request=request,
                status=400,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )

        _LOGGER.info(
            "pychestrate.runs.progress run_id=%s client_cn=%s summaries=%d records=%d",
            run_id,
            client_cn,
            summaries_accepted,
            records_accepted,
        )

        body = {
            "run_id": run_id,
            "summaries_accepted": summaries_accepted,
            "records_accepted": records_accepted,
        }
        rtnval: Response = JSONResponse(content=body, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/runs/{run_id}/results/complete
# ---------------------------------------------------------------------------


def handle_post_results_complete(request: Request) -> Response:
    """
        ``POST /api/v1/runs/{run_id}/results/complete`` -- pod
        client agent signals that the testbase result tree is
        fully uploaded.

        For PR p19c the scan is triggered synchronously inside the
        handler; later milestones move it to the scheduler from PR
        p19b. The handler is tolerant of scanner errors: a missing
        tree returns 409, a parse failure returns 502.

        :param request: Incoming webworks request.

        :returns: JSON response (202) or problem response.
    """
    run_id = request.path_params.get("run_id", "")
    try:
        client_cn = _require_mtls_client_cn(request=request)
        payload = _decode_json_object_or_abort(request=request)
        db_session = _require_session(request=request)
        _require_run_exists(
            request=request, db_session=db_session, run_id=run_id,
        )

        client_id_field = payload.get("client_id", None)
        format_tag = payload.get("format_tag", None)
        backend_key_prefix = payload.get("backend_key_prefix", None)
        completed_at_raw = payload.get("completed_at", None)
        terminal_outcome = payload.get("terminal_outcome", None)

        missing_fields: List[str] = []
        if not isinstance(client_id_field, str) or len(client_id_field) == 0:
            missing_fields.append("client_id")
        if not isinstance(format_tag, str) or len(format_tag) == 0:
            missing_fields.append("format_tag")
        if not isinstance(backend_key_prefix, str) or len(backend_key_prefix) == 0:
            missing_fields.append("backend_key_prefix")
        if not isinstance(completed_at_raw, str) or len(completed_at_raw) == 0:
            missing_fields.append("completed_at")
        if not isinstance(terminal_outcome, str) or len(terminal_outcome) == 0:
            missing_fields.append("terminal_outcome")
        if len(missing_fields) > 0:
            _abort_problem(
                request=request,
                status=400,
                detail="Missing required field(s): {}".format(
                    ", ".join(missing_fields),
                ),
                extensions={"missing_fields": missing_fields},
            )

        scan_status = "scheduled"
        scan_detail: Optional[str] = None
        try:
            outcome = result_scanner.scan_once(
                db_session=db_session,
                run_id=run_id,
                tree_path=backend_key_prefix,
            )
            scan_status = "scanned"
            scan_detail = getattr(outcome, "status", None)
        except ResultTreeNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={
                    "run_id": run_id,
                    "backend_key_prefix": backend_key_prefix,
                },
            )
        except ResultIngestError as xcpt:
            # Parse failures shouldn't deny the manifest; record the
            # failure and let the operator inspect via the run-event
            # SSE stream + audit log. Per the OpenAPI description
            # "errors in downstream parsing are surfaced via the
            # RunEvent SSE stream" -- we still return 202 here.
            _LOGGER.warning(
                "pychestrate.runs.results_complete.scan_error run_id=%s err=%s",
                run_id,
                xcpt,
            )
            scan_status = "scan_deferred"
            scan_detail = str(xcpt)

        _LOGGER.info(
            "pychestrate.runs.results_complete run_id=%s client_cn=%s status=%s",
            run_id,
            client_cn,
            scan_status,
        )

        body: Dict[str, Any] = {
            "run_id": run_id,
            "status": scan_status,
            "terminal_outcome": terminal_outcome,
        }
        if scan_detail is not None:
            body["scan_detail"] = scan_detail
        rtnval: Response = JSONResponse(content=body, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_runs_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the runs-feature routes (operator read + agent
        ingest) to a webworks application.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + RUNS_PATH
    app.attach_route(base, methods=["GET"])(handle_list_runs)
    app.attach_route(
        base + "/{run_id}", methods=["GET"],
    )(handle_read_run)
    app.attach_route(
        base + "/{run_id}/dispatch-ack", methods=["POST"],
    )(handle_dispatch_ack)
    app.attach_route(
        base + "/{run_id}/progress", methods=["POST"],
    )(handle_post_progress)
    app.attach_route(
        base + "/{run_id}/results/complete", methods=["POST"],
    )(handle_post_results_complete)

    _LOGGER.warning(
        "pychestrate.runs.routes.mtls_not_wired: ingest endpoints"
        " (/dispatch-ack, /progress, /results/complete) require"
        " nginx mTLS but nginx is not configured for client-cert"
        " auth in PR p19c; these endpoints will reject every"
        " request with 401 until SSL_CLIENT_S_DN_CN is forwarded."
    )
    return


__all__ = [
    "RUNS_PATH",
    "MTLS_CLIENT_CN_ENVIRON_KEY",
    "RUNS_READ_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_runs_routes",
    "handle_list_runs",
    "handle_read_run",
    "handle_dispatch_ack",
    "handle_post_progress",
    "handle_post_results_complete",
]
