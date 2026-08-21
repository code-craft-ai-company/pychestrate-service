"""
.. module:: orchestration.test.restapi.v1.test_catalog_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for the test_catalog tag.

.. moduleauthor:: Code Craft AI LLC

Implements the three planned ``test_catalog`` operations from
``specs/openapi/pychestrate.yaml``:

* ``GET  /api/v1/projects/{project_id}/test-catalog``
* ``POST /api/v1/projects/{project_id}/test-catalog``
* ``POST /api/v1/projects/{project_id}/test-catalog:import``

Each handler follows the shape of
``webservice.runs.restapi.v1.runs_routes``: cookie-or-api-key
session validation, RBAC permission check, JSON body decode, then
delegation to the in-tree catalog facade
(``orchestration.test.catalog.catalog``) or the testbase
importer factory (``orchestration.test.catalog.factories``).

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

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.orchestration.test.catalog import catalog
from ccai.pychestrate.webservice.orchestration.test.catalog.payloads import (
    ImporterEntryPayload,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


TEST_CATALOG_PATH_SUFFIX = "/test-catalog"
TEST_CATALOG_IMPORT_PATH_SUFFIX = "/test-catalog:import"
PROJECTS_PATH_PREFIX = "/projects"

TEST_CATALOG_READ_PERMISSION_KEY = "system:test_catalog.read"
TEST_CATALOG_WRITE_PERMISSION_KEY = "system:test_catalog.write"

TEST_CATALOG_IMPORTER_PROTOCOL = "test_catalog_importer"

DEFAULT_PAGE_SIZE = 50
MIN_PAGE_SIZE = 1
MAX_PAGE_SIZE = 500

_LOGGER = logging.getLogger("pychestrate.test_catalog.routes")


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
    ) -> None:
    """
        Require the calling principal to hold ``permission_key``.

        :param request: Incoming webworks request.
        :param db_session: Active SQLAlchemy session.
        :param permission_key: Required ``system:*`` permission key.

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
    return


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


def _require_project_exists(*, request: Request, db_session: Any, project_id: str) -> Any:
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


def _parse_optional_bool(
        *,
        raw: Optional[str],
        default: bool
    ) -> bool:
    """
        Decode a query-string flag into a boolean.

        :param raw: Raw query value or None.
        :param default: Fallback when missing.

        :returns: Boolean value.
    """
    if raw is None or len(raw) == 0:
        rtnval = default
        return rtnval
    normalized = raw.strip().lower()
    truthy = {"true", "1", "yes", "y", "on"}
    rtnval = normalized in truthy
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


def _entry_view_to_dict(view: Any) -> Dict[str, Any]:
    """
        Serialize a :class:`TestCatalogEntryView` to the OpenAPI
        ``TestCatalogEntry`` schema.

        :param view: Read-model returned by the catalog facade.

        :returns: JSON-friendly dict.
    """
    # ``created_at`` is the first-import timestamp and stays
    # stable across re-imports; ``updated_at`` moves on every
    # upsert. Older view snapshots may predate the created_at
    # field, so fall back to updated_at rather than emitting
    # null.
    updated_at_iso = _iso_or_none(getattr(view, "updated_at", None))
    created_at_raw = getattr(view, "created_at", None)
    if created_at_raw is not None:
        created_at_iso = _iso_or_none(created_at_raw)
    else:
        created_at_iso = updated_at_iso
    rtnval: Dict[str, Any] = {
        "entry_id": str(view.entry_id),
        "project_id": str(view.project_id),
        "importer_tag": view.importer_tag,
        "entry_key": view.entry_key,
        "display_name": view.display_name,
        "description": view.description if view.description is not None else "",
        "required_capability_tags": list(view.required_capability_tags or ()),
        "param_schema": dict(view.param_schema or {}),
        "raw_metadata": dict(view.raw_metadata or {}),
        "canonical_digest": view.canonical_digest,
        "retired": bool(view.retired),
        "created_at": created_at_iso,
        "updated_at": updated_at_iso,
    }
    return rtnval


# ---------------------------------------------------------------------------
# GET /api/v1/projects/{project_id}/test-catalog
# ---------------------------------------------------------------------------


def handle_list_test_catalog(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/test-catalog``

        Query params: ``importer_tag``, ``include_retired``,
        ``page``, ``per_page``.

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
            permission_key=TEST_CATALOG_READ_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        importer_tag = request.query_params.get("importer_tag", None)
        include_retired_raw = request.query_params.get("include_retired", None)
        include_retired = _parse_optional_bool(
            raw=include_retired_raw,
            default=False,
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

        normalized_tag: Optional[str] = None
        if importer_tag is not None and len(importer_tag) > 0:
            normalized_tag = importer_tag

        all_views = catalog.list_entries(
            db_session=db_session,
            project_id=project_id,
            include_retired=include_retired,
            importer_tag=normalized_tag,
        )
        total = len(all_views)
        offset = (page - 1) * per_page
        window = all_views[offset:offset + per_page]

        items: List[Dict[str, Any]] = []
        for view in window:
            items.append(_entry_view_to_dict(view=view))

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
# POST /api/v1/projects/{project_id}/test-catalog
# ---------------------------------------------------------------------------


def _build_importer_payload(
        *,
        request: Request,
        payload: Dict[str, Any]
    ) -> ImporterEntryPayload:
    """
        Validate the upsert body and build an
        :class:`ImporterEntryPayload`.

        :param request: Incoming webworks request.
        :param payload: Decoded JSON object body.

        :returns: ImporterEntryPayload instance.
    """
    entry_key = payload.get("entry_key", None)
    display_name = payload.get("display_name", None)

    missing_fields: List[str] = []
    if not isinstance(entry_key, str) or len(entry_key) == 0:
        missing_fields.append("entry_key")
    if not isinstance(display_name, str) or len(display_name) == 0:
        missing_fields.append("display_name")
    if len(missing_fields) > 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Missing required field(s): {}".format(
                ", ".join(missing_fields),
            ),
            extensions={"missing_fields": missing_fields},
        )

    description = payload.get("description", "")
    if isinstance(description, str) is False:
        description = ""

    tags_raw = payload.get("required_capability_tags", [])
    if isinstance(tags_raw, list) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'required_capability_tags' must be an array.",
        )
    tags = tuple(str(item) for item in tags_raw)

    param_schema = payload.get("param_schema", {})
    if isinstance(param_schema, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'param_schema' must be an object.",
        )

    raw_metadata = payload.get("raw_metadata", {})
    if isinstance(raw_metadata, dict) is False:
        _abort_problem(
            request=request,
            status=422,
            detail="Field 'raw_metadata' must be an object.",
        )

    rtnval = ImporterEntryPayload(
        entry_key=entry_key,
        display_name=display_name,
        description=description,
        required_capability_tags=tags,
        param_schema=dict(param_schema),
        raw_metadata=dict(raw_metadata),
    )
    return rtnval


def handle_upsert_test_catalog(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/test-catalog``

        Delegates to
        :func:`orchestration.test.catalog.catalog.upsert_entry`.

        :param request: Incoming webworks request.

        :returns: JSON response (200) with the upserted entry, or
                  a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=TEST_CATALOG_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)

        importer_tag = body.get("importer_tag", None)
        if not isinstance(importer_tag, str) or len(importer_tag) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'importer_tag' is required.",
                extensions={"missing_fields": ["importer_tag"]},
            )

        importer_payload = _build_importer_payload(
            request=request,
            payload=body,
        )

        view = catalog.upsert_entry(
            db_session=db_session,
            project_id=project_id,
            importer_tag=importer_tag,
            payload=importer_payload,
        )

        _LOGGER.info(
            "pychestrate.test_catalog.upsert project_id=%s entry_key=%s importer_tag=%s",
            project_id,
            importer_payload.entry_key,
            importer_tag,
        )

        response_body = _entry_view_to_dict(view=view)
        rtnval: Response = JSONResponse(content=response_body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# POST /api/v1/projects/{project_id}/test-catalog:import
# ---------------------------------------------------------------------------


def _resolve_importer(*, request: Request, importer_tag: str) -> Any:
    """
        Resolve a registered ``test_catalog_importer`` factory by
        tag, aborting 404 when no implementation matches.

        :param request: Incoming webworks request.
        :param importer_tag: Importer tag from the request body.

        :returns: Importer class.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=TEST_CATALOG_IMPORTER_PROTOCOL,
    )
    for impl in candidates:
        try:
            if impl.importer_tag() == importer_tag:
                rtnval = impl
                return rtnval
        except NotImplementedError:
            continue
    _abort_problem(
        request=request,
        status=404,
        detail="No test_catalog_importer registered for tag.",
        extensions={
            "importer_tag": importer_tag,
            "registered_count": len(candidates),
        },
    )
    rtnval = None  # unreachable
    return rtnval


def handle_import_test_catalog(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/test-catalog:import``

        Resolves the importer factory by ``importer_tag``, runs it
        synchronously against the supplied ``source`` descriptor,
        and upserts each returned :class:`ImporterEntryPayload`.

        :param request: Incoming webworks request.

        :returns: JSON response (202) with a
                  :class:`TestCatalogImportSummary`-shaped body, or
                  a problem response.
    """
    project_id = request.path_params.get("project_id", "")
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request,
            db_session=db_session,
            permission_key=TEST_CATALOG_WRITE_PERMISSION_KEY,
        )
        _require_project_exists(
            request=request,
            db_session=db_session,
            project_id=project_id,
        )

        body = _decode_json_object_or_abort(request=request)
        importer_tag = body.get("importer_tag", None)
        if not isinstance(importer_tag, str) or len(importer_tag) == 0:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'importer_tag' is required.",
                extensions={"missing_fields": ["importer_tag"]},
            )

        source = body.get("source", {})
        if isinstance(source, dict) is False:
            _abort_problem(
                request=request,
                status=422,
                detail="Field 'source' must be an object.",
            )

        importer = _resolve_importer(
            request=request,
            importer_tag=importer_tag,
        )

        started_at = datetime.now(timezone.utc)
        errors: List[str] = []
        entries_imported = 0

        try:
            payloads = importer.import_entries(
                project_id=project_id,
                source=source,
            )
        except Exception as xcpt:
            _LOGGER.warning(
                "pychestrate.test_catalog.import.factory_failure project_id=%s tag=%s err=%s",
                project_id,
                importer_tag,
                xcpt,
            )
            _abort_problem(
                request=request,
                status=422,
                detail="Importer raised: {}".format(str(xcpt)),
                extensions={"importer_tag": importer_tag},
            )
            payloads = []  # unreachable

        for payload in payloads:
            try:
                catalog.upsert_entry(
                    db_session=db_session,
                    project_id=project_id,
                    importer_tag=importer_tag,
                    payload=payload,
                )
                entries_imported += 1
            except Exception as xcpt:
                errors.append("{}: {}".format(payload.entry_key, str(xcpt)))

        summary_body: Dict[str, Any] = {
            "importer_tag": importer_tag,
            "started_at": started_at.isoformat(),
            "entries_imported": entries_imported,
            "entries_retired": 0,
            "errors": errors,
        }

        _LOGGER.info(
            "pychestrate.test_catalog.import project_id=%s tag=%s imported=%d errors=%d",
            project_id,
            importer_tag,
            entries_imported,
            len(errors),
        )

        rtnval: Response = JSONResponse(content=summary_body, status_code=202)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_test_catalog_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the test-catalog REST routes to a webworks app.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.
        :param version_prefix: Versioned API prefix (e.g.
                               ``"/api/v1"``).

        :returns: None.
    """
    base = version_prefix + PROJECTS_PATH_PREFIX + "/{project_id}"
    app.attach_route(
        base + TEST_CATALOG_PATH_SUFFIX, methods=["GET"],
    )(handle_list_test_catalog)
    app.attach_route(
        base + TEST_CATALOG_PATH_SUFFIX, methods=["POST"],
    )(handle_upsert_test_catalog)
    app.attach_route(
        base + TEST_CATALOG_IMPORT_PATH_SUFFIX, methods=["POST"],
    )(handle_import_test_catalog)
    return


__all__ = [
    "TEST_CATALOG_PATH_SUFFIX",
    "TEST_CATALOG_IMPORT_PATH_SUFFIX",
    "TEST_CATALOG_READ_PERMISSION_KEY",
    "TEST_CATALOG_WRITE_PERMISSION_KEY",
    "TEST_CATALOG_IMPORTER_PROTOCOL",
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "register_test_catalog_routes",
    "handle_list_test_catalog",
    "handle_upsert_test_catalog",
    "handle_import_test_catalog",
]
