"""
.. module:: orchestration.rpa.restapi.v1.rpa_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks REST routes for 6-rpa-orchestration.

.. moduleauthor:: Code Craft AI LLC

Job type registry (system scope)::

    GET    /api/v1/rpa/job-types
    POST   /api/v1/rpa/job-types
    GET    /api/v1/rpa/job-types/{type_id}
    PATCH  /api/v1/rpa/job-types/{type_id}
    POST   /api/v1/rpa/job-types/{type_id}/retire
    POST   /api/v1/rpa/job-types/{type_id}/versions
    POST   /api/v1/rpa/job-types/{type_id}/versions/{version}/deprecate
    POST   /api/v1/rpa/job-types/{type_id}/versions/{version}/retire
    GET    /api/v1/rpa/execution-modes

Specifications and jobs (project scope)::

    GET    /api/v1/projects/{project_id}/rpa/specs
    POST   /api/v1/projects/{project_id}/rpa/specs
    GET    /api/v1/projects/{project_id}/rpa/specs/{spec_id}
    PATCH  /api/v1/projects/{project_id}/rpa/specs/{spec_id}
    DELETE /api/v1/projects/{project_id}/rpa/specs/{spec_id}
    POST   /api/v1/projects/{project_id}/rpa/specs/{spec_id}/trigger
    GET    /api/v1/projects/{project_id}/rpa/jobs
    GET    /api/v1/projects/{project_id}/rpa/jobs/{job_id}
    GET    /api/v1/projects/{project_id}/rpa/jobs/{job_id}/logs
    POST   /api/v1/projects/{project_id}/rpa/jobs/{job_id}/cancel

Errors follow the RFC 7807 problem-document contract; packet
validation failures return 422 with an ``errors`` extension listing
``{path, message}`` per failing JSON pointer.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging
import uuid

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import JSONResponse, Response

from ccai.pychestrate.webservice.api.problem_json_webworks import (
    problem_response_for_http_status,
)
from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
from ccai.pychestrate.webservice.orchestration.rpa.packet import (
    redact_packet,
    restore_redacted_secrets,
)
from ccai.pychestrate.webservice.orchestration.rpa.candidates import (
    resolve_dispatch_candidates,
)
from ccai.pychestrate.webservice.orchestration.rpa.errors import (
    CapabilityMismatchError,
    DuplicateRpaJobTypeError,
    DuplicateRpaSpecError,
    DuplicateVersionError,
    PacketTooLargeError,
    PacketValidationError,
    RpaDispatchFailedError,
    RpaDispatchUnavailableError,
    RpaJobNotCancellableError,
    RpaJobNotFoundError,
    RpaJobTypeInvalidError,
    RpaJobTypeNotFoundError,
    RpaJobTypeRetiredError,
    RpaSecretReferenceError,
    RpaSpecInvalidError,
    RpaSpecNotFoundError,
    RpaVersionNotActiveError,
    RpaVersionNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.rpa.models import (
    RpaJobStatus,
    RpaJobTypeState,
    RpaVersionState,
)
from ccai.pychestrate.webservice.projects import repository as projects_repo
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


_LOGGER = logging.getLogger("pychestrate.rpa.routes")

RPA_READ_PERMISSION_KEY: str = "system:rpa.read"
RPA_CREATE_PERMISSION_KEY: str = "system:rpa.create"
RPA_JOB_TYPES_MANAGE_PERMISSION_KEY: str = "system:rpa.job_types.manage"

DEFAULT_PAGE_SIZE: int = 50
MAX_PAGE_SIZE: int = 200


# ---------------------------------------------------------------------------
# Problem-flow plumbing (mirrors build_runs_routes)
# ---------------------------------------------------------------------------


class _ProblemAbort(Exception):
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
    response = problem_response_for_http_status(
        status=status,
        detail=detail,
        instance=request.path,
        extensions=extensions,
    )
    raise _ProblemAbort(response)


def _require_session(request: Request) -> Any:
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        _abort_problem(
            request=request,
            status=503,
            detail="Request-scoped db_session not configured",
        )
    rtnval = db_session
    return rtnval


def _require_permission(*, request: Request, db_session: Any, permission_key: str) -> Any:
    principal = getattr(request, "auth_principal", None)
    if principal is None:
        _abort_problem(request=request, status=401, detail="Authentication required.")
    decision = rbac_evaluator.check_permission(
        db_session=db_session,
        principal=principal,
        permission_key=permission_key,
        now=datetime.now(timezone.utc),
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


def _actor_id(principal: Any) -> Optional[str]:
    user_id = getattr(principal, "user_id", None)
    rtnval = str(user_id) if user_id is not None else None
    return rtnval


def _decode_json_object_or_abort(*, request: Request) -> Dict[str, Any]:
    raw = getattr(request, "body", b"")
    if callable(raw):
        raw = raw()
    if raw is None or len(raw) == 0:
        rtnval: Dict[str, Any] = {}
        return rtnval
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        decoded = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as xcpt:
        _abort_problem(
            request=request,
            status=400,
            detail="Request body is not valid JSON: {}".format(str(xcpt)),
        )
        decoded = None  # unreachable
    if not isinstance(decoded, dict):
        _abort_problem(request=request, status=400, detail="Request body must be a JSON object.")
    rtnval = decoded
    return rtnval


#: Body fields each write endpoint reads. Anything else is refused (422)
#: so a misspelled field (``timeout_seconds`` for ``timeout_minutes``)
#: fails loudly instead of being silently ignored.
JOB_TYPE_CREATE_FIELDS = (
    "type_id", "display_name", "description", "execution_mode",
    "capability_requirements", "packet_schema", "secret_fields",
)
JOB_TYPE_UPDATE_FIELDS = (
    "display_name", "description", "capability_requirements", "packet_schema", "secret_fields",
)
VERSION_PUBLISH_FIELDS = (
    "version", "source", "source_kind", "source_ref", "entrypoint", "environment", "timeout_minutes",
)
SPEC_FIELDS = (
    "name", "type_id", "version_selector", "default_packet", "target_pod_id",
    "required_capabilities", "timeout_minutes", "description",
)
TRIGGER_FIELDS = ("work_packet", "idempotency_key", "allow_duplicate")


def _reject_unknown_fields(*, request: Request, body: Dict[str, Any], allowed: Iterable[str]) -> None:
    """
        Abort with a 422 problem naming every body field the endpoint
        does not read.

        :param request: The request (for the problem ``instance``).
        :param body: Decoded JSON object body.
        :param allowed: Field names the endpoint reads.
    """
    allowed_set = set(allowed)
    unknown = sorted(key for key in body if key not in allowed_set)
    if len(unknown) > 0:
        _abort_problem(
            request=request,
            status=422,
            detail="Unknown field(s): {}. This endpoint accepts: {}.".format(
                ", ".join(unknown), ", ".join(sorted(allowed_set)),
            ),
            extensions={"unknown_fields": unknown},
        )
    return


def _is_uuid(value: Any) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _require_project_exists(*, request: Request, db_session: Any, project_id: str) -> Any:
    """
        Resolve a project by UUID (orchestration project) or by
        integer id (consumer-UI project). Aborts 404 when neither
        table knows it.
    """
    row: Any = None
    if _is_uuid(project_id):
        row = projects_repo.get_project_by_id(db_session=db_session, project_id=project_id)
    else:
        try:
            numeric = int(str(project_id))
        except ValueError:
            numeric = None
        if numeric is not None:
            try:
                from ccai.pychestrate.core.orm import Project as CoreProject  # noqa: E402
                row = db_session.query(CoreProject).filter(CoreProject.id == numeric).first()
            except Exception:
                row = None
    if row is None:
        _abort_problem(
            request=request,
            status=404,
            detail="Project not found.",
            extensions={"project_id": project_id},
        )
    rtnval = row
    return rtnval


def _parse_positive_int(*, request: Request, name: str, default: int, maximum: Optional[int] = None) -> int:
    raw = request.query_params.get(name, None)
    if raw is None or len(str(raw)) == 0:
        return default
    try:
        value = int(str(raw))
    except ValueError:
        _abort_problem(request=request, status=400, detail="'{}' must be an integer.".format(name))
        value = default
    if value < 0:
        _abort_problem(request=request, status=400, detail="'{}' must not be negative.".format(name))
    if maximum is not None and value > maximum:
        value = maximum
    rtnval = value
    return rtnval


def _iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        rtnval = value.isoformat()
        return rtnval
    rtnval = str(value)
    return rtnval


def _enum_value(value: Any) -> Any:
    rtnval = getattr(value, "value", value)
    return rtnval


# ---------------------------------------------------------------------------
# View serialisers
# ---------------------------------------------------------------------------


def _version_to_dict(view: Any) -> Dict[str, Any]:
    rtnval = {
        "version_id": view.version_id,
        "type_id": view.type_id,
        "version": view.version,
        "source": {"kind": view.source_kind, "ref": view.source_ref},
        "entrypoint": dict(view.entrypoint),
        "environment": dict(view.environment),
        "timeout_minutes": view.timeout_minutes,
        "state": _enum_value(view.state),
        "published_by_id": view.published_by_id,
        "published_at": _iso_or_none(view.published_at),
    }
    return rtnval


def _job_type_to_dict(view: Any) -> Dict[str, Any]:
    rtnval = {
        "type_id": view.type_id,
        "display_name": view.display_name,
        "description": view.description,
        "execution_mode": _enum_value(view.execution_mode),
        "capability_requirements": list(view.capability_requirements),
        "packet_schema": dict(view.packet_schema) if view.packet_schema else None,
        "secret_fields": list(view.secret_fields),
        "state": _enum_value(view.state),
        "created_by_id": view.created_by_id,
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
        "active_version_count": view.active_version_count,
        "latest_active_version": view.latest_active_version,
        "versions": [_version_to_dict(v) for v in view.versions],
    }
    return rtnval


def _spec_to_dict(view: Any) -> Dict[str, Any]:
    rtnval = {
        "spec_id": view.spec_id,
        "project_id": view.project_id,
        "name": view.name,
        "type_id": view.type_id,
        "type_display_name": view.type_display_name,
        "execution_mode": _enum_value(view.execution_mode),
        "version_selector": view.version_selector,
        "resolved_version": view.resolved_version,
        # Secret-declared packet paths are never returned.
        "default_packet": redact_packet(
            packet=dict(view.default_packet), secret_fields=list(view.secret_fields)
        ),
        # Declared secret paths whose stored default is a plain value, not a {"$secret": "<vault ref>"} reference.
        "inline_secret_fields": list(view.inline_secret_fields),
        "packet_schema": dict(view.packet_schema) if view.packet_schema else None,
        "target_pod_id": view.target_pod_id,
        "required_capabilities": list(view.required_capabilities),
        "timeout_minutes": view.timeout_minutes,
        "description": view.description,
        "revision": view.revision,
        "created_by_id": view.created_by_id,
        "created_at": _iso_or_none(view.created_at),
        "updated_at": _iso_or_none(view.updated_at),
    }
    return rtnval


def _job_to_dict(view: Any) -> Dict[str, Any]:
    rtnval = {
        "job_id": view.job_id,
        "project_id": view.project_id,
        "spec_id": view.spec_id,
        "spec_name": view.spec_name,
        "spec_revision": view.spec_revision,
        "type_id": view.type_id,
        "resolved_version": view.resolved_version,
        "execution_mode": _enum_value(view.execution_mode),
        "work_packet": dict(view.work_packet),
        "packet_digest": view.packet_digest,
        "status": _enum_value(view.status),
        "run_state": view.run_state,
        "exit_code": view.exit_code,
        "dispatch_attempt_id": view.dispatch_attempt_id,
        "envelope_id": view.envelope_id,
        "client_id": view.client_id,
        "pod_id": view.pod_id,
        "triggered_by_id": view.triggered_by_id,
        "trigger_cause": dict(view.trigger_cause),
        "result_root_key": view.result_root_key,
        "final_state_reason": view.final_state_reason,
        "created_at": _iso_or_none(view.created_at),
        "started_at": _iso_or_none(view.started_at),
        "completed_at": _iso_or_none(view.completed_at),
        "duration_seconds": view.duration_seconds,
        "replayed": bool(getattr(view, "replayed", False)),
    }
    return rtnval


# ---------------------------------------------------------------------------
# Job type registry
# ---------------------------------------------------------------------------


def handle_list_execution_modes(request: Request) -> Response:
    """
        ``GET /api/v1/rpa/execution-modes``
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
        modes = []
        for impl in rpa_service.list_execution_modes():
            modes.append({
                "execution_mode": impl.execution_mode(),
                "description": impl.describe(),
                "implementation": "{}.{}".format(impl.__module__, impl.__name__),
            })
        rtnval: Response = JSONResponse(content={"execution_modes": modes}, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_list_job_types(request: Request) -> Response:
    """
        ``GET /api/v1/rpa/job-types``
    """
    try:
        db_session = _require_session(request=request)
        _require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
        state_raw = request.query_params.get("state", None)
        state: Optional[RpaJobTypeState] = None
        if state_raw:
            try:
                state = RpaJobTypeState(str(state_raw))
            except ValueError:
                _abort_problem(request=request, status=400, detail="Unknown job type state filter.")
        views = rpa_service.list_job_types(db_session=db_session, state=state)
        body = {"job_types": [_job_type_to_dict(v) for v in views], "total": len(views)}
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_create_job_type(request: Request) -> Response:
    """
        ``POST /api/v1/rpa/job-types``
    """
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request, db_session=db_session, permission_key=RPA_JOB_TYPES_MANAGE_PERMISSION_KEY,
        )
        body = _decode_json_object_or_abort(request=request)
        _reject_unknown_fields(request=request, body=body, allowed=JOB_TYPE_CREATE_FIELDS)
        inputs = rpa_service.RpaJobTypeInputs(
            type_id=str(body.get("type_id", "")).strip(),
            display_name=str(body.get("display_name", "")),
            description=str(body.get("description", "") or ""),
            execution_mode=str(body.get("execution_mode", "process") or "process"),
            capability_requirements=tuple(body.get("capability_requirements", []) or []),
            packet_schema=body.get("packet_schema", None),
            secret_fields=tuple(body.get("secret_fields", []) or []),
        )
        try:
            view = rpa_service.register_job_type(
                db_session=db_session, inputs=inputs, actor_id=_actor_id(principal),
            )
        except DuplicateRpaJobTypeError as xcpt:
            _abort_problem(request=request, status=409, detail=str(xcpt), extensions={"type_id": inputs.type_id})
            view = None
        except RpaJobTypeInvalidError as xcpt:
            _abort_problem(request=request, status=422, detail=str(xcpt), extensions={"type_id": inputs.type_id})
            view = None
        rtnval: Response = JSONResponse(content=_job_type_to_dict(view), status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_read_job_type(request: Request) -> Response:
    """
        ``GET /api/v1/rpa/job-types/{type_id}``
    """
    type_id = str(request.path_params.get("type_id", ""))
    try:
        db_session = _require_session(request=request)
        _require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
        try:
            view = rpa_service.get_job_type(db_session=db_session, type_id=type_id)
        except RpaJobTypeNotFoundError as xcpt:
            _abort_problem(request=request, status=404, detail=str(xcpt), extensions={"type_id": type_id})
            view = None
        rtnval: Response = JSONResponse(content=_job_type_to_dict(view), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_update_job_type(request: Request) -> Response:
    """
        ``PATCH /api/v1/rpa/job-types/{type_id}``
    """
    type_id = str(request.path_params.get("type_id", ""))
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request, db_session=db_session, permission_key=RPA_JOB_TYPES_MANAGE_PERMISSION_KEY,
        )
        body = _decode_json_object_or_abort(request=request)
        _reject_unknown_fields(request=request, body=body, allowed=JOB_TYPE_UPDATE_FIELDS)
        kwargs: Dict[str, Any] = {}
        if "display_name" in body:
            kwargs["display_name"] = body["display_name"]
        if "description" in body:
            kwargs["description"] = body["description"]
        if "capability_requirements" in body:
            kwargs["capability_requirements"] = body["capability_requirements"]
        if "secret_fields" in body:
            kwargs["secret_fields"] = body["secret_fields"]
        if "packet_schema" in body:
            kwargs["packet_schema"] = body["packet_schema"]
        try:
            principal = getattr(request, "auth_principal", None)
            view = rpa_service.update_job_type(
                db_session=db_session, type_id=type_id, actor_id=_actor_id(principal), **kwargs,
            )
        except RpaJobTypeNotFoundError as xcpt:
            _abort_problem(request=request, status=404, detail=str(xcpt), extensions={"type_id": type_id})
            view = None
        except RpaJobTypeInvalidError as xcpt:
            _abort_problem(request=request, status=422, detail=str(xcpt), extensions={"type_id": type_id})
            view = None
        rtnval: Response = JSONResponse(content=_job_type_to_dict(view), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_retire_job_type(request: Request) -> Response:
    """
        ``POST /api/v1/rpa/job-types/{type_id}/retire``
    """
    type_id = str(request.path_params.get("type_id", ""))
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request, db_session=db_session, permission_key=RPA_JOB_TYPES_MANAGE_PERMISSION_KEY,
        )
        try:
            view = rpa_service.retire_job_type(
                db_session=db_session, type_id=type_id, actor_id=_actor_id(principal),
            )
        except RpaJobTypeNotFoundError as xcpt:
            _abort_problem(request=request, status=404, detail=str(xcpt), extensions={"type_id": type_id})
            view = None
        rtnval: Response = JSONResponse(content=_job_type_to_dict(view), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_publish_version(request: Request) -> Response:
    """
        ``POST /api/v1/rpa/job-types/{type_id}/versions``
    """
    type_id = str(request.path_params.get("type_id", ""))
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request, db_session=db_session, permission_key=RPA_JOB_TYPES_MANAGE_PERMISSION_KEY,
        )
        body = _decode_json_object_or_abort(request=request)
        _reject_unknown_fields(request=request, body=body, allowed=VERSION_PUBLISH_FIELDS)
        source = body.get("source", None)
        source_kind = body.get("source_kind", None)
        source_ref = body.get("source_ref", None)
        if isinstance(source, dict):
            source_kind = source.get("kind", source_kind)
            source_ref = source.get("ref", source_ref)
        entrypoint = body.get("entrypoint", {})
        if not isinstance(entrypoint, dict):
            _abort_problem(request=request, status=422, detail="'entrypoint' must be a JSON object.")
        environment = body.get("environment", {}) or {}
        if not isinstance(environment, dict):
            _abort_problem(request=request, status=422, detail="'environment' must be a JSON object.")
        try:
            timeout_minutes = int(body.get("timeout_minutes", 60) or 60)
        except (TypeError, ValueError):
            _abort_problem(request=request, status=422, detail="'timeout_minutes' must be an integer.")
            timeout_minutes = 60
        inputs = rpa_service.RpaVersionInputs(
            version=str(body.get("version", "")),
            source_kind=str(source_kind or "git"),
            source_ref=str(source_ref or ""),
            entrypoint=entrypoint,
            environment=environment,
            timeout_minutes=timeout_minutes,
        )
        try:
            view = rpa_service.publish_version(
                db_session=db_session, type_id=type_id, inputs=inputs, actor_id=_actor_id(principal),
            )
        except RpaJobTypeNotFoundError as xcpt:
            _abort_problem(request=request, status=404, detail=str(xcpt), extensions={"type_id": type_id})
            view = None
        except RpaJobTypeRetiredError as xcpt:
            _abort_problem(request=request, status=409, detail=str(xcpt), extensions={"type_id": type_id})
            view = None
        except DuplicateVersionError as xcpt:
            _abort_problem(
                request=request, status=409, detail=str(xcpt),
                extensions={"type_id": type_id, "version": inputs.version},
            )
            view = None
        except RpaJobTypeInvalidError as xcpt:
            _abort_problem(request=request, status=422, detail=str(xcpt), extensions={"type_id": type_id})
            view = None
        rtnval: Response = JSONResponse(content=_version_to_dict(view), status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def _handle_version_state(request: Request, *, state: RpaVersionState) -> Response:
    type_id = str(request.path_params.get("type_id", ""))
    version = str(request.path_params.get("version", ""))
    try:
        db_session = _require_session(request=request)
        _require_permission(
            request=request, db_session=db_session, permission_key=RPA_JOB_TYPES_MANAGE_PERMISSION_KEY,
        )
        try:
            view = rpa_service.set_version_state(
                db_session=db_session, type_id=type_id, version=version, state=state,
            )
        except RpaVersionNotFoundError as xcpt:
            _abort_problem(
                request=request, status=404, detail=str(xcpt),
                extensions={"type_id": type_id, "version": version},
            )
            view = None
        rtnval: Response = JSONResponse(content=_version_to_dict(view), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_deprecate_version(request: Request) -> Response:
    """
        ``POST /api/v1/rpa/job-types/{type_id}/versions/{version}/deprecate``
    """
    rtnval = _handle_version_state(request, state=RpaVersionState.DEPRECATED)
    return rtnval


def handle_retire_version(request: Request) -> Response:
    """
        ``POST /api/v1/rpa/job-types/{type_id}/versions/{version}/retire``
    """
    rtnval = _handle_version_state(request, state=RpaVersionState.RETIRED)
    return rtnval


# ---------------------------------------------------------------------------
# Specifications
# ---------------------------------------------------------------------------


def _spec_inputs_from_body(*, request: Request, body: Dict[str, Any]) -> rpa_service.RpaSpecInputs:
    default_packet = body.get("default_packet", {}) or {}
    if not isinstance(default_packet, dict):
        _abort_problem(request=request, status=422, detail="'default_packet' must be a JSON object.")
    timeout_minutes = body.get("timeout_minutes", None)
    if timeout_minutes is not None:
        try:
            timeout_minutes = int(timeout_minutes)
        except (TypeError, ValueError):
            _abort_problem(request=request, status=422, detail="'timeout_minutes' must be an integer.")
    rtnval = rpa_service.RpaSpecInputs(
        name=str(body.get("name", "")),
        type_id=str(body.get("type_id", "")),
        version_selector=str(body.get("version_selector", "latest-active") or "latest-active"),
        default_packet=default_packet,
        target_pod_id=body.get("target_pod_id", None),
        required_capabilities=tuple(body.get("required_capabilities", []) or []),
        timeout_minutes=timeout_minutes,
        description=str(body.get("description", "") or ""),
    )
    return rtnval


def handle_list_specs(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/rpa/specs``
    """
    project_id = str(request.path_params.get("project_id", ""))
    try:
        db_session = _require_session(request=request)
        _require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
        _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        offset = _parse_positive_int(request=request, name="offset", default=0)
        limit = _parse_positive_int(request=request, name="limit", default=100, maximum=MAX_PAGE_SIZE)
        views, total = rpa_service.list_specs(
            db_session=db_session, project_id=project_id, offset=offset, limit=limit,
        )
        body = {
            "specs": [_spec_to_dict(v) for v in views],
            "total": total,
            "offset": offset,
            "limit": limit,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_create_spec(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/rpa/specs``
    """
    project_id = str(request.path_params.get("project_id", ""))
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request, db_session=db_session, permission_key=RPA_CREATE_PERMISSION_KEY,
        )
        _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        body = _decode_json_object_or_abort(request=request)
        _reject_unknown_fields(request=request, body=body, allowed=SPEC_FIELDS)
        inputs = _spec_inputs_from_body(request=request, body=body)
        try:
            view = rpa_service.create_spec(
                db_session=db_session, project_id=project_id, inputs=inputs,
                actor_id=_actor_id(principal), principal=principal,
            )
        except RpaSecretReferenceError as xcpt:
            _abort_for_trigger_error(request=request, xcpt=xcpt, spec_id="")
            view = None
        except DuplicateRpaSpecError as xcpt:
            _abort_problem(request=request, status=409, detail=str(xcpt), extensions={"name": inputs.name})
            view = None
        except RpaJobTypeNotFoundError as xcpt:
            _abort_problem(request=request, status=404, detail=str(xcpt), extensions={"type_id": inputs.type_id})
            view = None
        except (RpaSpecInvalidError, RpaVersionNotActiveError, RpaVersionNotFoundError,
                RpaJobTypeRetiredError) as xcpt:
            _abort_problem(request=request, status=422, detail=str(xcpt), extensions={"type_id": inputs.type_id})
            view = None
        rtnval: Response = JSONResponse(content=_spec_to_dict(view), status_code=201)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def _require_spec_in_project(*, request: Request, db_session: Any, project_id: str, spec_id: str) -> Any:
    try:
        view = rpa_service.get_spec(db_session=db_session, spec_id=spec_id)
    except RpaSpecNotFoundError as xcpt:
        _abort_problem(request=request, status=404, detail=str(xcpt), extensions={"spec_id": spec_id})
        view = None
    if view.project_id != project_id:
        _abort_problem(
            request=request, status=404, detail="RPA specification not found in this project.",
            extensions={"spec_id": spec_id, "project_id": project_id},
        )
    rtnval = view
    return rtnval


def handle_read_spec(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/rpa/specs/{spec_id}``
    """
    project_id = str(request.path_params.get("project_id", ""))
    spec_id = str(request.path_params.get("spec_id", ""))
    try:
        db_session = _require_session(request=request)
        _require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
        _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        view = _require_spec_in_project(
            request=request, db_session=db_session, project_id=project_id, spec_id=spec_id,
        )
        rtnval: Response = JSONResponse(content=_spec_to_dict(view), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_update_spec(request: Request) -> Response:
    """
        ``PATCH /api/v1/projects/{project_id}/rpa/specs/{spec_id}``
    """
    project_id = str(request.path_params.get("project_id", ""))
    spec_id = str(request.path_params.get("spec_id", ""))
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request, db_session=db_session, permission_key=RPA_CREATE_PERMISSION_KEY,
        )
        _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        current = _require_spec_in_project(
            request=request, db_session=db_session, project_id=project_id, spec_id=spec_id,
        )
        body = _decode_json_object_or_abort(request=request)
        _reject_unknown_fields(request=request, body=body, allowed=SPEC_FIELDS)
        merged: Dict[str, Any] = {
            "name": current.name,
            "type_id": current.type_id,
            "version_selector": current.version_selector,
            "default_packet": dict(current.default_packet),
            "target_pod_id": current.target_pod_id,
            "required_capabilities": list(current.required_capabilities),
            "timeout_minutes": current.timeout_minutes,
            "description": current.description,
        }
        merged.update(body)
        if isinstance(body.get("default_packet", None), dict):
            # A client that saves back a spec it read gets the redaction
            # marker at secret paths; keep the stored secret there.
            merged["default_packet"] = restore_redacted_secrets(
                incoming=body["default_packet"],
                stored=dict(current.default_packet),
                secret_fields=list(current.secret_fields),
            )
        inputs = _spec_inputs_from_body(request=request, body=merged)
        try:
            view = rpa_service.update_spec(
                db_session=db_session, spec_id=spec_id, inputs=inputs, actor_id=_actor_id(principal), principal=principal,
            )
        except RpaSecretReferenceError as xcpt:
            _abort_for_trigger_error(request=request, xcpt=xcpt, spec_id=spec_id)
            view = None
        except DuplicateRpaSpecError as xcpt:
            _abort_problem(request=request, status=409, detail=str(xcpt), extensions={"name": inputs.name})
            view = None
        except RpaJobTypeNotFoundError as xcpt:
            _abort_problem(request=request, status=404, detail=str(xcpt), extensions={"type_id": inputs.type_id})
            view = None
        except (RpaSpecInvalidError, RpaVersionNotActiveError, RpaVersionNotFoundError,
                RpaJobTypeRetiredError) as xcpt:
            _abort_problem(request=request, status=422, detail=str(xcpt), extensions={"spec_id": spec_id})
            view = None
        rtnval: Response = JSONResponse(content=_spec_to_dict(view), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_delete_spec(request: Request) -> Response:
    """
        ``DELETE /api/v1/projects/{project_id}/rpa/specs/{spec_id}``
    """
    project_id = str(request.path_params.get("project_id", ""))
    spec_id = str(request.path_params.get("spec_id", ""))
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request, db_session=db_session, permission_key=RPA_CREATE_PERMISSION_KEY,
        )
        _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        _require_spec_in_project(
            request=request, db_session=db_session, project_id=project_id, spec_id=spec_id,
        )
        try:
            rpa_service.delete_spec(db_session=db_session, spec_id=spec_id, actor_id=_actor_id(principal))
        except RpaSpecInvalidError as xcpt:
            _abort_problem(request=request, status=409, detail=str(xcpt), extensions={"spec_id": spec_id})
        rtnval: Response = JSONResponse(content={"deleted": True, "spec_id": spec_id}, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def _abort_for_trigger_error(*, request: Request, xcpt: Exception, spec_id: str) -> None:
    """
        Map a trigger-path error from :mod:`orchestration.rpa.service`
        onto its problem response and abort; other exceptions propagate.
    """
    if isinstance(xcpt, PacketValidationError):
        _abort_problem(
            request=request, status=422, detail=str(xcpt),
            extensions={"errors": [{"path": p, "message": m} for p, m in xcpt.issues]},
        )
    if isinstance(xcpt, PacketTooLargeError):
        _abort_problem(request=request, status=413, detail=str(xcpt))
    if isinstance(xcpt, (RpaJobTypeRetiredError, RpaVersionNotActiveError, RpaVersionNotFoundError)):
        _abort_problem(request=request, status=409, detail=str(xcpt), extensions={"spec_id": spec_id})
    if isinstance(xcpt, CapabilityMismatchError):
        _abort_problem(
            request=request, status=409, detail=str(xcpt),
            extensions={"reason": "capability_mismatch"},
        )
    if isinstance(xcpt, RpaDispatchUnavailableError):
        _abort_problem(
            request=request, status=503, detail=str(xcpt),
            extensions={"reason": "dispatch_not_configured"},
        )
    if isinstance(xcpt, RpaDispatchFailedError):
        _abort_problem(
            request=request, status=409, detail=str(xcpt), extensions={"reason": "dispatch_failed"},
        )
    raise xcpt


_TRIGGER_ERRORS = (
    PacketValidationError, PacketTooLargeError, RpaJobTypeRetiredError, RpaVersionNotActiveError,
    RpaVersionNotFoundError, CapabilityMismatchError, RpaDispatchUnavailableError, RpaDispatchFailedError,
)


def handle_trigger_job(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/rpa/specs/{spec_id}/trigger``

        Body: ``{"work_packet": {...}, "idempotency_key": "...",
        "allow_duplicate": false}``. Returns 202 with the new job; 200
        with the earlier job and ``"replayed": true`` when an identical
        run was submitted inside the idempotency window (send
        ``"allow_duplicate": true`` to start a new job anyway); 422 with
        an ``errors`` list when the packet fails validation (checked
        before any pod is chosen); 409 when no pod is eligible or the
        dispatcher refused.
    """
    project_id = str(request.path_params.get("project_id", ""))
    spec_id = str(request.path_params.get("spec_id", ""))
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request, db_session=db_session, permission_key=RPA_CREATE_PERMISSION_KEY,
        )
        project_row = _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        spec_view = _require_spec_in_project(
            request=request, db_session=db_session, project_id=project_id, spec_id=spec_id,
        )
        body = _decode_json_object_or_abort(request=request)
        _reject_unknown_fields(request=request, body=body, allowed=TRIGGER_FIELDS)
        work_packet = body.get("work_packet", {}) or {}
        if not isinstance(work_packet, dict):
            _abort_problem(request=request, status=422, detail="'work_packet' must be a JSON object.")
        idempotency_key = body.get("idempotency_key", None)
        allow_duplicate = body.get("allow_duplicate", False)
        if not isinstance(allow_duplicate, bool):
            _abort_problem(request=request, status=422, detail="'allow_duplicate' must be true or false.")

        # Validate the packet before looking for pods, so a caller with a
        # bad packet is told that rather than "no pod available".
        try:
            rpa_service.check_trigger_packet(
                db_session=db_session, project_id=project_id, spec_id=spec_id, work_packet=work_packet,
                principal=principal,
            )
        except _TRIGGER_ERRORS as xcpt:
            _abort_for_trigger_error(request=request, xcpt=xcpt, spec_id=spec_id)

        candidates = resolve_dispatch_candidates(
            db_session=db_session, project_id=project_id, target_pod_id=spec_view.target_pod_id,
        )
        if len(candidates) == 0:
            _abort_problem(
                request=request,
                status=409,
                detail=(
                    "No pod can run this RPA job: a pod needs at least one enrolled client "
                    "registered to it and the job's required capabilities."
                ),
                extensions={"project_id": project_id, "reason": "no_eligible_pod"},
            )

        aspect_kwargs: Dict[str, Any] = {
            "actor_id": _actor_id(principal),
            "candidates": candidates,
            "project_slug": str(getattr(project_row, "slug", "") or getattr(project_row, "name", "") or ""),
            "trigger_cause": {"kind": "api"},
            "principal": principal,
            "references_checked": True,
            "idempotency_key": str(idempotency_key) if idempotency_key else None,
        }
        if allow_duplicate is True:
            aspect_kwargs["idempotency_window_seconds"] = 0
        aspects = rpa_service.RpaTriggerAspects(**aspect_kwargs)
        view = None
        try:
            view = rpa_service.trigger_job(
                db_session=db_session, project_id=project_id, spec_id=spec_id,
                work_packet=work_packet, aspects=aspects,
            )
        except _TRIGGER_ERRORS as xcpt:
            _abort_for_trigger_error(request=request, xcpt=xcpt, spec_id=spec_id)
        _LOGGER.info(
            "pychestrate.rpa.trigger project_id=%s spec_id=%s job_id=%s replayed=%s",
            project_id, spec_id, view.job_id, view.replayed,
        )
        status_code = 200 if view.replayed is True else 202
        rtnval: Response = JSONResponse(content=_job_to_dict(view), status_code=status_code)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_list_jobs(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/rpa/jobs``
    """
    project_id = str(request.path_params.get("project_id", ""))
    try:
        db_session = _require_session(request=request)
        _require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
        _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        offset = _parse_positive_int(request=request, name="offset", default=0)
        limit = _parse_positive_int(
            request=request, name="limit", default=DEFAULT_PAGE_SIZE, maximum=MAX_PAGE_SIZE,
        )
        spec_id = request.query_params.get("spec_id", None) or None
        status_raw = request.query_params.get("status", None) or None
        status: Optional[RpaJobStatus] = None
        if status_raw:
            try:
                status = RpaJobStatus(str(status_raw))
            except ValueError:
                _abort_problem(request=request, status=400, detail="Unknown job status filter.")
        listing = rpa_service.list_jobs(
            db_session=db_session, project_id=project_id, spec_id=spec_id, status=status,
            offset=offset, limit=limit,
        )
        body = {
            "jobs": [_job_to_dict(v) for v in listing.jobs],
            "total": listing.total,
            "offset": listing.offset,
            "limit": listing.limit,
        }
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def _require_job_in_project(*, request: Request, db_session: Any, project_id: str, job_id: str) -> Any:
    try:
        view = rpa_service.get_job(db_session=db_session, job_id=job_id)
    except RpaJobNotFoundError as xcpt:
        _abort_problem(request=request, status=404, detail=str(xcpt), extensions={"job_id": job_id})
        view = None
    if view.project_id != project_id:
        _abort_problem(
            request=request, status=404, detail="RPA job not found in this project.",
            extensions={"job_id": job_id, "project_id": project_id},
        )
    rtnval = view
    return rtnval


def handle_read_job(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/rpa/jobs/{job_id}``
    """
    project_id = str(request.path_params.get("project_id", ""))
    job_id = str(request.path_params.get("job_id", ""))
    try:
        db_session = _require_session(request=request)
        _require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
        _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        view = _require_job_in_project(
            request=request, db_session=db_session, project_id=project_id, job_id=job_id,
        )
        rtnval: Response = JSONResponse(content=_job_to_dict(view), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_read_job_logs(request: Request) -> Response:
    """
        ``GET /api/v1/projects/{project_id}/rpa/jobs/{job_id}/logs``
        Returns ``{"job_id", "status", "text"}``; ``?tail=N`` keeps
        the last N lines.
    """
    project_id = str(request.path_params.get("project_id", ""))
    job_id = str(request.path_params.get("job_id", ""))
    try:
        db_session = _require_session(request=request)
        _require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
        _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        view = _require_job_in_project(
            request=request, db_session=db_session, project_id=project_id, job_id=job_id,
        )
        text = rpa_service.get_job_log_text(db_session=db_session, job_id=job_id)
        tail = _parse_positive_int(request=request, name="tail", default=0)
        if tail > 0:
            lines = text.splitlines()
            text = "\n".join(lines[-tail:])
        body = {"job_id": job_id, "status": _enum_value(view.status), "text": text}
        rtnval: Response = JSONResponse(content=body, status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


def handle_cancel_job(request: Request) -> Response:
    """
        ``POST /api/v1/projects/{project_id}/rpa/jobs/{job_id}/cancel``
    """
    project_id = str(request.path_params.get("project_id", ""))
    job_id = str(request.path_params.get("job_id", ""))
    try:
        db_session = _require_session(request=request)
        principal = _require_permission(
            request=request, db_session=db_session, permission_key=RPA_CREATE_PERMISSION_KEY,
        )
        _require_project_exists(request=request, db_session=db_session, project_id=project_id)
        _require_job_in_project(
            request=request, db_session=db_session, project_id=project_id, job_id=job_id,
        )
        try:
            view = rpa_service.cancel_job(
                db_session=db_session, job_id=job_id, actor_id=_actor_id(principal),
            )
        except RpaJobNotCancellableError as xcpt:
            _abort_problem(request=request, status=409, detail=str(xcpt), extensions={"job_id": job_id})
            view = None
        rtnval: Response = JSONResponse(content=_job_to_dict(view), status_code=200)
    except _ProblemAbort as xcpt:
        rtnval = xcpt.response
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_rpa_routes(*, app: Any, version_prefix: str) -> None:
    """
        Attach the RPA REST routes to a webworks app.

        :param app: WebWorks application.
        :param version_prefix: Versioned API prefix (``"/api/v1"``).
    """
    registry = version_prefix + "/rpa"
    app.attach_route(registry + "/execution-modes", methods=["GET"])(handle_list_execution_modes)
    app.attach_route(registry + "/job-types", methods=["GET"])(handle_list_job_types)
    app.attach_route(registry + "/job-types", methods=["POST"])(handle_create_job_type)
    app.attach_route(registry + "/job-types/{type_id}", methods=["GET"])(handle_read_job_type)
    app.attach_route(registry + "/job-types/{type_id}", methods=["PATCH"])(handle_update_job_type)
    app.attach_route(registry + "/job-types/{type_id}/retire", methods=["POST"])(handle_retire_job_type)
    app.attach_route(registry + "/job-types/{type_id}/versions", methods=["POST"])(handle_publish_version)
    app.attach_route(
        registry + "/job-types/{type_id}/versions/{version}/deprecate", methods=["POST"],
    )(handle_deprecate_version)
    app.attach_route(
        registry + "/job-types/{type_id}/versions/{version}/retire", methods=["POST"],
    )(handle_retire_version)

    project = version_prefix + "/projects/{project_id}/rpa"
    app.attach_route(project + "/specs", methods=["GET"])(handle_list_specs)
    app.attach_route(project + "/specs", methods=["POST"])(handle_create_spec)
    app.attach_route(project + "/specs/{spec_id}", methods=["GET"])(handle_read_spec)
    app.attach_route(project + "/specs/{spec_id}", methods=["PATCH"])(handle_update_spec)
    app.attach_route(project + "/specs/{spec_id}", methods=["DELETE"])(handle_delete_spec)
    app.attach_route(project + "/specs/{spec_id}/trigger", methods=["POST"])(handle_trigger_job)
    app.attach_route(project + "/jobs", methods=["GET"])(handle_list_jobs)
    app.attach_route(project + "/jobs/{job_id}", methods=["GET"])(handle_read_job)
    app.attach_route(project + "/jobs/{job_id}/logs", methods=["GET"])(handle_read_job_logs)
    app.attach_route(project + "/jobs/{job_id}/cancel", methods=["POST"])(handle_cancel_job)

    _LOGGER.info("pychestrate.rpa.routes.registered prefix=%s", version_prefix)
    return


__all__ = [
    "register_rpa_routes",
    "RPA_READ_PERMISSION_KEY",
    "RPA_CREATE_PERMISSION_KEY",
    "RPA_JOB_TYPES_MANAGE_PERMISSION_KEY",
]
