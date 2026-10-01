"""
.. module:: orchestration.pipelines.restapi.v1.pipeline_definitions_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the pipelines tag.

.. moduleauthor:: Code Craft AI LLC

Implements the pipeline-definition + matrix-sharding operations
from ``specs/openapi/pychestrate.yaml``:

* ``GET    /api/v1/projects/{project_id}/pipelines``
* ``POST   /api/v1/projects/{project_id}/pipelines``
* ``GET    /api/v1/projects/{project_id}/pipelines/{pipeline_id}``
* ``DELETE /api/v1/projects/{project_id}/pipelines/{pipeline_id}``
* ``POST   /api/v1/projects/{project_id}/pipelines:validate``
* ``POST   /api/v1/projects/{project_id}/pipelines:expand-matrix``

Each handler follows the shape of
``webservice.orchestration.build.restapi.v1.build_runs_routes``:
cookie-or-api-key session validation, RBAC permission check, JSON
body decode, then delegation to the in-tree pipeline-definition
facade (``orchestration.pipelines.definition.service``) and the
matrix-sharding facade (``orchestration.pipelines.sharding.service``).

The pipeline domain models pipeline runs directly; a "pipeline
definition" is the parsed + DAG-validated + canonicalized
document cached in ``PipelineDocumentCache``. The stable
``pipeline_id`` exposed over REST is the canonical-document
SHA-256 digest -- a definition with identical content always
resolves to the same id, so ``POST /pipelines`` is an upsert and
no ``PATCH`` is exposed (a content edit is just another upsert).

Pipeline execution dispatch (triggering a run) is intentionally
NOT exposed by this PR. The Layer-5 dispatch handoff is M2 work
(see ``orchestration.pipelines.definition.service.trigger_run``)
and the matrix-expand endpoint is a pure compute/preview surface
that writes no rows and emits no events.

Error responses are RFC 7807 problem documents emitted via
:mod:`api.problem_json_webworks`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    service as definition_service,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition.errors import (
    PipelineDagCycleError,
    PipelineDocumentInvalidError,
    PipelineRunNotFoundError,
    PipelineStepKindUnknownError,
)
from ccai.pychestrate.webservice.orchestration.pipelines.sharding import (
    service as sharding_service,
)
from ccai.pychestrate.webservice.orchestration.pipelines.sharding.errors import (
    MatrixSpecInvalidError,
    ShardingStrategyNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.pipelines.sharding.expansion import (
    MatrixDimensionFilter,
    MatrixSpec,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


PIPELINES_PATH_SUFFIX = "/pipelines"
PIPELINES_VALIDATE_PATH_SUFFIX = "/pipelines:validate"
PIPELINES_EXPAND_MATRIX_PATH_SUFFIX = "/pipelines:expand-matrix"
PROJECTS_PATH_PREFIX = "/projects"

PIPELINES_READ_PERMISSION_KEY = "system:pipelines.read"
PIPELINES_WRITE_PERMISSION_KEY = "system:pipelines.write"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

DEFAULT_STRATEGY_NAME = "cartesian"

_LOGGER = logging.getLogger("pychestrate.pipelines.routes")


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


def _step_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`PipelineStepView` to the OpenAPI
        ``PipelineStep`` schema.

        :param view: Step read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "step_id": view.step_id,
        "kind_name": view.kind_name,
        "uses": view.uses,
        "inputs": dict(view.inputs or {}),
    }
    return rtnval


def _stage_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`PipelineStageView` to the OpenAPI
        ``PipelineStage`` schema.

        :param view: Stage read-model.

        :returns: JSON-friendly dict.
    """
    steps: List[Dict[str, Any]] = []
    for step in view.steps:
        steps.append(_step_view_to_dict(view=step))
    rtnval: Dict[str, Any] = {
        "stage_id": view.stage_id,
        "when_clause": view.when_clause,
        "needs": list(view.needs),
        "steps": steps,
    }
    return rtnval


def collapse_by_definition(*, views: List[Any]) -> List[Tuple[Any, List[Any]]]:
    """
        Collapse cache rows that hold the same definition into one entry.

        A row is keyed by ``(commit, filename)`` but a pipeline is identified by the
        digest of its document, so saving the same document from a second commit or
        file adds a row with the same ``pipeline_id``. The list shows the pipeline once.

        :param views: The definition views, newest first.

        :returns: ``(newest view, the older views of the same definition)`` per
                  distinct ``pipeline_id``, in the order the newest views appear.
    """
    order: List[str] = []
    newest: Dict[str, Any] = {}
    others: Dict[str, List[Any]] = {}
    for view in views:
        key = str(view.pipeline_id)
        if key not in newest:
            order.append(key)
            newest[key] = view
            others[key] = []
        else:
            others[key].append(view)
    rtnval = [(newest[key], others[key]) for key in order]
    return rtnval


def _definition_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`PipelineDefinitionView` to the OpenAPI
        ``PipelineDefinition`` schema.

        :param view: Read-model returned by the definition facade.

        :returns: JSON-friendly dict.
    """
    stages: List[Dict[str, Any]] = []
    for stage in view.stages:
        stages.append(_stage_view_to_dict(view=stage))
    rtnval: Dict[str, Any] = {
        "pipeline_id": view.pipeline_id,
        "project_id": str(view.project_id),
        "name": view.name,
        "schema_version": view.schema_version,
        "commit_sha": view.commit_sha,
        "filename": view.filename,
        "stages": stages,
        "cached_at": _iso_or_none(view.cached_at),
    }
    return rtnval


def _validation_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`DagValidationView` to the OpenAPI
        ``DagValidationResult`` schema.

        :param view: DAG-validation read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "valid": bool(view.valid),
        "stage_count": int(view.stage_count),
        "topological_order": list(view.topological_order),
        "issues": list(view.issues),
    }
    return rtnval


def _expansion_shard_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize an :class:`ExpansionPreviewShard`.

        :param view: Preview-shard read-model.

        :returns: JSON-friendly dict.
    """
    rtnval: Dict[str, Any] = {
        "shard_id": view.shard_id,
        "parallel_group": view.parallel_group,
        "sequence_in_group": int(view.sequence_in_group),
        "dimension_values": dict(view.dimension_values or {}),
    }
    return rtnval


def _expansion_preview_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize an :class:`ExpansionPreview` to the OpenAPI
        ``ShardExpansion`` schema.

        :param view: Expansion-preview read-model.

        :returns: JSON-friendly dict.
    """
    shards: List[Dict[str, Any]] = []
    for shard in view.shards:
        shards.append(_expansion_shard_to_dict(view=shard))
    rtnval: Dict[str, Any] = {
        "strategy_name": view.strategy_name,
        "matrix_spec_canonical_sha256": view.matrix_spec_canonical_sha256,
        "shard_count": int(view.shard_count),
        "shards": shards,
    }
    return rtnval


# ---------------------------------------------------------------------------
# Body decoders
# ---------------------------------------------------------------------------


def _decode_definition_document(
        *,
        request: Request,
        body: Dict[str, Any]
    ) -> Dict[str, Any]:
    """
        Validate the upsert body and return the document bytes plus
        the cache-key components.

        :param request: Incoming webworks request.
        :param body: Decoded JSON object body.

        :returns: Dict with ``document_bytes`` / ``commit_sha`` /
                  ``filename`` keys.
    """
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

    rtnval: Dict[str, Any] = {
        "document_bytes": document_text.encode("utf-8"),
        "commit_sha": commit_sha,
        "filename": filename,
    }
    return rtnval


def _decode_matrix_filters(
        *,
        request: Request,
        raw: Any,
        field_name: str
    ) -> List[MatrixDimensionFilter]:
    """
        Decode an ``includes`` / ``excludes`` filter array.

        :param request: Incoming webworks request.
        :param raw: Raw filter array (or None).
        :param field_name: Field name for error context.

        :returns: List of :class:`MatrixDimensionFilter`.
    """
    if raw is None:
        rtnval: List[MatrixDimensionFilter] = []
        return rtnval
    if isinstance(raw, list) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field '{}' must be an array.".format(field_name),
        )
    filters: List[MatrixDimensionFilter] = []
    for index, entry in enumerate(raw):
        if isinstance(entry, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field '{}[{}]' must be an object.".format(
                    field_name, index,
                ),
            )
        values: Dict[str, str] = {}
        for key, value in entry.items():
            values[str(key)] = str(value)
        filters.append(MatrixDimensionFilter(values=values))
    rtnval = filters
    return rtnval


def _decode_matrix_spec(
        *,
        request: Request,
        body: Dict[str, Any]
    ) -> MatrixSpec:
    """
        Validate the expand-matrix body and build a
        :class:`MatrixSpec`.

        :param request: Incoming webworks request.
        :param body: Decoded JSON object body.

        :returns: A :class:`MatrixSpec`.
    """
    matrix_raw = body.get("matrix", None)
    if matrix_raw is None:
        matrix_raw = body
    if isinstance(matrix_raw, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'matrix' must be an object.",
        )

    dimensions_raw = matrix_raw.get("dimensions", None)
    if dimensions_raw is None:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'matrix.dimensions' is required.",
            extensions={"missing_fields": ["matrix.dimensions"]},
        )
    if isinstance(dimensions_raw, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'matrix.dimensions' must be an object.",
        )

    dimensions: Dict[str, List[str]] = {}
    for name, values in dimensions_raw.items():
        if isinstance(values, list) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Dimension '{}' must map to an array.".format(name),
            )
        dimensions[str(name)] = [str(value) for value in values]

    includes = _decode_matrix_filters(
        request=request,
        raw=matrix_raw.get("includes", None),
        field_name="matrix.includes",
    )
    excludes = _decode_matrix_filters(
        request=request,
        raw=matrix_raw.get("excludes", None),
        field_name="matrix.excludes",
    )

    rtnval = MatrixSpec(
        dimensions=dimensions,
        includes=includes,
        excludes=excludes,
    )
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/pipelines
# ---------------------------------------------------------------------------


def handle_list_pipelines(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pipelines``

        Query params: ``page``, ``per_page``.

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
            permission_key=PIPELINES_READ_PERMISSION_KEY,
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

        all_views = definition_service.list_definitions(
            db_session=db_session,
            project_id=project_id,
            limit=MAX_PAGE_SIZE,
        )

        # One row per definition: the same document saved from another commit
        # or file is the same pipeline (its id is the document's digest), so it
        # is listed once with its newest source and the others named.
        collapsed = collapse_by_definition(views=all_views)

        total = len(collapsed)
        offset = (page - 1) * per_page
        window = collapsed[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for view, others in window:
            entry = _definition_view_to_dict(view=view)
            entry["other_sources"] = [
                {
                    "filename": other.filename,
                    "commit_sha": other.commit_sha,
                    "cached_at": _iso_or_none(other.cached_at),
                }
                for other in others
            ]
            items.append(entry)

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
# POST /api/v1/projects/{project_id}/pipelines
# ---------------------------------------------------------------------------


def handle_upsert_pipeline(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/pipelines``

        Parses, DAG-validates, canonicalizes, and caches a
        pipeline-definition document. The response carries the
        canonicalized definition; the ``pipeline_id`` is the
        canonical-document SHA-256 digest.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the upserted
                  :class:`PipelineDefinition`, or a problem
                  response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PIPELINES_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)
        decoded = _decode_definition_document(request=request, body=body)

        try:
            view = definition_service.upsert_definition(
                db_session=db_session,
                project_id=project_id,
                commit_sha=decoded["commit_sha"],
                filename=decoded["filename"],
                document_bytes=decoded["document_bytes"],
            )
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
            "pychestrate.pipelines.upsert project_id=%s pipeline_id=%s",
            project_id,
            view.pipeline_id,
        )

        body_dict = _definition_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/pipelines/{pipeline_id}
# ---------------------------------------------------------------------------


def handle_read_pipeline(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/pipelines/{pipeline_id}``

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the pipeline definition
                  or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    pipeline_id = request.path_params.get("pipeline_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PIPELINES_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            view = definition_service.get_definition(
                db_session=db_session,
                project_id=project_id,
                pipeline_id=pipeline_id,
            )
        except PipelineRunNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"pipeline_id": pipeline_id},
            )
            view = None  # unreachable

        body = _definition_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# DELETE /api/v1/projects/{project_id}/pipelines/{pipeline_id}
# ---------------------------------------------------------------------------


def handle_delete_pipeline(request: Request) -> Response:
    """
        ``DELETE /api/v1/projects/{project_id}/pipelines/{pipeline_id}``

        :param request: Incoming webworks request.

        :returns: Empty JSON response (204) or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    pipeline_id = request.path_params.get("pipeline_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PIPELINES_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        try:
            definition_service.delete_definition(
                db_session=db_session,
                project_id=project_id,
                pipeline_id=pipeline_id,
            )
        except PipelineRunNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=404,
                detail=str(xcpt),
                extensions={"pipeline_id": pipeline_id},
            )

        rtnval: Response = JSONResponse(content={}, status_code=204)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/pipelines:validate
# ---------------------------------------------------------------------------


def handle_validate_pipeline(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/pipelines:validate``

        Pure DAG validation of a supplied pipeline-definition
        document -- parse, cycle detection, and stage-reference
        checks. Writes no rows and emits no events. A document
        that fails validation returns ``422`` with the issue
        list; a well-formed document returns ``200``.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a
                  :class:`DagValidationResult`, or a problem
                  response (422 on an invalid document).
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PIPELINES_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)
        decoded = _decode_definition_document(request=request, body=body)

        view = definition_service.validate_document(
            document_bytes=decoded["document_bytes"],
            filename=decoded["filename"],
        )
        body_dict = _validation_view_to_dict(view=view)

        if view.valid is False:
            _abort_problem(
                request=request,
                status=422,
                detail="The pipeline is not valid.",
                extensions={
                    "reason": "dag_invalid",
                    "issues": list(view.issues),
                    "stage_count": int(view.stage_count),
                },
            )

        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/pipelines:expand-matrix
# ---------------------------------------------------------------------------


def handle_expand_matrix(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/pipelines:expand-matrix``

        Pure compute/preview surface: expands a supplied matrix
        spec into the concrete shard set the named sharding
        strategy would produce. Writes no rows, emits no events,
        and triggers nothing.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with a
                  :class:`ShardExpansion`, or a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=PIPELINES_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)
        matrix_spec = _decode_matrix_spec(request=request, body=body)

        strategy_name = body.get("strategy_name", DEFAULT_STRATEGY_NAME)
        if not isinstance(strategy_name, str) or len(strategy_name) == 0:
            strategy_name = DEFAULT_STRATEGY_NAME

        try:
            view = sharding_service.preview_expansion(
                matrix_spec=matrix_spec,
                strategy_name=strategy_name,
            )
        except ShardingStrategyNotFoundError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"strategy_name": strategy_name},
            )
            view = None  # unreachable
        except MatrixSpecInvalidError as xcpt:
            _abort_problem(
                request=request,
                status=422,
                detail=str(xcpt),
                extensions={"reason": "matrix_spec_invalid"},
            )
            view = None  # unreachable

        body_dict = _expansion_preview_to_dict(view=view)
        rtnval: Response = JSONResponse(content=body_dict, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_pipeline_definitions_routes(
        *,
        app: Any,
        version_prefix: str
    ) -> None:
    """
        Attach the pipeline-definition + matrix-sharding REST
        routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + PIPELINES_PATH_SUFFIX, methods=["GET"],
    )(handle_list_pipelines)
    app.attach_route(
        base + PIPELINES_PATH_SUFFIX, methods=["POST"],
    )(handle_upsert_pipeline)
    app.attach_route(
        base + PIPELINES_PATH_SUFFIX + "/{pipeline_id}", methods=["GET"],
    )(handle_read_pipeline)
    app.attach_route(
        base + PIPELINES_PATH_SUFFIX + "/{pipeline_id}", methods=["DELETE"],
    )(handle_delete_pipeline)
    app.attach_route(
        base + PIPELINES_VALIDATE_PATH_SUFFIX,
        methods=["POST"],
    )(handle_validate_pipeline)
    app.attach_route(
        base + PIPELINES_EXPAND_MATRIX_PATH_SUFFIX,
        methods=["POST"],
    )(handle_expand_matrix)

    _LOGGER.warning(
        "pychestrate.pipelines.routes.dispatch_not_wired: this PR exposes"
        " pipeline-definition CRUD + DAG validation + matrix-expand preview"
        " only. Pipeline-execution dispatch (triggering a run) is M2 work"
        " (orchestration.pipelines.definition.service.trigger_run) and is"
        " intentionally not exposed over REST."
    )
    return


__all__ = [
    "PIPELINES_PATH_SUFFIX",
    "PIPELINES_READ_PERMISSION_KEY",
    "PIPELINES_WRITE_PERMISSION_KEY",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_pipeline_definitions_routes",
    "collapse_by_definition",
    "handle_list_pipelines",
    "handle_upsert_pipeline",
    "handle_read_pipeline",
    "handle_delete_pipeline",
    "handle_validate_pipeline",
    "handle_expand_matrix",
]
