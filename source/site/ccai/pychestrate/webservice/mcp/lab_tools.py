"""
.. module:: webservice.mcp.lab_tools
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: MCP tools for working the lab: runs and their failures,
               the execution queue, RPA jobs, and lab devices.

.. moduleauthor:: Code Craft AI LLC

An AI agent working with Pychestrate needs to see what ran and what
failed, start work, and borrow devices. These tools wrap the same
service layer and permission keys as the REST API and the web UI:

* runs: ``list_runs`` (optionally failures only), ``get_run`` (with the
  state history that explains a failure) and ``queue_status`` -- gated on
  ``system:runs.read`` like ``/api/v1/runs``;
* RPA: ``list_rpa_specs``, ``trigger_rpa_job``, ``list_rpa_jobs`` and
  ``get_rpa_job`` -- gated on ``system:rpa.read`` / ``system:rpa.create``
  like ``/api/v1/projects/{project_id}/rpa/*``;
* lab devices: ``list_devices``, ``check_out_device`` and
  ``check_in_device`` -- open to any signed-in caller, like checkout in
  the web UI; only the holder can check a device back in.

Secret-declared RPA packet paths and sensitive device metadata are
never returned.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging
import uuid

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from ccai.webworks.routing.request import Request

from ccai.pychestrate.core.managers.allocation_manager import (
    AllocationError,
    AllocationManager,
    AllocationNotFoundError,
    CheckoutRequest,
    NotAllocationOwnerError,
    ResourceNotFoundError as AllocationResourceNotFoundError,
)
from ccai.pychestrate.core.managers.audit_logger import AuditLogger
from ccai.pychestrate.core.managers.resource_manager import ResourceManager
from ccai.pychestrate.webservice.clients.enums import ClientStatus, LivenessState
from ccai.pychestrate.webservice.clients.models import Client
from ccai.pychestrate.webservice.jobs.dispatch.models import (
    DispatchAttempt,
    DispatchAttemptStatus,
)
from ccai.pychestrate.webservice.jobs.run.state import repository as run_repo
from ccai.pychestrate.webservice.jobs.run.state.enums import RunState
from ccai.pychestrate.webservice.jobs.run.state.errors import RunNotFoundError
from ccai.pychestrate.webservice.jobs.run.state.models import Run
from ccai.pychestrate.webservice.mcp.tooling import (
    MCP_CONFLICT,
    MCP_INVALID_ARGUMENT,
    MCP_NOT_FOUND,
    MCP_PERMISSION_DENIED,
    MCP_UNAVAILABLE,
    McpToolError,
    ToolDefinition,
    bool_argument,
    has_permission,
    int_argument,
    iso_or_none,
    require_permission,
    require_principal,
    require_session,
    string_argument,
)
from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
from ccai.pychestrate.webservice.orchestration.rpa.candidates import (
    resolve_dispatch_candidates,
)
from ccai.pychestrate.webservice.orchestration.rpa.errors import (
    CapabilityMismatchError,
    PacketTooLargeError,
    PacketValidationError,
    RpaDispatchFailedError,
    RpaDispatchUnavailableError,
    RpaJobNotFoundError,
    RpaJobTypeRetiredError,
    RpaSpecNotFoundError,
    RpaVersionNotActiveError,
    RpaVersionNotFoundError,
)
from ccai.pychestrate.webservice.orchestration.rpa.models import RpaJobStatus
from ccai.pychestrate.webservice.projects import repository as projects_repo
# The REST serializers are reused so an MCP result and a REST response
# for the same object always agree (including packet redaction).
from ccai.pychestrate.webservice.orchestration.rpa.restapi.v1.rpa_routes import (
    _job_to_dict as rpa_job_to_dict,
    _spec_to_dict as rpa_spec_to_dict,
)
from ccai.pychestrate.webservice.runs.restapi.v1.runs_routes import (
    _run_to_dict as run_to_dict,
)


_LOGGER = logging.getLogger("pychestrate.mcp.lab_tools")


RUNS_READ_PERMISSION_KEY = "system:runs.read"
CLIENTS_READ_PERMISSION_KEY = "system:clients.read"
RPA_READ_PERMISSION_KEY = "system:rpa.read"
RPA_CREATE_PERMISSION_KEY = "system:rpa.create"

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
MAX_CHECKOUT_MINUTES = 7 * 24 * 60

# Run states that mean the run did not succeed.
FAILED_RUN_STATES = (
    RunState.FAILED,
    RunState.DISPATCH_FAILED,
    RunState.DISPATCH_LOST,
    RunState.NEEDS_INVESTIGATION,
)

# Run states that are still in flight (waiting, dispatching or running).
ACTIVE_RUN_STATES = (
    RunState.PENDING,
    RunState.DISPATCHING,
    RunState.DISPATCHED,
    RunState.DISPATCH_UNCONFIRMED,
    RunState.RUNNING,
    RunState.PROGRESS_STALLED,
    RunState.CANCEL_REQUESTED,
    RunState.CANCELLING,
    RunState.COMPLETING,
)

# Dispatch attempts still waiting for the pod to take them.
QUEUED_DISPATCH_STATUSES = (
    DispatchAttemptStatus.PENDING,
    DispatchAttemptStatus.TRANSMITTED,
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _page_arguments(*, arguments: Dict[str, Any]) -> Dict[str, int]:
    page = int_argument(arguments=arguments, name="page", default=1, minimum=1)
    per_page = int_argument(
        arguments=arguments, name="per_page", default=DEFAULT_PAGE_SIZE, minimum=1, maximum=MAX_PAGE_SIZE,
    )
    rtnval = {"page": page, "per_page": per_page, "offset": (page - 1) * per_page}
    return rtnval


def _uuid_argument(*, arguments: Dict[str, Any], name: str) -> str:
    value = string_argument(arguments=arguments, name=name, required=True)
    try:
        rtnval = str(uuid.UUID(value))
    except ValueError:
        raise McpToolError(code=MCP_INVALID_ARGUMENT, message="Argument '{}' must be a UUID.".format(name))
    return rtnval


def _state_history(*, db_session: Any, run_id: str) -> List[Dict[str, Any]]:
    rows = run_repo.list_state_audits(db_session=db_session, run_id=run_id)
    rtnval: List[Dict[str, Any]] = []
    for row in rows:
        rtnval.append({
            "from_state": getattr(row.from_state, "value", row.from_state),
            "to_state": getattr(row.to_state, "value", row.to_state),
            "event": getattr(row.event, "value", row.event),
            "actor": row.actor,
            "reason": row.reason,
            "at": iso_or_none(row.transitioned_at),
        })
    return rtnval


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


def _tool_list_runs(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``list_runs`` -- runs newest first, optionally only failures.
    """
    db_session = require_session(request=request)
    require_permission(request=request, db_session=db_session, permission_key=RUNS_READ_PERMISSION_KEY)

    paging = _page_arguments(arguments=arguments)
    project_id = string_argument(arguments=arguments, name="project_id")
    state = string_argument(arguments=arguments, name="state")
    failed_only = bool_argument(arguments=arguments, name="failed_only")

    query = db_session.query(Run)
    if project_id is not None:
        query = query.filter(Run.project_id == project_id)
    if state is not None:
        try:
            query = query.filter(Run.state == RunState(state.lower()))
        except ValueError:
            raise McpToolError(
                code=MCP_INVALID_ARGUMENT,
                message="Unknown run state {!r}; one of: {}.".format(
                    state, ", ".join(member.value for member in RunState),
                ),
            )
    if failed_only is True:
        query = query.filter(Run.state.in_(FAILED_RUN_STATES))

    total = query.count()
    rows = (
        query.order_by(Run.entered_state_at.desc())
        .offset(paging["offset"])
        .limit(paging["per_page"])
        .all()
    )
    rtnval = {
        "items": [run_to_dict(row=row, db_session=db_session) for row in rows],
        "meta": {"page": paging["page"], "per_page": paging["per_page"], "total": int(total)},
    }
    return rtnval


def _tool_get_run(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``get_run`` -- one run with its result manifest and the state
        history (with reasons) that explains how it ended.
    """
    db_session = require_session(request=request)
    require_permission(request=request, db_session=db_session, permission_key=RUNS_READ_PERMISSION_KEY)
    run_id = _uuid_argument(arguments=arguments, name="run_id")
    try:
        row = run_repo.get_run(db_session=db_session, run_id=run_id)
    except RunNotFoundError:
        raise McpToolError(code=MCP_NOT_FOUND, message="No run found with id {}.".format(run_id))
    rtnval = run_to_dict(row=row, db_session=db_session, include_result_manifest=True)
    rtnval["state_history"] = _state_history(db_session=db_session, run_id=run_id)
    return rtnval


def _tool_queue_status(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``queue_status`` -- what is waiting and running, recent
        failures, and (with ``system:clients.read``) client liveness.
    """
    db_session = require_session(request=request)
    principal = require_permission(
        request=request, db_session=db_session, permission_key=RUNS_READ_PERMISSION_KEY,
    )
    project_id = string_argument(arguments=arguments, name="project_id")
    now = datetime.now(timezone.utc)

    run_query = db_session.query(Run.state, func.count(Run.run_id)).filter(Run.state.in_(ACTIVE_RUN_STATES))
    if project_id is not None:
        run_query = run_query.filter(Run.project_id == project_id)
    active: Dict[str, int] = {member.value: 0 for member in ACTIVE_RUN_STATES}
    for state, count in run_query.group_by(Run.state).all():
        active[getattr(state, "value", str(state))] = int(count)

    failed_query = db_session.query(func.count(Run.run_id)).filter(
        Run.state.in_(FAILED_RUN_STATES),
        Run.entered_state_at >= now - timedelta(hours=24),
    )
    if project_id is not None:
        failed_query = failed_query.filter(Run.project_id == project_id)
    failures_last_24h = int(failed_query.scalar() or 0)

    dispatch_query = db_session.query(DispatchAttempt.status, func.count(DispatchAttempt.attempt_id)).filter(
        DispatchAttempt.status.in_(QUEUED_DISPATCH_STATUSES)
    )
    queued: Dict[str, int] = {member.value: 0 for member in QUEUED_DISPATCH_STATUSES}
    for status, count in dispatch_query.group_by(DispatchAttempt.status).all():
        queued[getattr(status, "value", str(status))] = int(count)

    rtnval: Dict[str, Any] = {
        "project_id": project_id,
        "active_runs": active,
        "active_run_total": sum(active.values()),
        "queued_dispatches": queued,
        "failures_last_24h": failures_last_24h,
        "clients": None,
    }
    if has_permission(db_session=db_session, principal=principal, permission_key=CLIENTS_READ_PERMISSION_KEY):
        client_query = db_session.query(Client.liveness_state, func.count(Client.client_id)).filter(
            Client.status == ClientStatus.ACTIVE
        )
        if project_id is not None:
            client_query = client_query.filter(Client.project_id == project_id)
        liveness: Dict[str, int] = {member.value.lower(): 0 for member in LivenessState}
        for state, count in client_query.group_by(Client.liveness_state).all():
            liveness[str(getattr(state, "value", state)).lower()] = int(count)
        rtnval["clients"] = liveness
    return rtnval


# ---------------------------------------------------------------------------
# RPA
# ---------------------------------------------------------------------------


def _project_slug(*, db_session: Any, project_id: str) -> str:
    """
        The slug (or legacy name) of the project an RPA specification
        belongs to, which names the job's results prefix -- resolved the
        same way the REST trigger route resolves it.
    """
    row: Any = None
    try:
        row = projects_repo.get_project_by_id(db_session=db_session, project_id=str(uuid.UUID(project_id)))
    except ValueError:
        if project_id.isdigit():
            from ccai.pychestrate.core.orm import Project as CoreProject  # noqa: E402
            row = db_session.query(CoreProject).filter(CoreProject.id == int(project_id)).first()
    if row is None:
        raise McpToolError(code=MCP_NOT_FOUND, message="No project found with id {}.".format(project_id))
    rtnval = str(getattr(row, "slug", "") or getattr(row, "name", "") or "")
    return rtnval


def _spec_in_project(*, db_session: Any, project_id: str, spec_id: str) -> Any:
    try:
        view = rpa_service.get_spec(db_session=db_session, spec_id=spec_id)
    except RpaSpecNotFoundError:
        view = None
    if view is None or str(view.project_id) != project_id:
        raise McpToolError(
            code=MCP_NOT_FOUND,
            message="No RPA specification {} in project {}.".format(spec_id, project_id),
        )
    rtnval = view
    return rtnval


def _tool_list_rpa_specs(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``list_rpa_specs`` -- the RPA specifications a project can run.
    """
    db_session = require_session(request=request)
    require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
    project_id = string_argument(arguments=arguments, name="project_id", required=True)
    paging = _page_arguments(arguments=arguments)
    views, total = rpa_service.list_specs(
        db_session=db_session, project_id=project_id, offset=paging["offset"], limit=paging["per_page"],
    )
    rtnval = {
        "items": [rpa_spec_to_dict(view) for view in views],
        "meta": {"page": paging["page"], "per_page": paging["per_page"], "total": int(total)},
    }
    return rtnval


def _trigger_failure(xcpt: Exception) -> McpToolError:
    """
        Translate a trigger-path error from the RPA service into the tool
        error an agent can act on.
    """
    if isinstance(xcpt, PacketValidationError):
        details = "; ".join("{}: {}".format(path or "/", message) for path, message in xcpt.issues)
        rtnval = McpToolError(code=MCP_INVALID_ARGUMENT, message="{} {}".format(xcpt, details).strip())
    elif isinstance(xcpt, PacketTooLargeError):
        rtnval = McpToolError(code=MCP_INVALID_ARGUMENT, message=str(xcpt))
    elif isinstance(xcpt, RpaDispatchUnavailableError):
        rtnval = McpToolError(code=MCP_UNAVAILABLE, message=str(xcpt))
    else:
        rtnval = McpToolError(code=MCP_CONFLICT, message=str(xcpt))
    return rtnval


_TRIGGER_ERRORS = (
    PacketValidationError, PacketTooLargeError, RpaJobTypeRetiredError, RpaVersionNotActiveError,
    RpaVersionNotFoundError, CapabilityMismatchError, RpaDispatchUnavailableError, RpaDispatchFailedError,
)


def _tool_trigger_rpa_job(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``trigger_rpa_job`` -- start a job from an RPA specification,
        exactly as ``POST .../rpa/specs/{spec_id}/trigger`` does.
    """
    db_session = require_session(request=request)
    principal = require_permission(
        request=request, db_session=db_session, permission_key=RPA_CREATE_PERMISSION_KEY,
    )
    project_id = string_argument(arguments=arguments, name="project_id", required=True)
    spec_id = string_argument(arguments=arguments, name="spec_id", required=True)
    work_packet = arguments.get("work_packet", None)
    if work_packet is None:
        work_packet = {}
    if not isinstance(work_packet, dict):
        raise McpToolError(code=MCP_INVALID_ARGUMENT, message="Argument 'work_packet' must be an object.")
    idempotency_key = string_argument(arguments=arguments, name="idempotency_key")
    allow_duplicate = bool_argument(arguments=arguments, name="allow_duplicate")

    project_slug = _project_slug(db_session=db_session, project_id=project_id)
    spec_view = _spec_in_project(db_session=db_session, project_id=project_id, spec_id=spec_id)
    try:
        rpa_service.check_trigger_packet(
            db_session=db_session, project_id=project_id, spec_id=spec_id, work_packet=work_packet,
        )
    except _TRIGGER_ERRORS as xcpt:
        raise _trigger_failure(xcpt)

    candidates = resolve_dispatch_candidates(
        db_session=db_session, project_id=project_id, target_pod_id=spec_view.target_pod_id,
    )
    if len(candidates) == 0:
        raise McpToolError(
            code=MCP_CONFLICT,
            message=(
                "No pod can run this RPA job: a pod needs at least one enrolled client "
                "registered to it and the job's required capabilities."
            ),
        )

    user_id = getattr(principal, "user_id", None)
    aspect_kwargs: Dict[str, Any] = {
        "actor_id": str(user_id) if user_id is not None else None,
        "candidates": candidates,
        "project_slug": project_slug,
        "trigger_cause": {"kind": "mcp"},
        "idempotency_key": idempotency_key,
    }
    if allow_duplicate is True:
        aspect_kwargs["idempotency_window_seconds"] = 0
    try:
        view = rpa_service.trigger_job(
            db_session=db_session, project_id=project_id, spec_id=spec_id,
            work_packet=work_packet, aspects=rpa_service.RpaTriggerAspects(**aspect_kwargs),
        )
    except _TRIGGER_ERRORS as xcpt:
        raise _trigger_failure(xcpt)
    _LOGGER.info(
        "pychestrate.mcp.trigger_rpa_job project_id=%s spec_id=%s job_id=%s replayed=%s",
        project_id, spec_id, view.job_id, view.replayed,
    )
    rtnval = rpa_job_to_dict(view)
    return rtnval


def _tool_list_rpa_jobs(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``list_rpa_jobs`` -- a project's RPA jobs, newest first.
    """
    db_session = require_session(request=request)
    require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
    project_id = string_argument(arguments=arguments, name="project_id", required=True)
    status_raw = string_argument(arguments=arguments, name="status")
    status: Optional[RpaJobStatus] = None
    if status_raw is not None:
        try:
            status = RpaJobStatus(status_raw.lower())
        except ValueError:
            raise McpToolError(
                code=MCP_INVALID_ARGUMENT,
                message="Unknown job status {!r}; one of: {}.".format(
                    status_raw, ", ".join(member.value for member in RpaJobStatus),
                ),
            )
    paging = _page_arguments(arguments=arguments)
    listing = rpa_service.list_jobs(
        db_session=db_session, project_id=project_id, status=status,
        offset=paging["offset"], limit=paging["per_page"],
    )
    rtnval = {
        "items": [rpa_job_to_dict(view) for view in listing.jobs],
        "meta": {"page": paging["page"], "per_page": paging["per_page"], "total": int(listing.total)},
    }
    return rtnval


def _tool_get_rpa_job(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``get_rpa_job`` -- one RPA job, with its log when asked.
    """
    db_session = require_session(request=request)
    require_permission(request=request, db_session=db_session, permission_key=RPA_READ_PERMISSION_KEY)
    job_id = string_argument(arguments=arguments, name="job_id", required=True)
    include_log = bool_argument(arguments=arguments, name="include_log")
    try:
        view = rpa_service.get_job(db_session=db_session, job_id=job_id)
    except RpaJobNotFoundError:
        raise McpToolError(code=MCP_NOT_FOUND, message="No RPA job found with id {}.".format(job_id))
    rtnval = rpa_job_to_dict(view)
    if include_log is True:
        rtnval["log"] = rpa_service.get_job_log_text(db_session=db_session, job_id=job_id)
    return rtnval


# ---------------------------------------------------------------------------
# Lab devices
# ---------------------------------------------------------------------------


def _device_to_dict(*, resource: Any, manager: ResourceManager, allocation_manager: AllocationManager) -> Dict[str, Any]:
    upcoming = allocation_manager.list_reservations(
        resource_id=resource.id, status="pending", start_after=None, limit=1,
    )
    next_reservation = None
    if len(upcoming.reservations) > 0:
        reservation = upcoming.reservations[0]
        next_reservation = {
            "reservation_id": reservation.id,
            "reserved_by": reservation.username,
            "start_time": iso_or_none(reservation.start_time),
            "end_time": iso_or_none(reservation.end_time),
        }
    rtnval = {
        "resource_id": resource.id,
        "name": resource.name,
        "resource_type": resource.resource_type,
        "pool_id": resource.pool_id,
        "pool_name": resource.pool_name,
        "description": resource.description,
        "tags": list(resource.tags),
        "health_status": resource.health_status,
        "capacity": resource.capacity,
        "current_allocations": resource.current_allocations,
        "available": resource.health_status not in ("offline", "maintenance")
        and resource.current_allocations < resource.capacity,
        # Sensitive metadata fields (passwords, keys) come back masked.
        "metadata": manager.get_metadata(resource.id, include_sensitive=False),
        "next_reservation": next_reservation,
    }
    return rtnval


def _allocation_to_dict(allocation: Any) -> Dict[str, Any]:
    rtnval = {
        "allocation_id": allocation.id,
        "resource_id": allocation.resource_id,
        "resource_name": allocation.resource_name,
        "holder": allocation.username,
        "job_id": allocation.job_id,
        "mode": allocation.mode,
        "status": allocation.status,
        "checkout_time": iso_or_none(allocation.checkout_time),
        "expected_checkin": iso_or_none(allocation.expected_checkin),
        "actual_checkin": iso_or_none(allocation.actual_checkin),
        "duration_minutes": allocation.duration_minutes,
    }
    return rtnval


def _tool_list_devices(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``list_devices`` -- lab devices with health, availability and
        the next reservation.
    """
    db_session = require_session(request=request)
    require_principal(request=request)
    paging = _page_arguments(arguments=arguments)
    tag = string_argument(arguments=arguments, name="tag")
    manager = ResourceManager(db_session)
    listing = manager.list_resources(
        pool_id=int_argument(arguments=arguments, name="pool_id", minimum=1),
        tags=[tag] if tag is not None else None,
        available_only=bool_argument(arguments=arguments, name="available_only"),
        search=string_argument(arguments=arguments, name="search"),
        offset=paging["offset"],
        limit=paging["per_page"],
    )
    allocation_manager = AllocationManager(db_session)
    rtnval = {
        "items": [
            _device_to_dict(resource=resource, manager=manager, allocation_manager=allocation_manager)
            for resource in listing.resources
        ],
        "meta": {"page": paging["page"], "per_page": paging["per_page"], "total": int(listing.total)},
    }
    return rtnval


def _tool_check_out_device(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``check_out_device`` -- borrow a lab device, as the web UI's
        Check out button does.
    """
    db_session = require_session(request=request)
    require_principal(request=request)
    actor_user_id = getattr(request, "actor_user_id", None)
    if actor_user_id is None:
        raise McpToolError(code=MCP_PERMISSION_DENIED, message="The caller has no user identity to hold a device.")
    resource_id = int_argument(arguments=arguments, name="resource_id", minimum=1, required=True)
    mode = string_argument(arguments=arguments, name="mode") or "exclusive"
    if mode not in ("exclusive", "shared"):
        raise McpToolError(code=MCP_INVALID_ARGUMENT, message="Argument 'mode' must be 'exclusive' or 'shared'.")
    checkout = CheckoutRequest(
        resource_id=resource_id,
        job_id=string_argument(arguments=arguments, name="job_id"),
        mode=mode,
        timeout_minutes=int_argument(
            arguments=arguments, name="timeout_minutes", minimum=1, maximum=MAX_CHECKOUT_MINUTES,
        ),
        reason=string_argument(arguments=arguments, name="reason") or "Checked out through MCP",
    )
    manager = AllocationManager(db_session, audit_logger=AuditLogger(db_session))
    try:
        allocation = manager.checkout(checkout, str(actor_user_id))
    except AllocationResourceNotFoundError as xcpt:
        raise McpToolError(code=MCP_NOT_FOUND, message=str(xcpt))
    except AllocationError as xcpt:
        raise McpToolError(code=MCP_CONFLICT, message=str(xcpt))
    rtnval = _allocation_to_dict(allocation)
    return rtnval


def _tool_check_in_device(*, request: Request, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """
        Tool ``check_in_device`` -- return a device the caller holds.
    """
    db_session = require_session(request=request)
    require_principal(request=request)
    actor_user_id = getattr(request, "actor_user_id", None)
    if actor_user_id is None:
        raise McpToolError(code=MCP_PERMISSION_DENIED, message="The caller has no user identity to hold a device.")
    allocation_id = int_argument(arguments=arguments, name="allocation_id", minimum=1, required=True)
    manager = AllocationManager(db_session, audit_logger=AuditLogger(db_session))
    try:
        allocation = manager.checkin(allocation_id, str(actor_user_id))
    except AllocationNotFoundError as xcpt:
        raise McpToolError(code=MCP_NOT_FOUND, message=str(xcpt))
    except NotAllocationOwnerError as xcpt:
        raise McpToolError(code=MCP_PERMISSION_DENIED, message=str(xcpt))
    except AllocationError as xcpt:
        raise McpToolError(code=MCP_CONFLICT, message=str(xcpt))
    rtnval = _allocation_to_dict(allocation)
    return rtnval


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _paging_properties() -> Dict[str, Any]:
    rtnval = {
        "page": {"type": "integer", "minimum": 1, "description": "1-based page number."},
        "per_page": {"type": "integer", "minimum": 1, "maximum": MAX_PAGE_SIZE, "description": "Page size."},
    }
    return rtnval


_RPA_PROJECT_DESCRIPTION = (
    "The project the RPA specification belongs to: the project UUID, or the"
    " numeric project id shown in the web UI."
)


def build_lab_tools() -> List[ToolDefinition]:
    """
        The lab tools, in the order ``tools/list`` advertises them.

        :returns: Tool definitions.
    """
    rtnval = [
        ToolDefinition(
            name="list_runs",
            title="List runs",
            description=(
                "List job runs newest first. Filter by project, by state, or to failures only"
                " (failed, dispatch_failed, dispatch_lost, needs_investigation)."
                " Requires 'system:runs.read'."
            ),
            input_schema={
                "type": "object",
                "properties": dict({
                    "project_id": {"type": "string", "description": "Only runs of this project (UUID)."},
                    "state": {
                        "type": "string",
                        "enum": [member.value for member in RunState],
                        "description": "Only runs in this state.",
                    },
                    "failed_only": {"type": "boolean", "description": "Only runs that did not succeed."},
                }, **_paging_properties()),
                "additionalProperties": False,
            },
            handler=_tool_list_runs,
        ),
        ToolDefinition(
            name="get_run",
            title="Get a run",
            description=(
                "Read one run: its state, outcome, timing, pod, progress, result manifest and the"
                " state history with the reason for each transition (why it failed)."
                " Requires 'system:runs.read'."
            ),
            input_schema={
                "type": "object",
                "properties": {"run_id": {"type": "string", "description": "The run UUID."}},
                "required": ["run_id"],
                "additionalProperties": False,
            },
            handler=_tool_get_run,
        ),
        ToolDefinition(
            name="queue_status",
            title="Queue status",
            description=(
                "What is in flight: active runs by state, dispatches waiting for a pod, failures in"
                " the last 24 hours and (with 'system:clients.read') client liveness."
                " Requires 'system:runs.read'."
            ),
            input_schema={
                "type": "object",
                "properties": {"project_id": {"type": "string", "description": "Only this project (UUID)."}},
                "additionalProperties": False,
            },
            handler=_tool_queue_status,
        ),
        ToolDefinition(
            name="list_rpa_specs",
            title="List RPA specifications",
            description=(
                "List the RPA specifications a project can run, with their packet schema and"
                " default packet (secret fields redacted). Requires 'system:rpa.read'."
            ),
            input_schema={
                "type": "object",
                "properties": dict({
                    "project_id": {"type": "string", "description": _RPA_PROJECT_DESCRIPTION},
                }, **_paging_properties()),
                "required": ["project_id"],
                "additionalProperties": False,
            },
            handler=_tool_list_rpa_specs,
        ),
        ToolDefinition(
            name="trigger_rpa_job",
            title="Trigger an RPA job",
            description=(
                "Start a job from an RPA specification. The work packet is merged over the"
                " specification's default and validated against its schema. Resending the same"
                " packet and idempotency key inside the idempotency window returns the earlier job"
                " with replayed=true; pass allow_duplicate=true to start another."
                " Requires 'system:rpa.create'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": _RPA_PROJECT_DESCRIPTION},
                    "spec_id": {"type": "string", "description": "The RPA specification id."},
                    "work_packet": {"type": "object", "description": "Work packet for this run."},
                    "idempotency_key": {"type": "string", "description": "Optional idempotency key."},
                    "allow_duplicate": {"type": "boolean", "description": "Start a new job even if identical."},
                },
                "required": ["project_id", "spec_id"],
                "additionalProperties": False,
            },
            handler=_tool_trigger_rpa_job,
            read_only=False,
        ),
        ToolDefinition(
            name="list_rpa_jobs",
            title="List RPA jobs",
            description="List a project's RPA jobs newest first, optionally by status. Requires 'system:rpa.read'.",
            input_schema={
                "type": "object",
                "properties": dict({
                    "project_id": {"type": "string", "description": _RPA_PROJECT_DESCRIPTION},
                    "status": {
                        "type": "string",
                        "enum": [member.value for member in RpaJobStatus],
                        "description": "Only jobs with this status.",
                    },
                }, **_paging_properties()),
                "required": ["project_id"],
                "additionalProperties": False,
            },
            handler=_tool_list_rpa_jobs,
        ),
        ToolDefinition(
            name="get_rpa_job",
            title="Get an RPA job",
            description=(
                "Read one RPA job: status, pod, timing, exit code and the reason it ended;"
                " include_log adds the log the client reported. Requires 'system:rpa.read'."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "The RPA job id."},
                    "include_log": {"type": "boolean", "description": "Also return the job's log text."},
                },
                "required": ["job_id"],
                "additionalProperties": False,
            },
            handler=_tool_get_rpa_job,
        ),
        ToolDefinition(
            name="list_devices",
            title="List lab devices",
            description=(
                "List lab devices with health, capacity, current allocations, availability and the"
                " next reservation. Sensitive metadata fields are masked."
            ),
            input_schema={
                "type": "object",
                "properties": dict({
                    "pool_id": {"type": "integer", "minimum": 1, "description": "Only devices in this pool."},
                    "tag": {"type": "string", "description": "Only devices with this tag."},
                    "search": {"type": "string", "description": "Match the name or description."},
                    "available_only": {"type": "boolean", "description": "Only devices free to check out."},
                }, **_paging_properties()),
                "additionalProperties": False,
            },
            handler=_tool_list_devices,
        ),
        ToolDefinition(
            name="check_out_device",
            title="Check out a device",
            description=(
                "Check out a lab device for the caller, as the web UI's Check out button does."
                " Fails when the device is offline, in maintenance, or already held."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "resource_id": {"type": "integer", "minimum": 1, "description": "The device id."},
                    "timeout_minutes": {
                        "type": "integer", "minimum": 1, "maximum": MAX_CHECKOUT_MINUTES,
                        "description": "Release the device automatically after this long.",
                    },
                    "mode": {"type": "string", "enum": ["exclusive", "shared"], "description": "Allocation mode."},
                    "reason": {"type": "string", "description": "Why the device is needed."},
                    "job_id": {"type": "string", "description": "Job the device is used for."},
                },
                "required": ["resource_id"],
                "additionalProperties": False,
            },
            handler=_tool_check_out_device,
            read_only=False,
        ),
        ToolDefinition(
            name="check_in_device",
            title="Check in a device",
            description="Check in a device the caller holds, ending the allocation.",
            input_schema={
                "type": "object",
                "properties": {
                    "allocation_id": {
                        "type": "integer", "minimum": 1,
                        "description": "The allocation id check_out_device returned.",
                    },
                },
                "required": ["allocation_id"],
                "additionalProperties": False,
            },
            handler=_tool_check_in_device,
            read_only=False,
        ),
    ]
    return rtnval
