"""
.. module:: orchestration.build.restapi.v1.build_runs_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the builds + build artifacts tags.

.. moduleauthor:: Automation Mojo LLC

Implements the build-orchestration operations from
``specs/openapi/pychestrate.yaml``:

* ``POST /api/v1/projects/{project_id}/builds``
* ``GET  /api/v1/projects/{project_id}/builds``
* ``GET  /api/v1/projects/{project_id}/builds/{build_id}``
* ``GET  /api/v1/projects/{project_id}/builds/{build_id}/artifacts``

Each handler follows the shape of
``webservice.orchestration.test.restapi.v1.test_runs_routes``:
cookie-or-api-key session validation, RBAC permission check, JSON
body decode, then delegation to the in-tree build-orchestration
facade (``orchestration.build.service``) and the build-artifacts
facade (``orchestration.build.artifacts.service``).

The build domain models a :class:`BuildRun` directly -- there is
no ``BuildPlan`` ORM table in the M1 scaffolding, so this PR
exposes the build-run lifecycle (trigger / read / list) rather
than a separate plan resource. ``POST /builds`` resolves the
runner kind, validates inputs, computes the repro digest, builds
+ signs a ``job_kind=build`` JobEnvelope, and dispatches it
through the wired :class:`JobDispatcher` so the build job queues
for an enrolled client -- the BuildRun comes back ``running``
with the run-state machine at ``dispatching``. When the project
has no enrolled pod with an active client registration the
trigger answers ``409`` (the same "no eligible pod" path test
runs use).

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response

from automojo.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from automojo.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from automojo.pychestrate.webservice.orchestration.build import (
    service as build_service,
)
from automojo.pychestrate.webservice.orchestration.build.errors import (
    BuildDispatchFailedError,
    BuildDispatchUnavailableError,
    BuildInputsInvalidError,
    BuildRunNotFoundError,
    BuildRunnerKindUnknownError,
    BuildSourceIntegrationUnknownError,
)
from automojo.pychestrate.webservice.pods.models import (
    PodDefinition,
    PodRegistration,
    RegistrationState,
)
from automojo.pychestrate.webservice.orchestration.build.artifacts import (
    repository as artifacts_repo,
)
from automojo.pychestrate.webservice.orchestration.build.artifacts import (
    service as artifacts_service,
)
from automojo.pychestrate.webservice.projects import repository as projects_repo
from automojo.pychestrate.webservice.security.rbac import rbac_evaluator


BUILDS_PATH_SUFFIX = "/builds"
PROJECTS_PATH_PREFIX = "/projects"

BUILDS_READ_PERMISSION_KEY = "system:builds.read"
BUILDS_CREATE_PERMISSION_KEY = "system:builds.create"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.builds.routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
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
        middleware, or ``None`` when the request is anonymous.

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


def _decode_json_object_or_abort(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request body as a JSON object, aborting with
        422 on missing / malformed / non-dict bodies.

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


def _require_project_exists(
        *,
        request: Request,
        db_session: Any,
        project_id: str
    ) -> Any:
    """
        Look up the project row, aborting 404 when not found.

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


def _enum_value_or_str(value: Any) -> str:
    """
        Return the ``.value`` of a string-enum or its ``str``.

        :param value: Enum instance or scalar.

        :returns: String value.
    """
    extracted = getattr(value, "value", None)
    if extracted is not None:
        rtnval = str(extracted)
        return rtnval
    rtnval = str(value)
    return rtnval


def _toolchain_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`BuildToolchainSnapshotView`.

        :param view: Toolchain read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "toolchain_key": view.toolchain_key,
        "version": view.version,
        "fingerprint_sha256": view.fingerprint_sha256,
    }
    return rtnval


def _build_run_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`BuildRunView` to the OpenAPI
        ``BuildRun`` schema.

        :param view: Read-model returned by the build facade.

        :returns: JSON-friendly dict.
    """
    toolchain: List[Dict[str, Any]] = []
    for entry in view.toolchain:
        toolchain.append(_toolchain_view_to_dict(view=entry))
    rtnval: Dict[str, Any] = {
        "run_id": str(view.run_id),
        "project_id": str(view.project_id),
        "runner_kind": view.runner_kind,
        "repro_digest_sha256": view.repro_digest_sha256,
        "state": _enum_value_or_str(view.state),
        "run_state": getattr(view, "run_state", None),
        "dispatch_attempt_id": getattr(view, "dispatch_attempt_id", None),
        "layer5_run_id": view.layer5_run_id,
        "pipeline_run_id": view.pipeline_run_id,
        "pipeline_step_run_id": view.pipeline_step_run_id,
        "actor_id": view.actor_id,
        "started_at": _iso_or_none(view.started_at),
        "finished_at": _iso_or_none(view.finished_at),
        "final_state_reason": view.final_state_reason,
        "inputs": dict(view.inputs or {}),
        "annotations": dict(view.annotations or {}),
        "toolchain": toolchain,
        "source": getattr(view, "source", None),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Dispatch-candidate selection
# ---------------------------------------------------------------------------
#
# Mirrors the capability-based eligible-pod selection the test
# orchestrator uses: every pod enrolled in the project that carries at
# least one REGISTERED client registration is an eligible target. The
# build dispatcher then picks one via the active dispatch strategy.


def _candidates_for_pod(
        *,
        db_session: Any,
        pod_id: str
    ) -> List[DispatchCandidate]:
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


def _build_eligible_pod_candidates(
        *,
        db_session: Any,
        project_id: str
    ) -> List[DispatchCandidate]:
    """
        Enumerate every pod enrolled in the project carrying at least
        one REGISTERED client registration and build the combined
        :class:`DispatchCandidate` list. May be empty -- the caller
        decides how to surface "no eligible pod".

        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.

        :returns: List of dispatch candidates (possibly empty).
    """
    pod_rows = (
        db_session.query(PodDefinition)
        .filter(PodDefinition.project_id == project_id)
        .all()
    )

    candidates: List[DispatchCandidate] = []
    for pod_row in pod_rows:
        pod_id = str(pod_row.pod_id)
        pod_candidates = _candidates_for_pod(
            db_session=db_session, pod_id=pod_id,
        )
        for candidate in pod_candidates:
            candidates.append(candidate)

    rtnval = candidates
    return rtnval


def _artifact_entry_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize an :class:`ArtifactEntryView` to the OpenAPI
        ``BuildArtifact`` schema.

        :param view: Artifact-entry read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "manifest_id": str(view.manifest_id),
        "artifact_id": view.artifact_id,
        "artifact_type": view.artifact_type,
        "artifact_name": view.artifact_name,
        "storage_uri": view.storage_uri,
        "sha256": view.sha256,
        "payload": dict(view.payload or {}),
    }
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/builds
# ---------------------------------------------------------------------------


def _build_run_inputs(
        *,
        request: Request,
        body: Dict[str, Any]
    ) -> Any:
    """
        Validate the trigger body and build a
        :class:`BuildRunInputs`.

        :param request: Incoming webworks request.
        :param body: Decoded JSON object body.

        :returns: BuildRunInputs instance.
    """
    runner_kind = body.get("runner_kind", None)
    if not isinstance(runner_kind, str) or len(runner_kind) == 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'runner_kind' is required.",
            extensions={"missing_fields": ["runner_kind"]},
        )

    runner_inputs = body.get("runner_inputs", {})
    if isinstance(runner_inputs, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'runner_inputs' must be an object.",
        )

    input_files = body.get("input_files", {})
    if isinstance(input_files, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'input_files' must be an object.",
        )

    env = body.get("env", {})
    if isinstance(env, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'env' must be an object.",
        )

    annotations = body.get("annotations", {})
    if isinstance(annotations, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'annotations' must be an object.",
        )

    toolchain_raw = body.get("toolchain", [])
    if isinstance(toolchain_raw, list) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'toolchain' must be an array.",
        )
    toolchain_entries: List[Any] = []
    for index, entry in enumerate(toolchain_raw):
        if isinstance(entry, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'toolchain[{}]' must be an object.".format(index),
            )
        entry_key = entry.get("key", None)
        version = entry.get("version", "")
        fingerprint = entry.get("fingerprint_sha256", "")
        if not isinstance(entry_key, str) or len(entry_key) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'toolchain[{}].key' is required.".format(index),
            )
        toolchain_entries.append(
            build_service.BuildToolchainEntry(
                key=entry_key,
                version=str(version) if version is not None else "",
                fingerprint_sha256=(
                    str(fingerprint) if fingerprint is not None else ""
                ),
            )
        )

    source_integration_id = body.get("source_integration_id", None)
    if source_integration_id is not None:
        if not isinstance(source_integration_id, str):
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'source_integration_id' must be a string.",
            )
        if len(source_integration_id) == 0:
            source_integration_id = None

    rtnval = build_service.BuildRunInputs(
        runner_kind=runner_kind,
        runner_inputs=dict(runner_inputs),
        input_files=dict(input_files),
        toolchain=tuple(toolchain_entries),
        env=dict(env),
        annotations=dict(annotations),
        source_integration_id=source_integration_id,
    )
    return rtnval


def handle_trigger_build(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/builds``

        Triggers a build run from the supplied runner kind +
        inputs. Delegates to
        :func:`orchestration.build.service.trigger_run`.

        :param request: Incoming webworks request.

        :returns: JSON response (202) carrying the freshly-created
                  :class:`BuildRun`, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=BUILDS_CREATE_PERMISSION_KEY,
        )
        project_row = _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)
        inputs = _build_run_inputs(request=request, body=body)

        # Capability-based eligible-pod selection -- the same set the
        # test orchestrator narrows by capability match. No enrolled
        # pod with an active client registration => 409, exactly as
        # test runs answer.
        candidates = _build_eligible_pod_candidates(
            db_session=db_session,
            project_id=project_id,
        )
        if len(candidates) == 0:
            _abort_problem(
                request=request,
                status=409,
                detail=(
                    "No enrolled pod matches the build job's "
                    "requirements -- enroll a client/pod first."
                ),
                extensions={
                    "project_id": project_id,
                    "reason": "no_eligible_pod",
                },
            )

        actor_id: Optional[str] = None
        principal_user_id = getattr(principal, "user_id", None)
        if principal_user_id is not None:
            actor_id = str(principal_user_id)

        project_slug = getattr(project_row, "slug", "") or ""

        aspects = build_service.BuildTriggerAspects(
            actor_id=actor_id,
            candidates=candidates,
            project_slug=str(project_slug),
        )

        try:
            view = build_service.trigger_run(
                db_session=db_session,
                project_id=project_id,
                inputs=inputs,
                aspects=aspects,
            )
        except BuildRunnerKindUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"runner_kind": inputs.runner_kind},
            )
            view = None  # unreachable
        except BuildInputsInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"runner_kind": inputs.runner_kind},
            )
            view = None  # unreachable
        except BuildSourceIntegrationUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={
                    "source_integration_id": inputs.source_integration_id,
                },
            )
            view = None  # unreachable
        except BuildDispatchUnavailableError as xcpt:
            _abort_problem(
                request=request,
                status=503,
                detail=str(xcpt),
                extensions={"reason": "dispatch_not_configured"},
            )
            view = None  # unreachable
        except BuildDispatchFailedError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"reason": "dispatch_failed"},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.builds.trigger project_id=%s runner_kind=%s run_id=%s",
            project_id,
            inputs.runner_kind,
            str(view.run_id),
        )

        body_dict = _build_run_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/builds
# ---------------------------------------------------------------------------


def handle_list_builds(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/builds``

        Query params: ``state``, ``page``, ``per_page``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``{items, meta}`` page
                  or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=BUILDS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

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

        all_views = build_service.list_build_runs_for_project(
            db_session=db_session,
            project_id=project_id,
            limit=MAX_PAGE_SIZE,
        )
        if state_filter is not None and len(state_filter) > 0:
            filtered: List[Any] = []
            for view in all_views:
                if _enum_value_or_str(view.state) == state_filter:
                    filtered.append(view)
            all_views = filtered

        total = len(all_views)
        offset = (page - 1) * per_page
        window = all_views[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for view in window:
            items.append(_build_run_view_to_dict(view=view))

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
# GET /api/v1/projects/{project_id}/builds/{build_id}
# ---------------------------------------------------------------------------


def handle_read_build(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/builds/{build_id}``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the build run dict or a
                  problem response.
    """
    project_id = request.path_params.get("project_id", "")
    build_id = request.path_params.get("build_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=BUILDS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            view = build_service.get_build_run(
                db_session=db_session,
                run_id=build_id,
            )
        except BuildRunNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"build_id": build_id},
            )
            view = None  # unreachable

        if str(view.project_id) != str(project_id):
            _abort_problem(
                request=request,
                status=404,
                detail="Build run does not belong to this project.",
                extensions={"project_id": project_id, "build_id": build_id},
            )

        body = _build_run_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/builds/{build_id}/artifacts
# ---------------------------------------------------------------------------


def handle_list_build_artifacts(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/builds/{build_id}/artifacts``

        Lists the artifact-manifest entries synthesized for a
        build run. Returns an empty list when the build run has
        not synthesized a manifest yet.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with an ``{items, meta}``
                  page or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    build_id = request.path_params.get("build_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=BUILDS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            view = build_service.get_build_run(
                db_session=db_session,
                run_id=build_id,
            )
        except BuildRunNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"build_id": build_id},
            )
            view = None  # unreachable

        if str(view.project_id) != str(project_id):
            _abort_problem(
                request=request,
                status=404,
                detail="Build run does not belong to this project.",
                extensions={"project_id": project_id, "build_id": build_id},
            )

        manifest_row = artifacts_repo.find_manifest_by_build_run(
            db_session=db_session,
            build_run_id=build_id,
        )

        items: List[Dict[str, Any]] = []
        manifest_id: Optional[str] = None
        if manifest_row is not None:
            manifest_id = str(manifest_row.manifest_id)
            entry_views = artifacts_service.list_entries(
                db_session=db_session,
                manifest_id=manifest_id,
            )
            for entry_view in entry_views:
                items.append(_artifact_entry_view_to_dict(view=entry_view))

        body = {
            "items": items,
            "meta": {
                "page": 1,
                "per_page": len(items),
                "total": len(items),
                "next_cursor": None,
            },
            "manifest_id": manifest_id,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_build_runs_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the build-runs REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + BUILDS_PATH_SUFFIX, methods=["POST"],
    )(handle_trigger_build)
    app.attach_route(
        base + BUILDS_PATH_SUFFIX, methods=["GET"],
    )(handle_list_builds)
    app.attach_route(
        base + BUILDS_PATH_SUFFIX + "/{build_id}", methods=["GET"],
    )(handle_read_build)
    app.attach_route(
        base + BUILDS_PATH_SUFFIX + "/{build_id}/artifacts", methods=["GET"],
    )(handle_list_build_artifacts)

    _LOGGER.info(
        "pychestrate.builds.routes.dispatch_wired: POST /builds"
        " dispatches a job_kind=build JobEnvelope through the wired"
        " JobDispatcher (orchestration.build.service.trigger_run)."
    )
    return


__all__ = [
    "BUILDS_PATH_SUFFIX",
    "BUILDS_READ_PERMISSION_KEY",
    "BUILDS_CREATE_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_build_runs_routes",
    "handle_trigger_build",
    "handle_list_builds",
    "handle_read_build",
    "handle_list_build_artifacts",
]
