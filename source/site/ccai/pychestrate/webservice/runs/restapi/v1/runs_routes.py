"""
.. module:: runs.restapi.v1.runs_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native REST routes for /api/v1/runs and the agent ingest entry points.

.. moduleauthor:: Code Craft AI LLC

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

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging
import os

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.ingest.progress.errors import (
    ProgressClientMismatchError,
    ProgressFormatError,
    ProgressUnknownRunError,
)
from ccai.pychestrate.webservice.ingest.progress import (
    service as progress_service,
)
from ccai.pychestrate.webservice.ingest.result.errors import (
    ResultIngestError,
    ResultTreeNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.rpa.errors import (
    RpaJobNotFoundError,
)
from ccai.pychestrate.webservice.ingest.result import (
    classification as result_classification,
)
from ccai.pychestrate.webservice.ingest.result import scanner as result_scanner
from ccai.pychestrate.webservice.ingest.result import (
    completion as result_completion,
)
from ccai.pychestrate.webservice.ingest.result.events import (
    ResultEventTopics,
)
from ccai.pychestrate.webservice.orchestration.build.errors import (
    BuildRunNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.infra.runs.errors import (
    InfraRunNotFoundError,
)
from ccai.pychestrate.webservice.ingest.progress.factories.testbase_v1 import (
    TESTBASE_V1_FORMAT_TAG,
)
from ccai.pychestrate.webservice.jobs.cancel.client_cancel import (
    queue_client_cancel,
    set_active_cancel_dispatcher,
)
from ccai.pychestrate.webservice.jobs.cancel.heartbeattransport import (
    acknowledge_client_cancellation,
)
from ccai.pychestrate.webservice.jobs.dispatch import repository as dispatch_repo
from ccai.pychestrate.webservice.jobs.dispatch.receipt import (
    service as receipt_service,
)
from ccai.pychestrate.webservice.jobs.dispatch.receipt.errors import (
    DuplicateRunReceiptError,
    ReceiptEnvelopeMismatchError,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    repository as envelope_repo,
)
from ccai.pychestrate.webservice.jobs.results.artifact_root import (
    resolve_result_tree_path,
)
from ccai.pychestrate.webservice.jobs.results.errors import (
    ArtifactPathInvalidError,
)
from ccai.pychestrate.webservice.jobs.run.state import repository as run_repo
from ccai.pychestrate.webservice.jobs.run.state.enums import (
    RunEvent,
    RunState,
    TERMINAL_STATES,
)
from ccai.pychestrate.webservice.jobs.run.state.machine import (
    transition as _run_state_transition,
)
from ccai.pychestrate.webservice.jobs.run.state.advance import (
    advance_to_cancelled as _advance_to_cancelled,
)
from ccai.pychestrate.webservice.jobs.run.state.advance import (
    advance_to_dispatched as _advance_to_dispatched,
    advance_to_terminal as _advance_to_terminal,
    note_progress as _note_progress,
)
from ccai.pychestrate.webservice.jobs.run.state.errors import (
    IllegalTransitionError,
    RunNotFoundError,
    TerminalStateError,
)
from ccai.pychestrate.webservice.jobs.run.state.machine import (
    request_cancel as _request_cancel,
)
from ccai.pychestrate.webservice.jobs.run.state.models import Run
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


RUNS_PATH = "/runs"

#: WSGI environ key nginx populates with the verified client cert
#: common-name after a successful mTLS handshake. Treated as the
#: PR-p19c placeholder for transport-level auth -- presence means
#: "nginx verified a client certificate"; absence means "no mTLS
#: was performed" and the handler returns 401.
MTLS_CLIENT_CN_ENVIRON_KEY = "SSL_CLIENT_S_DN_CN"

#: Permission key the operator-facing GET endpoints require.
RUNS_READ_PERMISSION_KEY = "system:runs.read"

#: Permission required to cancel an in-flight run: the project-scoped
#: ``project:runs.cancel`` grant registered in
#: ``security.rbac.extensions.project_roles``. The evaluator needs the
#: run's project in the key (``project:<id>:runs.cancel``); build it with
#: :func:`runs_cancel_permission_key`.
RUNS_CANCEL_PERMISSION_KEY = "project:runs.cancel"
RUNS_CANCEL_PERMISSION_ACTION = "runs.cancel"
#: System-wide alternative (granted to system-admin): cancel any run.
RUNS_CANCEL_SYSTEM_PERMISSION_KEY = "system:runs.cancel"


def runs_cancel_permission_key(*, project_id: str) -> str:
    """
        :param project_id: The run's project UUID.

        :returns: ``project:<project_id>:runs.cancel``.
    """
    rtnval = "project:{}:{}".format(project_id, RUNS_CANCEL_PERMISSION_ACTION)
    return rtnval

#: Parser tag a progress record without its own ``format_tag`` gets when
#: its frame carries no summary either: the registered testbase parser.
DEFAULT_PROGRESS_RECORD_FORMAT_TAG = TESTBASE_V1_FORMAT_TAG

#: Notes prefix a pod uses when it refuses a dispatch; the run is ended.
DISPATCH_REJECTED_NOTE_PREFIX = "REJECTED:"

#: ``TerminalOutcome`` value a pod reports when an operator cancel
#: stopped the run. Distinguished from ``failure`` at ingest so a
#: cancelled run does not land in ``FAILED``.
TERMINAL_OUTCOME_CANCELLED = "cancelled"

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


def _load_latest_dispatch_attempt(
        *,
        db_session: Any,
        run_id: str
    ) -> Optional[Any]:
    """
        Return the most recent :class:`DispatchAttempt` row for the
        run, or ``None`` when the run has never been dispatched.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: The latest attempt row or None.
    """
    attempts = dispatch_repo.list_attempts_for_run(
        db_session=db_session, run_id=run_id,
    )
    if len(attempts) == 0:
        rtnval = None
        return rtnval
    rtnval = attempts[-1]
    return rtnval


def _load_envelope_job_fields(
        *,
        db_session: Any,
        envelope_id: str
    ) -> Tuple[Optional[str], Optional[str]]:
    """
        Resolve ``(job_id, job_name)`` from the archived dispatch
        envelope. ``job_id`` is a first-class column on the
        envelope archive row; ``job_name`` only exists inside the
        canonical signed payload, so it is parsed out of the
        archived ``canonical_payload_text`` JSON.

        :param db_session: Active SQLAlchemy session.
        :param envelope_id: Envelope UUID from the dispatch attempt.

        :returns: ``(job_id, job_name)`` — either element is None
                  when unrecoverable.
    """
    record = envelope_repo.get_envelope(
        db_session=db_session, envelope_id=envelope_id,
    )
    if record is None:
        rtnval = (None, None)
        return rtnval

    job_id: Optional[str] = None
    if record.job_id is not None:
        job_id = str(record.job_id)

    job_name: Optional[str] = None
    payload_text = getattr(record, "canonical_payload_text", None)
    if isinstance(payload_text, str) and len(payload_text) > 0:
        try:
            canonical = json.loads(payload_text)
        except ValueError:
            canonical = None
        if isinstance(canonical, dict):
            candidate = canonical.get("job_name", None)
            if isinstance(candidate, str) and len(candidate) > 0:
                job_name = candidate

    rtnval = (job_id, job_name)
    return rtnval


def _progress_summary_block(
        *,
        db_session: Any,
        run_id: str
    ) -> Optional[Dict[str, Any]]:
    """
        Build the OpenAPI ``ProgressSummary`` block for a run from
        the ingested progress data.

        Test runs roll up through the latest posted test summary
        (``ingest_run_progress_summary``). Build / provision runs
        have no test-shaped summary — their latest generalized
        progress frame (``ingest_run_progress_frame``) is mapped
        into the same block instead, carrying ``frame_kind`` /
        ``phase`` / ``status`` alongside zeroed test counters.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: A ``ProgressSummary``-shaped dict, or None when
                  no progress has been ingested for the run.
    """
    summary = progress_service.get_summary(
        db_session=db_session, run_id=run_id,
    )
    if summary is not None:
        rtnval: Dict[str, Any] = {
            "run_id": summary.run_id,
            "client_id": summary.client_id,
            "format_tag": summary.format_tag,
            "tests_total": summary.tests_total,
            "tests_passed": summary.tests_passed,
            "tests_failed": summary.tests_failed,
            "tests_skipped": summary.tests_skipped,
            "tests_errored": summary.tests_errored,
            "percent_complete": summary.percent_complete,
            "notes": summary.notes,
            "recorded_at": _iso_or_none(summary.recorded_at),
        }
        return rtnval

    frame = progress_service.get_latest_frame(
        db_session=db_session, run_id=run_id,
    )
    if frame is not None:
        rtnval = {
            "run_id": frame.run_id,
            "client_id": frame.client_id,
            "format_tag": frame.frame_kind,
            "frame_kind": frame.frame_kind,
            "phase": frame.phase,
            "status": frame.status,
            "tests_total": None,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_skipped": 0,
            "tests_errored": 0,
            "percent_complete": frame.percent_complete,
            "notes": frame.notes,
            "recorded_at": _iso_or_none(frame.recorded_at),
        }
        return rtnval

    rtnval = None
    return rtnval


def _load_result_manifest_block(
        *,
        db_session: Any,
        run_id: str
    ) -> Optional[Dict[str, Any]]:
    """
        Recall the run's latest recorded result-manifest block from
        the durable event outbox.

        ``POST /runs/{run_id}/results/complete`` writes a
        ``MANIFEST_LANDED`` outbox row whose payload carries the
        ``manifest`` block the SSE ``result_manifest`` RunEvent
        streams. Recalling it here lets the single-run read model
        serve the same block after the fact, so a run-detail page
        opened on an already-completed run can render its
        artifacts pane without having watched the live stream.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.

        :returns: The manifest block dict, or None when the run
                  has never posted results-complete.
    """
    outbox_row = run_repo.find_latest_outbox_row_for_topic(
        db_session=db_session,
        run_id=run_id,
        topic=ResultEventTopics.MANIFEST_LANDED,
    )
    if outbox_row is None:
        rtnval = None
        return rtnval

    payload = outbox_row.payload
    if isinstance(payload, dict) is False:
        rtnval = None
        return rtnval

    manifest = payload.get("manifest", None)
    if isinstance(manifest, dict) is False:
        rtnval = None
        return rtnval

    rtnval = manifest
    return rtnval


def _run_timing_block(
        *,
        db_session: Any,
        row: Run
    ) -> Dict[str, Optional[str]]:
    """
        Derive the run's lifecycle timestamps from the append-only
        state-audit trail.

        The ``Run`` row only keeps ``entered_state_at`` (mutated on
        every transition), so the stable timestamps come from the
        audit history:

        * ``created_at`` — the first audit row's ``transitioned_at``
          (the run entered its initial state at creation and the
          row existed only milliseconds before its first
          transition). A run that has never transitioned still has
          ``entered_state_at`` == creation time, so that is the
          fallback.
        * ``dispatched_at`` — first transition into ``DISPATCHED``.
        * ``started_at`` — first transition into ``RUNNING``.
        * ``completed_at`` — first transition into a terminal
          state; falls back to ``entered_state_at`` when the row is
          terminal but predates audit coverage.

        :param db_session: Active SQLAlchemy session.
        :param row: Run ORM row.

        :returns: Dict with ``created_at`` / ``dispatched_at`` /
                  ``started_at`` / ``completed_at`` ISO strings or
                  None.
    """
    audits = run_repo.list_state_audits(
        db_session=db_session, run_id=str(row.run_id),
    )

    created_at: Optional[Any] = None
    dispatched_at: Optional[Any] = None
    started_at: Optional[Any] = None
    completed_at: Optional[Any] = None

    for audit in audits:
        if created_at is None:
            created_at = audit.transitioned_at
        if dispatched_at is None and audit.to_state == RunState.DISPATCHED:
            dispatched_at = audit.transitioned_at
        if started_at is None and audit.to_state == RunState.RUNNING:
            started_at = audit.transitioned_at
        if completed_at is None and audit.to_state in TERMINAL_STATES:
            completed_at = audit.transitioned_at

    if created_at is None:
        created_at = row.entered_state_at
    if completed_at is None and row.state in TERMINAL_STATES:
        completed_at = row.entered_state_at

    rtnval: Dict[str, Optional[str]] = {
        "created_at": _iso_or_none(created_at),
        "dispatched_at": _iso_or_none(dispatched_at),
        "started_at": _iso_or_none(started_at),
        "completed_at": _iso_or_none(completed_at),
    }
    return rtnval


def _outcome_reason(
        *,
        db_session: Any,
        row: Any,
        result_manifest: Optional[Dict[str, Any]]
    ) -> Optional[str]:
    """
        Why the run is where it is, for the run detail view: the pod's
        notes on its result manifest (why the job failed or was stopped),
        else the reason recorded with the transition into the current
        terminal state (a rejected dispatch, a passed deadline, ...),
        else -- for a run awaiting a cancel -- the cancel reason.

        :param db_session: Active SQLAlchemy session.
        :param row: The :class:`Run` row.
        :param result_manifest: The run's manifest block, if loaded.

        :returns: The reason text, or ``None`` when there is none.
    """
    if isinstance(result_manifest, dict):
        notes = result_manifest.get("notes", None)
        if isinstance(notes, str) and len(notes.strip()) > 0:
            rtnval: Optional[str] = notes.strip()
            return rtnval
    if row.state in TERMINAL_STATES:
        audits = run_repo.list_state_audits(db_session=db_session, run_id=str(row.run_id))
        entering = [audit for audit in audits if getattr(audit, "to_state", None) == row.state]
        if len(entering) > 0:
            reason = getattr(entering[-1], "reason", None)
            if isinstance(reason, str) and len(reason.strip()) > 0:
                rtnval = reason.strip()
                return rtnval
    if row.state == RunState.CANCEL_REQUESTED:
        cancel_reason = getattr(row, "cancel_reason", None)
        if isinstance(cancel_reason, str) and len(cancel_reason.strip()) > 0:
            rtnval = "Cancel requested: {}".format(cancel_reason.strip())
            return rtnval
    rtnval = None
    return rtnval


def _assigned_client_block(*, db_session: Any, client_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """
        The client the run was dispatched to, as the run page needs it
        to say "waiting for pod <name>, last heard from <when>" instead
        of sitting silently in DISPATCHED while that pod is offline
        (E2E-16).

        :param db_session: Active SQLAlchemy session.
        :param client_id: The latest dispatch attempt's client, if any.

        :returns: ``{client_id, pod_name, status, liveness_state,
                  last_seen}``, or None when there is no such client.
    """
    if client_id is None:
        return None
    from ccai.pychestrate.webservice.clients.models import Client  # noqa: E402

    try:
        client = db_session.query(Client).filter(Client.client_id == client_id).first()
    except Exception:
        # Sessions without the clients table (unit-test fakes) have no
        # client to describe.
        client = None
    if client is None:
        return None
    rtnval = {
        "client_id": str(client.client_id),
        "pod_name": client.pod_name,
        "status": _enum_value_or_none(client.status),
        "liveness_state": _enum_value_or_none(client.liveness_state),
        "last_seen": _iso_or_none(client.last_seen),
    }
    return rtnval


def _run_to_dict(
        *,
        row: Run,
        db_session: Any,
        include_result_manifest: bool = False
    ) -> Dict[str, Any]:
    """
        Serialize a :class:`Run` row to the OpenAPI ``Run`` schema.

        The ``Run`` row itself only carries the state-machine
        columns; the rest of the schema is joined in from the
        feature tables that own each fact:

        * ``pod_id`` / ``client_id`` /
          ``current_dispatch_attempt_id`` — latest
          ``jobs_dispatch_attempt`` row.
        * ``job_id`` / ``job_name`` — the archived dispatch
          envelope the latest attempt transmitted.
        * ``progress_summary`` — latest ingested progress summary
          (test runs) or generalized progress frame (build /
          provision runs).
        * ``created_at`` / ``dispatched_at`` / ``started_at`` /
          ``completed_at`` — derived from the append-only
          state-audit trail (see :func:`_run_timing_block`).
        * ``result_manifest`` — the latest recorded
          result-manifest block, recalled from the durable event
          outbox. Only loaded when ``include_result_manifest`` is
          True (the single-run read); list pages keep it ``null``
          so a 500-row page does not drag every manifest's file
          index along.

        Facts the data model does not record (``labels``) are
        emitted empty.

        :param row: Run ORM row.
        :param db_session: Active SQLAlchemy session used to join
                           the feature tables.
        :param include_result_manifest: Load the recorded result
                                        manifest into the payload.

        :returns: JSON-friendly dict.
    """
    run_id = str(row.run_id)

    pod_id: Optional[str] = None
    client_id: Optional[str] = None
    current_attempt_id: Optional[str] = None
    job_id: Optional[str] = None
    job_name: Optional[str] = None

    attempt = _load_latest_dispatch_attempt(
        db_session=db_session, run_id=run_id,
    )
    if attempt is not None:
        pod_id = str(attempt.pod_id)
        client_id = str(attempt.client_id)
        current_attempt_id = str(attempt.attempt_id)
        job_id, job_name = _load_envelope_job_fields(
            db_session=db_session,
            envelope_id=str(attempt.envelope_id),
        )

    progress_summary = _progress_summary_block(
        db_session=db_session, run_id=run_id,
    )
    timings = _run_timing_block(db_session=db_session, row=row)

    result_manifest: Optional[Dict[str, Any]] = None
    if include_result_manifest is True:
        result_manifest = _load_result_manifest_block(
            db_session=db_session, run_id=run_id,
        )

    outcome_reason: Optional[str] = None
    assigned_client: Optional[Dict[str, Any]] = None
    if include_result_manifest is True:
        outcome_reason = _outcome_reason(
            db_session=db_session, row=row, result_manifest=result_manifest,
        )
        assigned_client = _assigned_client_block(db_session=db_session, client_id=client_id)
    rtnval: Dict[str, Any] = {
        "run_id": run_id,
        "project_id": str(row.project_id),
        "pod_id": pod_id,
        "client_id": client_id,
        "job_id": job_id,
        "job_name": job_name,
        "job_type": str(row.job_type) if row.job_type is not None else "",
        "state": _enum_value_or_none(row.state),
        "terminal_outcome": _enum_value_or_none(row.terminal_outcome),
        "outcome_reason": outcome_reason,
        "assigned_client": assigned_client,
        "current_dispatch_attempt_id": current_attempt_id,
        "progress_summary": progress_summary,
        "result_manifest": result_manifest,
        "created_at": timings["created_at"],
        "dispatched_at": timings["dispatched_at"],
        "started_at": timings["started_at"],
        "completed_at": timings["completed_at"],
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


#: Most rows a CSV export carries; beyond it the file is cut and says so
#: (``X-Export-Truncated``).
CSV_EXPORT_MAX_ROWS = 5000

CSV_EXPORT_COLUMNS = (
    "run_id", "project_id", "job_name", "job_type", "state", "terminal_outcome",
    "created_at", "started_at", "completed_at", "duration_seconds", "pod_id",
)


def _duration_seconds(*, started: Optional[str], finished: Optional[str]) -> str:
    """
        Whole seconds between two ISO timestamps, or "" when either is missing.
    """
    if not started or not finished:
        return ""
    try:
        began = datetime.fromisoformat(started)
        ended = datetime.fromisoformat(finished)
    except ValueError:
        return ""
    return str(max(0, int((ended - began).total_seconds())))


def _runs_csv_response(*, db_session: Any, query: Any) -> Response:
    """
        The filtered runs as a CSV attachment, newest first, at most
        :data:`CSV_EXPORT_MAX_ROWS` rows (paging does not apply: an export is
        the whole filtered list).

        :param db_session: Active SQLAlchemy session.
        :param query: The run query with the request's filters applied.

        :returns: A CSV download.
    """
    from ccai.pychestrate.webservice.csv_export import csv_response, render_csv  # noqa: E402

    rows = (
        query.order_by(Run.entered_state_at.desc())
        .limit(CSV_EXPORT_MAX_ROWS + 1)
        .all()
    )
    truncated = len(rows) > CSV_EXPORT_MAX_ROWS
    records: List[Dict[str, Any]] = []
    for row in rows[:CSV_EXPORT_MAX_ROWS]:
        item = _run_to_dict(row=row, db_session=db_session)
        item["duration_seconds"] = _duration_seconds(started=item.get("started_at"), finished=item.get("completed_at"))
        records.append(item)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    return csv_response(
        filename="pychestrate-runs-{}.csv".format(stamp),
        body=render_csv(columns=CSV_EXPORT_COLUMNS, rows=records),
        truncated=truncated,
    )


def handle_list_runs(request: Request) -> Response:
    """
        ``GET /api/v1/runs`` -- list runs with optional filters.

        Query params: ``project_id``, ``pod_id``, ``state``,
        ``page``, ``per_page``, and ``format=csv`` to download the whole
        filtered list (at most 5000 rows) as a spreadsheet-safe CSV instead.

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

        if str(request.query_params.get("format", "") or "").lower() == "csv":
            rtnval_csv = _runs_csv_response(db_session=db_session, query=query)
            return rtnval_csv

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
            items.append(_run_to_dict(row=row, db_session=db_session))

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

        body = _run_to_dict(
            row=row,
            db_session=db_session,
            include_result_manifest=True,
        )
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

        dispatch_repo.mark_attempt_acked(
            db_session=db_session,
            attempt=attempt,
            acked_at=datetime.now(timezone.utc),
        )

        try:
            _advance_to_dispatched(
                db_session=db_session,
                run_id=run_id,
                actor="system:dispatch-ack",
                reason="dispatch-ack receipt recorded",
            )
        except Exception as xcpt:
            _LOGGER.warning(
                "pychestrate.runs.dispatch_ack.state_advance_error"
                " run_id=%s err=%s",
                run_id,
                xcpt,
            )

        # A pod that refuses a dispatch (the envelope failed verification,
        # it is shutting down) acks it with notes starting "REJECTED:". The
        # run will never progress, so end it here with the pod's words as
        # the reason instead of leaving it "dispatched" with no explanation.
        ack_notes = payload.get("notes", None)
        if isinstance(ack_notes, str) and ack_notes.strip().upper().startswith(DISPATCH_REJECTED_NOTE_PREFIX):
            try:
                _run_state_transition(
                    db_session=db_session,
                    run_id=run_id,
                    event=RunEvent.FAILURE_OBSERVED,
                    actor="system:dispatch-ack",
                    reason=ack_notes.strip(),
                )
            except Exception as xcpt:
                _LOGGER.warning(
                    "pychestrate.runs.dispatch_ack.rejection_not_applied"
                    " run_id=%s err=%s",
                    run_id,
                    xcpt,
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


#: ProgressFrame ``frame_kind`` discriminator values. ``test``
#: keeps the legacy ``summary`` / ``records`` test-shaped body;
#: ``build`` / ``provision`` carry a generalized ``frame`` object
#: (or a ``frames`` array). A body with no ``frame_kind`` defaults
#: to ``test`` so an unmodified testbase client posts unchanged.
PROGRESS_FRAME_KIND_TEST = "test"
PROGRESS_FRAME_KIND_BUILD = "build"
PROGRESS_FRAME_KIND_PROVISION = "provision"
PROGRESS_FRAME_KIND_RPA = "rpa"
SUPPORTED_PROGRESS_FRAME_KINDS = (
    PROGRESS_FRAME_KIND_TEST,
    PROGRESS_FRAME_KIND_BUILD,
    PROGRESS_FRAME_KIND_PROVISION,
    PROGRESS_FRAME_KIND_RPA,
)


def _handle_build_provision_progress(
        *,
        request: Request,
        db_session: Any,
        run_id: str,
        frame_kind: str,
        payload: Dict[str, Any]
    ) -> int:
    """
        Ingest the ``build`` / ``provision`` generalized progress
        frames carried by a ``frame_kind != test`` ProgressFrame.

        The body carries either a single ``frame`` object or a
        ``frames`` array; each frame must carry ``client_id`` and
        an integer ``frame_index``. Frames route to
        :func:`progress_service.ingest_frame` which persists them
        without testbase parsing and emits a ``FRAME_LANDED`` bus
        event the live hub forwards onto the run's SSE stream.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the path.
        :param frame_kind: ``"build"`` or ``"provision"``.
        :param payload: The decoded ProgressFrame body.

        :returns: Count of frames accepted.
    """
    frames_payload = payload.get("frames", None)
    single_frame = payload.get("frame", None)
    if frames_payload is None and single_frame is None:
        _abort_problem(
            request=request,
            status=400,
            detail=(
                "ProgressFrame frame_kind='{}' must include 'frame' or"
                " 'frames'.".format(frame_kind)
            ),
        )
    if frames_payload is not None and isinstance(frames_payload, list) is False:
        _abort_problem(
            request=request,
            status=400,
            detail="ProgressFrame 'frames' must be an array.",
        )

    frame_list: List[Any] = []
    if single_frame is not None:
        frame_list.append(single_frame)
    if frames_payload is not None:
        frame_list.extend(frames_payload)

    frames_accepted = 0
    for index, frame in enumerate(frame_list):
        if isinstance(frame, dict) is False:
            _abort_problem(
                request=request,
                status=400,
                detail="ProgressFrame frame #{} must be an object.".format(index),
            )
        frame_client_id = frame.get("client_id", "")
        frame_index = frame.get("frame_index", None)
        if isinstance(frame_client_id, str) is False or len(frame_client_id) == 0:
            _abort_problem(
                request=request,
                status=400,
                detail="ProgressFrame frame #{} missing 'client_id'.".format(index),
            )
        if isinstance(frame_index, int) is False:
            _abort_problem(
                request=request,
                status=400,
                detail="ProgressFrame frame #{} 'frame_index' must be int.".format(index),
            )

        progress_service.ingest_frame(
            db_session=db_session,
            run_id=run_id,
            authenticated_client_id=frame_client_id,
            frame_kind=frame_kind,
            frame_index=frame_index,
            payload=frame,
        )
        frames_accepted += 1

    rtnval = frames_accepted
    return rtnval


def handle_post_progress(request: Request) -> Response:
    """
        ``POST /api/v1/runs/{run_id}/progress`` -- live progress
        frame from the pod client agent.

        The body carries a ``frame_kind`` discriminator:

        * ``test`` (the default when ``frame_kind`` is absent) --
          the test-shaped body with a ``summary`` roll-up and / or
          a ``records`` array of per-test records, parsed by the
          testbase progress parser exactly as PR p19c established.
        * ``build`` / ``provision`` -- a generalized progress frame
          (or ``frames`` array) carrying phase / status / log-line
          excerpts; persisted by the progress ingest service
          without testbase parsing and streamed onto the run's SSE
          events route as a ``progress`` RunEvent.

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

        frame_kind = payload.get("frame_kind", PROGRESS_FRAME_KIND_TEST)
        if isinstance(frame_kind, str) is False or len(frame_kind) == 0:
            frame_kind = PROGRESS_FRAME_KIND_TEST
        if frame_kind not in SUPPORTED_PROGRESS_FRAME_KINDS:
            _abort_problem(
                request=request,
                status=400,
                detail="ProgressFrame 'frame_kind' must be one of: {}.".format(
                    ", ".join(SUPPORTED_PROGRESS_FRAME_KINDS),
                ),
                extensions={"frame_kind": frame_kind},
            )

        if frame_kind != PROGRESS_FRAME_KIND_TEST:
            try:
                frames_accepted = _handle_build_provision_progress(
                    request=request,
                    db_session=db_session,
                    run_id=run_id,
                    frame_kind=frame_kind,
                    payload=payload,
                )
            except ProgressUnknownRunError as xcpt:
                _abort_problem(
                    request=request,
                    status=404,
                    detail=str(xcpt),
                    extensions={"run_id": run_id},
                )
                frames_accepted = 0  # unreachable
            except ProgressClientMismatchError as xcpt:
                _abort_problem(
                    request=request,
                    status=403,
                    detail=str(xcpt),
                    extensions={"run_id": run_id},
                )
                frames_accepted = 0  # unreachable
            except ProgressFormatError as xcpt:
                _abort_problem(
                    request=request,
                    status=400,
                    detail=str(xcpt),
                    extensions={"run_id": run_id},
                )
                frames_accepted = 0  # unreachable

            try:
                _note_progress(
                    db_session=db_session,
                    run_id=run_id,
                    actor="system:progress-ingest",
                    reason="progress frame: kind={}".format(frame_kind),
                )
            except Exception as xcpt:
                _LOGGER.warning(
                    "pychestrate.runs.progress.state_advance_error"
                    " run_id=%s err=%s",
                    run_id,
                    xcpt,
                )

            _LOGGER.info(
                "pychestrate.runs.progress run_id=%s client_cn=%s"
                " frame_kind=%s frames=%d",
                run_id,
                client_cn,
                frame_kind,
                frames_accepted,
            )

            body = {
                "run_id": run_id,
                "frame_kind": frame_kind,
                "frames_accepted": frames_accepted,
            }
            rtnval: Response = JSONResponse(content=body, status_code=202)
            return rtnval

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
                    # A record inherits the frame summary's format_tag; the
                    # client sends it once per frame. The old fallback,
                    # "testbase", names no registered parser, so every
                    # record frame was refused with 400.
                    record_format_tag = record.get("format_tag", None)
                    if isinstance(record_format_tag, str) is False or len(record_format_tag) == 0:
                        record_format_tag = DEFAULT_PROGRESS_RECORD_FORMAT_TAG
                        if isinstance(summary_payload, dict):
                            summary_tag = summary_payload.get("format_tag", None)
                            if isinstance(summary_tag, str) and len(summary_tag) > 0:
                                record_format_tag = summary_tag
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

        try:
            _note_progress(
                db_session=db_session,
                run_id=run_id,
                actor="system:progress-ingest",
                reason="progress frame: kind=test",
            )
        except Exception as xcpt:
            _LOGGER.warning(
                "pychestrate.runs.progress.state_advance_error"
                " run_id=%s err=%s",
                run_id,
                xcpt,
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
            "frame_kind": PROGRESS_FRAME_KIND_TEST,
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


def _handle_build_provision_completion(
        *,
        request: Request,
        db_session: Any,
        run_id: str,
        format_tag: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
    """
        Job-kind-aware completion ingest for a ``build`` /
        ``provision`` ``ResultManifest``.

        Build and provision runs flow a ``run_id`` through the same
        ``results/complete`` surface as test runs, but their
        uploaded trees are not testbase trees -- they carry raw
        artifact files only. This helper takes the direct,
        non-testbase completion path
        (:mod:`ingest.result.completion`): it advances the
        :class:`BuildRun` / :class:`InfraRun` to its terminal
        state, records the uploaded artifacts, and drives the
        run-state machine terminal. The testbase result scanner is
        not invoked.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the path.
        :param format_tag: ``"build"`` or ``"provision"``.
        :param payload: The decoded ``ResultManifest`` dict.

        :returns: The completion summary dict the handler echoes in
                  its 202 body.
    """
    try:
        if format_tag == result_completion.BUILD_FORMAT_TAG:
            outcome = result_completion.complete_build_run(
                db_session=db_session,
                run_id=run_id,
                manifest=payload,
            )
        elif format_tag == result_completion.RPA_FORMAT_TAG:
            outcome = result_completion.complete_rpa_run(
                db_session=db_session,
                run_id=run_id,
                manifest=payload,
            )
        else:
            outcome = result_completion.complete_provision_run(
                db_session=db_session,
                run_id=run_id,
                manifest=payload,
            )
    except BuildRunNotFoundError as xcpt:
        _abort_problem(
            request=request,
            status=404,
            detail=str(xcpt),
            extensions={"run_id": run_id, "format_tag": format_tag},
        )
        outcome = None  # unreachable -- _abort_problem raises.
    except RpaJobNotFoundError as xcpt:
        _abort_problem(
            request=request,
            status=404,
            detail=str(xcpt),
            extensions={"run_id": run_id, "format_tag": format_tag},
        )
        outcome = None  # unreachable
    except InfraRunNotFoundError as xcpt:
        _abort_problem(
            request=request,
            status=404,
            detail=str(xcpt),
            extensions={"run_id": run_id, "format_tag": format_tag},
        )
        outcome = None  # unreachable

    rtnval: Dict[str, Any] = {
        "job_kind": outcome.job_kind,
        "domain_state": outcome.domain_state,
        "run_state": outcome.run_state,
        "artifacts_recorded": outcome.artifacts_recorded,
    }
    if outcome.manifest_id is not None:
        rtnval["manifest_id"] = outcome.manifest_id
    return rtnval


#: Testbase result-tree well-known artifact paths and their
#: OpenAPI ``ResultManifest`` defaults. Applied when a testbase
#: manifest omits the explicit path fields so the UI's artifact
#: links always resolve.
_TESTBASE_ARTIFACT_PATH_DEFAULTS: Dict[str, str] = {
    "summary_artifact_path": "testrun_summary.json",
    "results_stream_artifact_path": "testrun_results_stream.jsos",
    "results_artifact_path": "testrun_results.json",
    "html_summary_artifact_path": "testsummary.html",
}


def _build_result_manifest_block(
        *,
        run_id: str,
        format_tag: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
    """
        Build the ``manifest`` block for the ``result_manifest``
        RunEvent from a posted ``ResultManifest`` body.

        The block echoes the manifest's identity fields, resolves
        the well-known testbase artifact paths (applying the
        OpenAPI defaults when the client omitted them), and lifts
        the walked artifact-file index (``extras.files``) to a
        top-level ``files`` array + ``artifact_count`` so the UI
        can render the artifacts pane without digging into
        ``extras``.

        :param run_id: Run UUID from the path.
        :param format_tag: The manifest's ``format_tag``.
        :param payload: The decoded ``ResultManifest`` dict.

        :returns: JSON-serializable manifest block.
    """
    files = result_completion.artifact_files_from_manifest(manifest=payload)

    failure_classification = (
        result_classification.failure_classification_from_manifest(
            manifest=payload,
        )
    )

    rtnval: Dict[str, Any] = {
        "run_id": run_id,
        "client_id": payload.get("client_id", None),
        "format_tag": format_tag,
        "backend_key_prefix": payload.get("backend_key_prefix", None),
        "completed_at": payload.get("completed_at", None),
        "terminal_outcome": payload.get("terminal_outcome", None),
        "failure_classification": failure_classification,
        "artifact_count": len(files),
        "files": files,
    }

    for path_field, default_path in _TESTBASE_ARTIFACT_PATH_DEFAULTS.items():
        candidate = payload.get(path_field, None)
        if isinstance(candidate, str) and len(candidate) > 0:
            rtnval[path_field] = candidate
        elif format_tag == "testbase":
            rtnval[path_field] = default_path

    counter_fields = (
        "tests_passed",
        "tests_failed",
        "tests_skipped",
        "tests_errored",
    )
    for counter_field in counter_fields:
        candidate = payload.get(counter_field, None)
        if isinstance(candidate, int):
            rtnval[counter_field] = candidate

    notes = payload.get("notes", None)
    if isinstance(notes, str) and len(notes) > 0:
        rtnval["notes"] = notes

    return rtnval


def _emit_result_manifest_event(
        *,
        db_session: Any,
        run_id: str,
        project_id: str,
        format_tag: str,
        payload: Dict[str, Any]
    ) -> None:
    """
        Publish the ``result_manifest`` live event for a completed
        result upload.

        Writes a durable ``runs_run_event_outbox`` row and buffers
        the in-process bus event
        (:attr:`ResultEventTopics.MANIFEST_LANDED`) for after-commit
        delivery — the :class:`LiveRunBusBridge` forwards it onto
        the run's SSE relay as a ``result_manifest`` RunEvent so
        the run-detail artifacts pane renders.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the path.
        :param project_id: Owning project UUID.
        :param format_tag: The manifest's ``format_tag``.
        :param payload: The decoded ``ResultManifest`` dict.

        :returns: None.
    """
    now = datetime.now(timezone.utc)
    manifest_block = _build_result_manifest_block(
        run_id=run_id,
        format_tag=format_tag,
        payload=payload,
    )
    event_payload: Dict[str, Any] = {
        "run_id": run_id,
        "project_id": project_id,
        "terminal_outcome": manifest_block["terminal_outcome"],
        "received_at": now.isoformat(),
        "manifest": manifest_block,
    }
    run_repo.append_outbox_row(
        db_session=db_session,
        run_id=run_id,
        topic=ResultEventTopics.MANIFEST_LANDED,
        payload=event_payload,
        created_at=now,
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ResultEventTopics.MANIFEST_LANDED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return


def _advance_run_state_from_outcome(
        *,
        db_session: Any,
        run_id: str,
        terminal_outcome: str,
        reason: str
    ) -> None:
    """
        Drive the run-state row terminal in the direction the
        client's reported ``terminal_outcome`` actually points.

        Three outcomes are distinguished rather than two.
        ``success`` completes the run; ``cancelled`` cancels it; and
        everything else fails it. Collapsing ``cancelled`` into the
        failure branch -- which is what a plain
        ``succeeded = outcome == "success"`` boolean does -- would
        stamp ``TerminalOutcome.FAILURE`` on a run an operator
        deliberately stopped, making a cancel indistinguishable from
        a broken job in every downstream metric.

        A state-advance failure is logged, not raised: the manifest
        was ingested and the client is owed its 202 regardless of
        whether the bookkeeping row could be walked forward.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the path.
        :param terminal_outcome: The manifest's ``terminal_outcome``.
        :param reason: Reason written to the state-audit row.

        :returns: None.
    """
    actor = "system:result-ingest"

    try:
        if terminal_outcome == TERMINAL_OUTCOME_CANCELLED:
            _advance_to_cancelled(
                db_session=db_session,
                run_id=run_id,
                actor=actor,
                reason=reason,
            )
        else:
            succeeded = (
                terminal_outcome == result_completion.TERMINAL_OUTCOME_SUCCESS
            )
            _advance_to_terminal(
                db_session=db_session,
                run_id=run_id,
                succeeded=succeeded,
                actor=actor,
                reason=reason,
            )
    except Exception as xcpt:
        _LOGGER.warning(
            "pychestrate.runs.results_complete.state_advance_error"
            " run_id=%s err=%s",
            run_id,
            xcpt,
        )
    return


def _close_cancel_request_on_cancelled_result(
        *,
        db_session: Any,
        run_id: str,
        client_id: str,
        terminal_outcome: str
    ) -> None:
    """
        Close the open cancel request when the pod reports that it
        actually stopped the run.

        The cancel queue is drained by the client heartbeat and rows
        stay open so an undelivered cancel is retried. A run
        reporting ``cancelled`` is the pod confirming it received
        the signal and acted on it, which is the only acknowledgement
        worth recording -- and the thing that stops the retry.

        Failures are logged, never raised: the completion itself has
        already been ingested.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the path.
        :param client_id: Reporting client's UUID.
        :param terminal_outcome: The manifest's ``terminal_outcome``.

        :returns: None.
    """
    if terminal_outcome != TERMINAL_OUTCOME_CANCELLED:
        return

    try:
        acknowledge_client_cancellation(
            db_session=db_session,
            run_id=run_id,
            client_id=client_id,
        )
    except Exception as xcpt:
        _LOGGER.warning(
            "pychestrate.runs.results_complete.cancel_ack_error"
            " run_id=%s client_id=%s err=%s",
            run_id,
            client_id,
            xcpt,
        )
    return


def handle_post_results_complete(request: Request) -> Response:
    """
        ``POST /api/v1/runs/{run_id}/results/complete`` -- pod
        client agent signals that a result tree is fully uploaded.

        The handler is job-kind-aware. The posted ``ResultManifest``
        carries a ``format_tag``:

        * ``testbase`` -- the result tree is parsed + persisted by
          the testbase result scanner, exactly as in PR p19c.
        * ``build`` / ``provision`` -- the run is a build /
          provisioning run; the manifest is routed to the direct
          completion path (:mod:`ingest.result.completion`), which
          advances the :class:`BuildRun` / :class:`InfraRun` to a
          terminal state, records the uploaded artifacts, and
          drives the run-state machine terminal. The testbase
          scanner is not invoked for these job kinds.

        For testbase the scan is triggered synchronously inside the
        handler; later milestones move it to the scheduler. The
        handler is tolerant of scanner errors: a missing tree
        returns 409, a parse failure is deferred (still 202).

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
        completion_summary: Optional[Dict[str, Any]] = None

        is_build_or_provision = format_tag in (
            result_completion.BUILD_FORMAT_TAG,
            result_completion.PROVISION_FORMAT_TAG,
            result_completion.RPA_FORMAT_TAG,
        )

        if is_build_or_provision is True:
            # Build / provision runs take the direct completion
            # path -- the uploaded tree is not a testbase tree, so
            # the testbase result scanner is bypassed entirely.
            completion_summary = _handle_build_provision_completion(
                request=request,
                db_session=db_session,
                run_id=run_id,
                format_tag=format_tag,
                payload=payload,
            )
            scan_status = "completed"
        else:
            # testbase result tree -- parse + persist via the
            # result scanner exactly as PR p19c established. The
            # manifest's prefix is relative to the artifact root
            # (never the process working directory, LD-14); a
            # client-supplied absolute or escaping prefix is
            # refused rather than read.
            try:
                tree_path = resolve_result_tree_path(
                    backend_key_prefix=backend_key_prefix,
                    allow_absolute=False,
                )
            except ArtifactPathInvalidError as xcpt:
                _abort_problem(
                    request=request,
                    status=400,
                    detail=str(xcpt),
                    extensions={
                        "run_id": run_id,
                        "backend_key_prefix": backend_key_prefix,
                    },
                )
                tree_path = ""  # unreachable -- _abort_problem raises.
            try:
                outcome = result_scanner.scan_once(
                    db_session=db_session,
                    run_id=run_id,
                    tree_path=tree_path,
                )
                scan_status = "scanned"
                scan_detail = getattr(outcome, "status", None)
            except ResultTreeNotFoundError as xcpt:
                if terminal_outcome == TERMINAL_OUTCOME_CANCELLED:
                    # A job stopped by a cancel may have written nothing;
                    # the cancelled outcome is what the run needs, and
                    # refusing it left the run in CANCEL_REQUESTED with
                    # the cancel re-sent on every heartbeat.
                    scan_status = "not_found"
                    scan_detail = "no result tree for a cancelled run"
                    _LOGGER.info(
                        "pychestrate.runs.results_complete.cancelled_without_tree"
                        " run_id=%s", run_id,
                    )
                else:
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
                # Parse failures shouldn't deny the manifest; record
                # the failure and let the operator inspect via the
                # run-event SSE stream + audit log. Per the OpenAPI
                # description "errors in downstream parsing are
                # surfaced via the RunEvent SSE stream" -- we still
                # return 202 here.
                _LOGGER.warning(
                    "pychestrate.runs.results_complete.scan_error"
                    " run_id=%s err=%s",
                    run_id,
                    xcpt,
                )
                scan_status = "scan_deferred"
                scan_detail = str(xcpt)

            # Drive the run-state machine to a terminal state.
            # Success is determined from the manifest's
            # ``terminal_outcome`` field, mirroring how
            # ingest.result.completion decides success for build /
            # provision runs (terminal_outcome == "success" => True).
            _advance_run_state_from_outcome(
                db_session=db_session,
                run_id=run_id,
                terminal_outcome=terminal_outcome,
                reason="testbase result manifest: outcome={}".format(terminal_outcome),
            )

        # A run reporting ``cancelled`` is the pod confirming it
        # received the operator's cancel and stopped the job, so the
        # open cancel request can be closed and the heartbeat drain
        # can stop re-delivering it.
        _close_cancel_request_on_cancelled_result(
            db_session=db_session,
            run_id=run_id,
            client_id=client_id_field,
            terminal_outcome=terminal_outcome,
        )

        # Publish the result_manifest live event so a subscribed
        # run-detail view renders the artifacts pane. Mirrors the
        # state-advance calls above: a publish failure is logged
        # but never denies the client its 202 — the manifest was
        # ingested.
        try:
            _emit_result_manifest_event(
                db_session=db_session,
                run_id=run_id,
                project_id=str(getattr(run_row, "project_id", "")),
                format_tag=format_tag,
                payload=payload,
            )
        except Exception as xcpt:
            _LOGGER.warning(
                "pychestrate.runs.results_complete.manifest_event_error"
                " run_id=%s err=%s",
                run_id,
                xcpt,
            )

        _LOGGER.info(
            "pychestrate.runs.results_complete run_id=%s client_cn=%s"
            " format_tag=%s status=%s",
            run_id,
            client_cn,
            format_tag,
            scan_status,
        )

        body: Dict[str, Any] = {
            "run_id": run_id,
            "status": scan_status,
            "terminal_outcome": terminal_outcome,
        }
        if scan_detail is not None:
            body["scan_detail"] = scan_detail
        if completion_summary is not None:
            body.update(completion_summary)
        rtnval: Response = JSONResponse(content=body, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/runs/{run_id}/cancel
# ---------------------------------------------------------------------------


def _require_runs_cancel_permission(*, request: Request, db_session: Any, project_id: str) -> None:
    """
        Require the calling principal to hold the cancel permission in
        the run's project -- ``project:<project_id>:runs.cancel``, granted
        to the ``operator`` and ``admin`` project roles by
        :mod:`security.rbac.extensions.project_roles` -- or the system-wide
        ``system:runs.cancel`` (granted to ``system-admin``).

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: The run's project UUID.

        :returns: None.
    """
    principal = _resolve_auth_principal(request=request)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )

    # Either the project grant or the system-wide one (system-admin), so
    # an administrator can cancel from the global runs page.
    permission_key = runs_cancel_permission_key(project_id=project_id)
    now = datetime.now(timezone.utc)
    allowed = False
    for candidate_key in (permission_key, RUNS_CANCEL_SYSTEM_PERMISSION_KEY):
        decision = rbac_evaluator.check_permission(
            db_session=db_session,
            principal=principal,
            permission_key=candidate_key,
            now=now,
        )
        if decision.allowed is True:
            allowed = True
            break
    if allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {} or {}".format(
                permission_key, RUNS_CANCEL_SYSTEM_PERMISSION_KEY),
            extensions={"required_permission": permission_key,
                        "alternative_permission": RUNS_CANCEL_SYSTEM_PERMISSION_KEY},
        )
    return


def handle_cancel_run(request: Request) -> Response:
    """
        ``POST /api/v1/runs/{run_id}/cancel`` -- request cancellation
        of an in-flight run.

        Requires the ``project:runs.cancel`` permission. The optional
        ``reason`` field in the JSON body is recorded on the run and
        included in the state-audit log for operator triage.

        Idempotent for CANCEL_REQUESTED: the transition from any
        cancel-family state that does NOT raise
        :class:`IllegalTransitionError` or
        :class:`TerminalStateError` proceeds normally; a run already
        in a terminal state returns a 409 problem response so the
        caller knows no cancel was needed.

        :param request: Incoming webworks request.

        :returns: 200 JSON with the run snapshot on success;
                  409 problem+json when the run is terminal;
                  404 problem+json when the run does not exist.
    """
    run_id = request.path_params.get("run_id", "")
    try:
        db_session = _require_session(request=request)

        # The permission is project-scoped, so the run (and its project)
        # is loaded first; an unknown run is still a 404.
        run_row = _require_run_exists(
            request=request, db_session=db_session, run_id=run_id,
        )
        _require_runs_cancel_permission(
            request=request, db_session=db_session,
            project_id=str(run_row.project_id),
        )

        payload = {}
        try:
            candidate = request.json()
            if isinstance(candidate, dict):
                payload = candidate
        except Exception:
            pass

        reason = payload.get("reason", None)
        if not isinstance(reason, str) or len(reason) == 0:
            reason = "cancel requested via REST"

        principal = _resolve_auth_principal(request=request)
        actor_id = "user:unknown"
        if principal is not None:
            user_id = getattr(principal, "user_id", None)
            if user_id is not None:
                actor_id = "user:{}".format(str(user_id))

        try:
            snapshot = _request_cancel(
                db_session=db_session,
                run_id=run_id,
                actor=actor_id,
                reason=reason,
            )
        except TerminalStateError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={
                    "run_id": run_id,
                    "reason": "run is already in a terminal state",
                },
            )
            snapshot = None  # unreachable — _abort_problem raises.
        except IllegalTransitionError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={
                    "run_id": run_id,
                    "reason": "cancel not permitted from current state",
                },
            )
            snapshot = None  # unreachable.
        except RunNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
            snapshot = None  # unreachable.

        cancel_request_id = queue_client_cancel(
            db_session=db_session,
            run_id=run_id,
            reason=reason,
            actor_id=actor_id,
        )

        body = {
            "run_id": snapshot.run_id,
            "state": snapshot.state.value,
            "prior_state": snapshot.prior_state.value if snapshot.prior_state is not None else None,
            "entered_state_at": snapshot.entered_state_at.isoformat(),
            "terminal_outcome": snapshot.terminal_outcome,
            "cancel_request_id": cancel_request_id,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
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
    app.attach_route(
        base + "/{run_id}/cancel", methods=["POST"],
    )(handle_cancel_run)
    return


__all__ = [
    "RUNS_PATH",
    "MTLS_CLIENT_CN_ENVIRON_KEY",
    "RUNS_READ_PERMISSION_KEY",
    "RUNS_CANCEL_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "SUPPORTED_PROGRESS_FRAME_KINDS",
    "register_runs_routes",
    "handle_list_runs",
    "handle_read_run",
    "handle_dispatch_ack",
    "handle_post_progress",
    "handle_post_results_complete",
    "handle_cancel_run",
]
