"""
.. module:: orchestration.pipelines.restapi.v1.pipeline_runs_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the pipeline-runs tag.

.. moduleauthor:: Code Craft AI LLC

Implements the pipeline-execution operations from
``specs/openapi/pychestrate.yaml`` (6-pipeline-execution PR p20q):

* ``POST /api/v1/projects/{project_id}/pipeline-runs``
* ``GET  /api/v1/projects/{project_id}/pipeline-runs``
* ``GET  /api/v1/projects/{project_id}/pipeline-runs/{run_id}``

``POST`` triggers a pipeline run: the :class:`PipelineOrchestrator`
parses + DAG-checks the supplied pipeline document, persists a
:class:`PipelineRun` + per-stage + per-step rows, and dispatches the
root stages' jobs through the reused build / test / provision
dispatch. ``GET`` (collection + item) reads pipeline runs including
per-stage status.

Each handler follows the shape of
``orchestration.pipelines.restapi.v1.pipeline_definitions_routes``:
cookie-or-api-key session validation, RBAC permission check, JSON
body decode, then delegation to the pipeline orchestrator and the
pipeline-definition read facade.

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging

from datetime import datetime
from typing import Any, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    repository as definition_repository,
    service as definition_service,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition.errors import (
    PipelineDagCycleError,
    PipelineDocumentInvalidError,
    PipelineRunNotFoundError,
    PipelineStepKindUnknownError,
)
from ccai.pychestrate.webservice.orchestration.pipelines.execution import (
    orchestrator as execution_orchestrator,
)
from ccai.pychestrate.webservice.orchestration.pipelines.execution.errors import (
    PipelineMatrixUnsupportedError,
    PipelineRunConflictError,
)
from ccai.pychestrate.webservice.orchestration.pipelines.execution.orchestrator import (
    PipelineTriggerInputs,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


PROJECTS_PATH_PREFIX = "/projects"
PIPELINE_RUNS_PATH_SUFFIX = "/pipeline-runs"

PIPELINE_RUNS_RUN_PERMISSION_KEY = "system:pipelines.run"
PIPELINE_RUNS_READ_PERMISSION_KEY = "system:pipeline_runs.read"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.pipelines.run_routes")


# ---------------------------------------------------------------------------
# Problem-flow plumbing
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
    """
        Internal control-flow exception carrying a webworks problem
        response so nested helpers can signal an error once and the
        top-level handler converts it at the boundary.
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


def _require_session(request: Request) -> Any:
    """
        Resolve the request-scoped db session or abort 503.

        :param request: Incoming webworks request.

        :returns: SQLAlchemy session.
    """
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
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
    principal = getattr(request, "auth_principal", None)
    if principal is None:
        _abort_problem(
            request=request,
            status=401,
            detail="Authentication required.",
        )

    from datetime import timezone
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


def _step_run_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`PipelineStepRunView` to the OpenAPI
        ``PipelineStepStatus`` schema.

        :param view: Step-run read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "step_run_id": view.step_run_id,
        "step_id": view.step_id,
        "step_index": int(view.step_index),
        "kind_name": view.kind_name,
        "job_kind": view.job_kind,
        "layer5_run_id": view.layer5_run_id,
        "state": view.state.value,
        "final_state_reason": view.final_state_reason,
        "started_at": _iso_or_none(view.started_at),
        "finished_at": _iso_or_none(view.finished_at),
    }
    return rtnval


def _stage_run_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`PipelineStageRunView` to the OpenAPI
        ``PipelineStageStatus`` schema.

        :param view: Stage-run read-model.

        :returns: JSON-friendly dict.
    """
    steps: List[Dict[str, Any]] = []
    for step in view.steps:
        steps.append(_step_run_to_dict(view=step))
    rtnval: Dict[str, Any] = {
        "stage_run_id": view.stage_run_id,
        "stage_id": view.stage_id,
        "stage_index": int(view.stage_index),
        "state": view.state.value,
        "when_clause": view.when_clause,
        "needs": list(view.needs),
        "steps": steps,
        "final_state_reason": view.final_state_reason,
        "started_at": _iso_or_none(view.started_at),
        "finished_at": _iso_or_none(view.finished_at),
    }
    return rtnval


def _pipeline_run_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`PipelineRunView` to the OpenAPI
        ``PipelineRun`` schema.

        :param view: Pipeline-run read-model.

        :returns: JSON-friendly dict.
    """
    stages: List[Dict[str, Any]] = []
    for stage in view.stages:
        stages.append(_stage_run_to_dict(view=stage))
    rtnval: Dict[str, Any] = {
        "run_id": view.run_id,
        "project_id": str(view.project_id),
        "pipeline_id": view.pipeline_digest_sha256,
        "commit_sha": view.commit_sha,
        "ref": view.ref,
        "filename": view.filename,
        "state": view.state.value,
        "trigger_cause": view.trigger_cause.value,
        "actor_id": view.actor_id,
        "stages": stages,
        "final_state_reason": view.final_state_reason,
        "started_at": _iso_or_none(view.started_at),
        "finished_at": _iso_or_none(view.finished_at),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Body decoder
# ---------------------------------------------------------------------------


def _decode_saved_pipeline_trigger_body(
        *,
        request: Request,
        body: Dict[str, Any],
        db_session: Any,
        project_id: str
    ) -> Dict[str, Any]:
    """
        Resolve a run requested by ``pipeline_id``: the document is the project's saved
        definition (what the pipelines page shows), so the caller does not have to send it
        again. The commit and filename are the ones it was saved from (the cache row is the
        same one a run of the inline document would use, so no second copy is made); a
        ``commit_sha`` in the body overrides the commit.

        :param request: Incoming webworks request.
        :param body: Decoded JSON object body, with ``pipeline_id`` and without ``document``.
        :param db_session: Active SQLAlchemy session.
        :param project_id: The project the run is for.

        :returns: Dict with the decoded trigger inputs.
    """
    if "document" in body:
        _abort_problem(
            request=request, status=422,
            detail="Give either 'pipeline_id' (a saved pipeline) or 'document', not both.",
            extensions={"invalid_fields": ["pipeline_id", "document"]},
        )
    pipeline_id = body.get("pipeline_id", None)
    if not isinstance(pipeline_id, str) or len(pipeline_id.strip()) == 0:
        _abort_problem(
            request=request, status=422, detail="Field 'pipeline_id' must be a non-empty string.",
            extensions={"invalid_fields": ["pipeline_id"]},
        )
        pipeline_id = ""  # unreachable
    row = definition_repository.find_document_cache_by_digest(
        db_session=db_session, project_id=project_id, pipeline_digest_sha256=pipeline_id.strip(),
    )
    if row is None:
        _abort_problem(
            request=request, status=404,
            detail="No saved pipeline has this id in this project. Save it first.",
            extensions={"reason": "pipeline_not_found", "pipeline_id": pipeline_id},
        )
        return {}  # unreachable
    commit_sha = body.get("commit_sha", None)
    if commit_sha is None:
        commit_sha = row.commit_sha
    elif not isinstance(commit_sha, str) or len(commit_sha.strip()) == 0:
        _abort_problem(
            request=request, status=422, detail="Field 'commit_sha' must be a non-empty string.",
            extensions={"invalid_fields": ["commit_sha"]},
        )
    ref = body.get("ref", "")
    matrix = body.get("matrix", {})
    rtnval: Dict[str, Any] = {
        "document_bytes": str(row.canonical_json).encode("utf-8"),
        "commit_sha": str(commit_sha).strip(),
        "ref": ref if isinstance(ref, str) else "",
        "filename": str(row.filename),
        "matrix": matrix if isinstance(matrix, dict) else {},
    }
    return rtnval


def _decode_trigger_body(
        *,
        request: Request,
        body: Dict[str, Any],
        db_session: Any = None,
        project_id: str = ""
    ) -> Dict[str, Any]:
    """
        Validate the trigger body and return the document bytes plus
        the run metadata.

        The body carries the pipeline document inline (string or
        object) plus ``commit_sha`` / ``ref`` / ``filename`` and an
        optional ``matrix`` dimensions object (the orchestrator
        refuses a non-empty one -- matrix execution is unsupported); or
        a ``pipeline_id`` naming a saved pipeline instead of the document.

        :param request: Incoming webworks request.
        :param body: Decoded JSON object body.
        :param db_session: Active SQLAlchemy session (needed for ``pipeline_id``).
        :param project_id: The project the run is for (needed for ``pipeline_id``).

        :returns: Dict with the decoded trigger inputs.
    """
    if "pipeline_id" in body:
        return _decode_saved_pipeline_trigger_body(
            request=request, body=body, db_session=db_session, project_id=project_id,
        )
    commit_sha = body.get("commit_sha", None)
    if not isinstance(commit_sha, str) or len(commit_sha) == 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'commit_sha' is required.",
            extensions={"missing_fields": ["commit_sha"]},
        )

    filename = body.get("filename", None)
    if not isinstance(filename, str) or len(filename) == 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'filename' is required.",
            extensions={"missing_fields": ["filename"]},
        )

    document = body.get("document", None)
    if document is None:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'document' is required.",
            extensions={"missing_fields": ["document"]},
        )

    if isinstance(document, str):
        document_text = document
    elif isinstance(document, dict):
        document_text = json.dumps(document)
        if not filename.lower().endswith(".json"):
            filename = filename + ".json"
    else:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'document' must be a string or an object.",
        )
        document_text = ""  # unreachable

    ref = body.get("ref", "")
    if not isinstance(ref, str):
        ref = ""

    matrix = body.get("matrix", {})
    if not isinstance(matrix, dict):
        matrix = {}

    rtnval: Dict[str, Any] = {
        "document_bytes": document_text.encode("utf-8"),
        "commit_sha": commit_sha,
        "ref": ref,
        "filename": filename,
        "matrix": matrix,
    }
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/pipeline-runs
# ---------------------------------------------------------------------------


def handle_trigger_pipeline_run(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/pipeline-runs``

        Triggers a pipeline run. The :class:`PipelineOrchestrator`
        parses + DAG-checks the document, persists the run + stages +
        steps, and dispatches the root stages' jobs through the reused
        build / test / provision dispatch.

        :param request: Incoming webworks request.

        :returns: JSON response (201) with the :class:`PipelineRun`,
                  or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PIPELINE_RUNS_RUN_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        orchestrator = execution_orchestrator.get_active_pipeline_orchestrator()
        if orchestrator is None:
            _abort_problem(
                request=request,
                status=503,
                detail=(
                    "Pipeline orchestrator not wired."
                    " bootstrap_phase6_runtime publishes it via"
                    " set_active_pipeline_orchestrator()."
                ),
            )

        body = _decode_json_object_or_abort(request=request)
        decoded = _decode_trigger_body(
            request=request, body=body, db_session=db_session, project_id=project_id,
        )

        project_row = projects_repo.get_project_by_id(
            db_session=db_session, project_id=project_id,
        )
        project_slug = getattr(project_row, "slug", "") or ""
        actor_id = getattr(principal, "user_id", None)
        if actor_id is not None:
            actor_id = str(actor_id)

        candidates = orchestrator._eligible_candidates_for_project(
            db_session=db_session, project_id=project_id,
        )

        inputs = PipelineTriggerInputs(
            project_id=project_id,
            project_slug=project_slug,
            commit_sha=decoded["commit_sha"],
            ref=decoded["ref"],
            filename=decoded["filename"],
            document_bytes=decoded["document_bytes"],
            actor_id=actor_id,
            candidates=candidates,
            matrix_params=decoded["matrix"],
        )

        try:
            view = orchestrator.trigger_pipeline(
                db_session=db_session, inputs=inputs,
            )
        except PipelineRunConflictError as xcpt:
            _abort_problem(
                request=request,
                status=409,
                detail=str(xcpt),
                extensions={"reason": "pipeline_run_conflict"},
            )
            view = None  # unreachable
        except PipelineMatrixUnsupportedError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"reason": "matrix_not_supported"},
            )
            view = None  # unreachable
        except PipelineDagCycleError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"reason": "dag_cycle"},
            )
            view = None  # unreachable
        except PipelineStepKindUnknownError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"reason": "unknown_step_kind"},
            )
            view = None  # unreachable
        except PipelineDocumentInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"reason": "document_invalid"},
            )
            view = None  # unreachable

        _LOGGER.info(
            "pychestrate.pipeline_runs.triggered project_id=%s run_id=%s"
            " state=%s",
            project_id, view.run_id, view.state.value,
        )

        body_dict = _pipeline_run_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/pipeline-runs
# ---------------------------------------------------------------------------


def handle_list_pipeline_runs(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pipeline-runs``

        Query params: ``page``, ``per_page``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a ``{items, meta}`` page or
                  a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PIPELINE_RUNS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

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

        all_views = definition_service.list_pipeline_runs(
            db_session=db_session,
            project_id=project_id,
            limit=MAX_PAGE_SIZE,
        )

        total = len(all_views)
        offset = (page - 1) * per_page
        window = all_views[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for view in window:
            items.append(_pipeline_run_to_dict(view=view))

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
# GET /api/v1/projects/{project_id}/pipeline-runs/{run_id}
# ---------------------------------------------------------------------------


def handle_read_pipeline_run(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pipeline-runs/{run_id}``

        Reads a single pipeline run including its per-stage status.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the :class:`PipelineRun`,
                  or a problem response (404 on a miss).
    """
    project_id = request.path_params.get("project_id", "")
    run_id = request.path_params.get("run_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PIPELINE_RUNS_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            view = definition_service.get_pipeline_run(
                db_session=db_session, run_id=run_id,
            )
        except PipelineRunNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"run_id": run_id},
            )
            view = None  # unreachable
        except Exception:  # noqa: BLE001 -- malformed run id -> 404
            # A run_id that is not a valid UUID is rejected by the
            # column type before the row lookup; surface it as a 404
            # rather than a 500.
            _abort_problem(
                request=request,
                status=404,
                detail="Pipeline run not found.",
                extensions={"run_id": run_id},
            )
            view = None  # unreachable

        if str(view.project_id) != str(project_id):
            _abort_problem(
                request=request,
                status=404,
                detail="Pipeline run not found in project.",
                extensions={"run_id": run_id, "project_id": project_id},
            )

        body = _pipeline_run_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_pipeline_runs_routes(
        *,
        app: Any,
        version_prefix: str
    ) -> None:
    """
        Attach the pipeline-run REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + PIPELINE_RUNS_PATH_SUFFIX, methods=["POST"],
    )(handle_trigger_pipeline_run)
    app.attach_route(
        base + PIPELINE_RUNS_PATH_SUFFIX, methods=["GET"],
    )(handle_list_pipeline_runs)
    app.attach_route(
        base + PIPELINE_RUNS_PATH_SUFFIX + "/{run_id}", methods=["GET"],
    )(handle_read_pipeline_run)

    _LOGGER.info(
        "pychestrate.pipeline_runs.routes_registered prefix=%s",
        version_prefix,
    )
    return


__all__ = [
    "PIPELINE_RUNS_PATH_SUFFIX",
    "PIPELINE_RUNS_RUN_PERMISSION_KEY",
    "PIPELINE_RUNS_READ_PERMISSION_KEY",
    "register_pipeline_runs_routes",
    "handle_trigger_pipeline_run",
    "handle_list_pipeline_runs",
    "handle_read_pipeline_run",
]
