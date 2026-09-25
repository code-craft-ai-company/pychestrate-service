"""
.. module:: orchestration.test.restapi.v1.test_runs_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST route for POST /api/v1/projects/{id}/test-runs.

.. moduleauthor:: Code Craft AI LLC

Implements the planned ``test_runs`` operation from
``specs/openapi/pychestrate.yaml``:

* ``POST /api/v1/projects/{project_id}/test-runs``

Validates the requesting principal holds ``system:test_runs.create``,
resolves the catalog entry (either by id or by ``importer_tag`` +
``entry_key``), discovers the target pod's active client
registration, and delegates to
:class:`webservice.orchestration.test.orchestrator.TestOrchestrator`.

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.errors.exceptions import SemanticError

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.jobs.dispatch.errors import (
    DispatchError,
    DispatchNoCandidatesError,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.orchestration.test import orchestrator as orchestrator_module
from ccai.pychestrate.webservice.orchestration.test.catalog import repository as catalog_repo
from ccai.pychestrate.webservice.orchestration.test.errors import (
    CapabilityMismatchError,
    DispatchFailedError,
    TestOrchestrationError,
)
from ccai.pychestrate.webservice.orchestration.test.catalog.errors import (
    CatalogEntryNotFoundError,
)
from ccai.pychestrate.webservice.pods.models import (
    PodDefinition,
    PodRegistration,
    RegistrationState,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


TEST_RUNS_PATH_SUFFIX = "/test-runs"
PROJECTS_PATH_PREFIX = "/projects"

TEST_RUNS_CREATE_PERMISSION_KEY = "system:test_runs.create"

DEFAULT_SOFT_DEADLINE_SECONDS = 1800
DEFAULT_HARD_DEADLINE_SECONDS = 3600

_LOGGER = logging.getLogger("pychestrate.test_runs.routes")


# ---------------------------------------------------------------------------
# Orchestrator seam (test-injectable)
# ---------------------------------------------------------------------------


#: Module-level seam holding the active :class:`TestOrchestrator`
#: instance. The service bootstrap rebinds this on startup; tests
#: patch it via :func:`ccai.testbase.mocking.create_module_patch`.
ACTIVE_TEST_ORCHESTRATOR: Optional[Any] = None


def set_active_test_orchestrator(*, orchestrator: Any) -> None:
    """
        Register the process-wide :class:`TestOrchestrator`. The
        REST handler reads this seam on every request so the
        bootstrap can swap implementations without re-importing the
        route module.

        :param orchestrator: TestOrchestrator instance.

        :returns: None.
    """
    global ACTIVE_TEST_ORCHESTRATOR
    ACTIVE_TEST_ORCHESTRATOR = orchestrator
    return


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception. Carries a webworks problem
        response so nested helpers can signal an error condition
        and the top-level handler converts it at the boundary.
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
        middleware, or ``None`` when anonymous.

        :param request: Incoming webworks request.

        :returns: AuthPrincipal or None.
    """
    rtnval = getattr(request, "auth_principal", None)
    return rtnval


def _require_test_runs_create_permission(*, request: Request, db_session: Any) -> Any:
    """
        Require the calling principal to hold
        ``system:test_runs.create``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.

        :returns: The :class:`AuthPrincipal` (so callers can pull
                  the user_id off it without a second lookup).
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
        permission_key=TEST_RUNS_CREATE_PERMISSION_KEY,
        now=now,
    )
    if decision.allowed is False:
        _abort_problem(
            request=request,
            status=403,
            detail="Permission denied: {}".format(TEST_RUNS_CREATE_PERMISSION_KEY),
            extensions={
                "required_permission": TEST_RUNS_CREATE_PERMISSION_KEY,
            },
        )
    rtnval = principal
    return rtnval


def _decode_json_object_or_abort(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, aborting 422 on
        missing / malformed / non-dict bodies.

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


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------


def _require_project_exists(*, request: Request, db_session: Any, project_id: str) -> Any:
    """
        Look up the project, aborting 404 when not found.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID from the path.

        :returns: Project ORM row.
    """
    row = projects_repo.get_project_by_id(
        db_session=db_session,
        project_id=project_id,
    )
    if row is None:
        _abort_problem(
            request=request,
            status=404,
            detail="Project not found.",
            extensions={"project_id": project_id},
        )
    rtnval = row
    return rtnval


def _resolve_catalog_entry(
        *,
        request: Request,
        db_session: Any,
        project_id: str,
        body: Dict[str, Any]
    ) -> Any:
    """
        Resolve the catalog entry row from either ``catalog_entry_id``
        or the ``(importer_tag, entry_key)`` natural-key pair.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: Project UUID from the path.
        :param body: Decoded JSON body.

        :returns: TestCatalogEntry ORM row.
    """
    catalog_entry_id = body.get("catalog_entry_id", None)
    importer_tag = body.get("importer_tag", None)
    entry_key = body.get("entry_key", None)

    row: Optional[Any] = None
    if isinstance(catalog_entry_id, str) and len(catalog_entry_id) > 0:
        row = catalog_repo.find_by_id(
            db_session=db_session,
            entry_id=catalog_entry_id,
        )
        if row is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Catalog entry not found.",
                extensions={"catalog_entry_id": catalog_entry_id},
            )
    elif isinstance(importer_tag, str) and len(importer_tag) > 0 \
            and isinstance(entry_key, str) and len(entry_key) > 0:
        row = catalog_repo.find_entry(
            db_session=db_session,
            project_id=project_id,
            importer_tag=importer_tag,
            entry_key=entry_key,
        )
        if row is None:
            _abort_problem(
                request=request,
                status=404,
                detail="Catalog entry not found.",
                extensions={
                    "importer_tag": importer_tag,
                    "entry_key": entry_key,
                },
            )
    else:
        _abort_problem(
            request=request,
            status=422,
            detail=(
                "Body must include either 'catalog_entry_id' or "
                "('importer_tag' AND 'entry_key')."
            ),
        )

    if str(row.project_id) != str(project_id):
        _abort_problem(
            request=request,
            status=404,
            detail="Catalog entry does not belong to this project.",
            extensions={
                "project_id": project_id,
                "entry_id": str(row.entry_id),
            },
        )
    rtnval = row
    return rtnval


def _candidates_for_pod(*, db_session: Any, pod_id: str) -> List[DispatchCandidate]:
    """
        Build a :class:`DispatchCandidate` list from the REGISTERED
        client registrations for a single pod.

        :param db_session: Active SQLAlchemy session.
        :param pod_id: Target pod UUID.

        :returns: List of dispatch candidates (may be empty).
    """
    registrations = (
        db_session.query(PodRegistration)
        .filter(PodRegistration.pod_id == pod_id)
        .filter(PodRegistration.state == RegistrationState.REGISTERED)
        .all()
    )

    candidates: List[DispatchCandidate] = []
    for reg in registrations:
        client_id = reg.client_id
        if client_id is None:
            continue
        candidates.append(
            DispatchCandidate(
                client_id=str(client_id),
                pod_id=str(pod_id),
                capability_tags=tuple(),
                inflight_dispatch_count=0,
                last_dispatched_at_iso="",
            )
        )
    rtnval = candidates
    return rtnval


def _build_pod_candidates(
        *,
        request: Request,
        db_session: Any,
        project_id: str,
        pod_id: str
    ) -> List[DispatchCandidate]:
    """
        Resolve the active client registrations for ``pod_id`` and
        build a :class:`DispatchCandidate` list. Aborts 404 when the
        pod is unknown.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.
        :param pod_id: Target pod UUID from the body.

        :returns: List of dispatch candidates (may be empty when no
                  active registration is present).
    """
    pod_row = (
        db_session.query(PodDefinition)
        .filter(PodDefinition.pod_id == pod_id)
        .first()
    )
    if pod_row is None:
        _abort_problem(
            request=request,
            status=404,
            detail="Pod not found.",
            extensions={"pod_id": pod_id},
        )
    if str(pod_row.project_id) != str(project_id):
        _abort_problem(
            request=request,
            status=404,
            detail="Pod does not belong to this project.",
            extensions={
                "pod_id": pod_id,
                "project_id": project_id,
            },
        )

    rtnval = _candidates_for_pod(db_session=db_session, pod_id=pod_id)
    return rtnval


def _build_eligible_pod_candidates(
        *,
        request: Request,
        db_session: Any,
        project_id: str
    ) -> List[DispatchCandidate]:
    """
        Enumerate every pod enrolled in the project that carries at
        least one REGISTERED client registration and build the
        combined :class:`DispatchCandidate` list. The orchestrator
        then narrows this set down by capability match.

        Aborts 409 with an actionable message when the project has
        no enrolled pod with an active client registration.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.

        :returns: Non-empty list of dispatch candidates.
    """
    pod_rows = (
        db_session.query(PodDefinition)
        .filter(PodDefinition.project_id == project_id)
        .all()
    )

    candidates: List[DispatchCandidate] = []
    for pod_row in pod_rows:
        pod_id = str(pod_row.pod_id)
        pod_candidates = _candidates_for_pod(db_session=db_session, pod_id=pod_id)
        for candidate in pod_candidates:
            candidates.append(candidate)

    if len(candidates) == 0:
        _abort_problem(
            request=request,
            status=409,
            detail=(
                "No enrolled pod matches the job's capability "
                "requirements -- enroll a client/pod first."
            ),
            extensions={
                "project_id": project_id,
                "reason": "no_eligible_pod",
            },
        )

    rtnval = candidates
    return rtnval


# ---------------------------------------------------------------------------
# Body parsing
# ---------------------------------------------------------------------------


def _parse_positive_int_field(
        *,
        request: Request,
        body: Dict[str, Any],
        name: str,
        default: int
    ) -> int:
    """
        Coerce an optional positive-integer body field.

        :param request: Incoming webworks request.
        :param body: Decoded JSON body.
        :param name: Field name.
        :param default: Fallback when missing.

        :returns: Coerced integer.
    """
    raw = body.get(name, None)
    if raw is None:
        rtnval = default
        return rtnval
    if isinstance(raw, bool) is True:
        # ``bool`` is a subclass of ``int`` in Python; explicitly
        # reject it so ``True`` doesn't slip through as 1.
        _abort_problem(
            request=request,
            status=422,
            detail="Field '{}' must be a positive integer.".format(name),
        )
    if isinstance(raw, int) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field '{}' must be a positive integer.".format(name),
        )
    if raw < 1:
        _abort_problem(
            request=request,
            status=422,
            detail="Field '{}' must be >= 1.".format(name),
        )
    rtnval = int(raw)
    return rtnval


# ---------------------------------------------------------------------------
# Serializer (OpenAPI Run schema -- subset matching runs_routes._run_to_dict)
# ---------------------------------------------------------------------------


def _trigger_outcome_to_run_dict(
        *,
        outcome: Any,
        project_id: str,
        pod_id: Optional[str],
        catalog_entry: Any,
        triggered_at: datetime
    ) -> Dict[str, Any]:
    """
        Serialize a :class:`TriggerRunOutcome` plus its surrounding
        context to the OpenAPI ``Run`` schema.

        The fields not directly present on the outcome (labels,
        completed_at, job_name) are emitted as ``None`` / ``{}`` so
        the response matches the OpenAPI ``Run`` shape; subsequent
        PRs will fill them in once the orchestrator returns richer
        state.

        :param outcome: TriggerRunOutcome from the orchestrator.
        :param project_id: Owning project UUID.
        :param pod_id: Target pod UUID.
        :param catalog_entry: Resolved catalog entry row.
        :param triggered_at: When the request was accepted.

        :returns: JSON-friendly dict.
    """
    dispatch = getattr(outcome, "dispatch", None)
    attempt_id = None
    if dispatch is not None:
        candidate_attempt = getattr(dispatch, "attempt_id", None)
        if candidate_attempt is not None:
            attempt_id = str(candidate_attempt)

    state_value = getattr(outcome.test_run_state, "value", None)
    if state_value is None:
        state_value = str(outcome.test_run_state)

    rtnval: Dict[str, Any] = {
        "run_id": str(outcome.run_id),
        "project_id": str(project_id),
        "pod_id": str(pod_id) if pod_id is not None else None,
        "client_id": None,
        "job_id": str(catalog_entry.entry_id),
        "job_name": catalog_entry.display_name,
        "job_type": str(catalog_entry.raw_metadata.get("runner_kind", "testbase"))
            if isinstance(catalog_entry.raw_metadata, dict) is True else "testbase",
        "state": state_value,
        "terminal_outcome": None,
        "current_dispatch_attempt_id": attempt_id,
        "progress_summary": None,
        "created_at": triggered_at.isoformat(),
        "dispatched_at": triggered_at.isoformat(),
        "started_at": None,
        "completed_at": None,
        "labels": {},
        "catalog_entry_id": str(outcome.catalog_entry_id),
        "catalog_digest": outcome.catalog_digest,
    }
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/test-runs
# ---------------------------------------------------------------------------


def handle_trigger_test_run(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/test-runs``

        :param request: Incoming webworks request.

        :returns: JSON response (202) carrying the freshly-created
                  :class:`Run` envelope, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_test_runs_create_permission(
            request=request,
            db_session=db_session,
        )
        project_row = _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)

        # ``pod_id`` is optional. When supplied, the run targets that
        # specific pod. When omitted, the orchestrator selects an
        # eligible pod by capability match across the project's
        # enrolled, available pods.
        pod_id_raw = body.get("pod_id", None)
        explicit_pod_id: Optional[str] = None
        if pod_id_raw is not None:
            if isinstance(pod_id_raw, str) is False or len(pod_id_raw) == 0:
                _abort_problem(
                    request=request,
                    status=422,
                    detail="Field 'pod_id' must be a non-empty string when supplied.",
                )
            explicit_pod_id = pod_id_raw

        catalog_entry = _resolve_catalog_entry(
            request=request,
            db_session=db_session,
            project_id=project_id,
            body=body,
        )

        if explicit_pod_id is not None:
            candidates = _build_pod_candidates(
                request=request,
                db_session=db_session,
                project_id=project_id,
                pod_id=explicit_pod_id,
            )
            if len(candidates) == 0:
                _abort_problem(
                    request=request,
                    status=409,
                    detail="No eligible client registration for the requested pod.",
                    extensions={
                        "pod_id": explicit_pod_id,
                        "reason": "pod_offline_or_unregistered",
                    },
                )
        else:
            candidates = _build_eligible_pod_candidates(
                request=request,
                db_session=db_session,
                project_id=project_id,
            )

        params = body.get("params", {})
        if isinstance(params, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'params' must be an object.",
            )

        soft_deadline = _parse_positive_int_field(
            request=request,
            body=body,
            name="soft_deadline_seconds",
            default=DEFAULT_SOFT_DEADLINE_SECONDS,
        )
        hard_deadline = _parse_positive_int_field(
            request=request,
            body=body,
            name="hard_deadline_seconds",
            default=DEFAULT_HARD_DEADLINE_SECONDS,
        )

        active = ACTIVE_TEST_ORCHESTRATOR
        if active is None:
            _abort_problem(
                request=request,
                status=503,
                detail="Test orchestrator not configured.",
            )

        triggered_by: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            triggered_by = str(principal_user_id)

        project_slug = getattr(project_row, "slug", "") or ""

        trigger_request = orchestrator_module.TriggerRunRequest(
            project_id=project_id,
            project_slug=str(project_slug),
            catalog_entry_id=str(catalog_entry.entry_id),
            triggered_by=triggered_by,
            inputs=dict(params),
            candidates=candidates,
            soft_deadline_seconds=soft_deadline,
            hard_deadline_seconds=hard_deadline,
        )

        triggered_at = datetime.now(timezone.utc)
        try:
            outcome = active.trigger_run(
                db_session=db_session,
                request=trigger_request,
            )
        except CatalogEntryNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"catalog_entry_id": str(catalog_entry.entry_id)},
            )
            outcome = None  # unreachable
        except CapabilityMismatchError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"reason": "capability_mismatch"},
            )
            outcome = None  # unreachable
        except DispatchNoCandidatesError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"reason": "no_eligible_candidate"},
            )
            outcome = None  # unreachable
        except DispatchFailedError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"reason": "dispatch_failed"},
            )
            outcome = None  # unreachable
        except DispatchError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"reason": "dispatch_error"},
            )
            outcome = None  # unreachable
        except SemanticError as xcpt:
            # The runner rejected the inputs (for example no includes):
            # the caller's request is at fault, and the message says how.
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"reason": "invalid_runner_inputs"},
            )
            outcome = None  # unreachable
        except TestOrchestrationError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"reason": "test_orchestration_error"},
            )
            outcome = None  # unreachable

        # Prefer the pod the dispatcher actually picked; fall back to
        # the explicitly requested pod, or the first candidate's pod
        # when the orchestrator selected one by capability match.
        dispatch_outcome = getattr(outcome, "dispatch", None)
        resolved_pod_id: Optional[str] = None
        if dispatch_outcome is not None:
            dispatched_pod = getattr(dispatch_outcome, "pod_id", None)
            if dispatched_pod is not None:
                resolved_pod_id = str(dispatched_pod)
        if resolved_pod_id is None and explicit_pod_id is not None:
            resolved_pod_id = explicit_pod_id
        if resolved_pod_id is None and len(candidates) > 0:
            resolved_pod_id = candidates[0].pod_id

        _LOGGER.info(
            "pychestrate.test_runs.trigger project_id=%s pod_id=%s entry_id=%s run_id=%s",
            project_id,
            resolved_pod_id,
            str(catalog_entry.entry_id),
            str(outcome.run_id),
        )

        body_dict = _trigger_outcome_to_run_dict(
            outcome=outcome,
            project_id=project_id,
            pod_id=resolved_pod_id,
            catalog_entry=catalog_entry,
            triggered_at=triggered_at,
        )
        rtnval: Response = JSONResponse(content=body_dict, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_test_runs_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the test-runs trigger route to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + TEST_RUNS_PATH_SUFFIX, methods=["POST"],
    )(handle_trigger_test_run)
    return


__all__ = [
    "TEST_RUNS_PATH_SUFFIX",
    "TEST_RUNS_CREATE_PERMISSION_KEY",
    "DEFAULT_SOFT_DEADLINE_SECONDS",
    "DEFAULT_HARD_DEADLINE_SECONDS",
    "ACTIVE_TEST_ORCHESTRATOR",
    "set_active_test_orchestrator",
    "register_test_runs_routes",
    "handle_trigger_test_run",
]
