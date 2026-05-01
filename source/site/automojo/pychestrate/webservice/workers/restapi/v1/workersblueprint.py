"""
.. module:: workers.restapi.v1.workersblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/workers.

.. moduleauthor:: Automation Mojo LLC

Endpoints:

* POST   /api/v1/workers/register   — public; agent (bearer) self-register
                                       OR admin (cookie) for local-process
                                       workers.
* POST   /api/v1/workers/{id}/heartbeat — agent or admin.
* GET    /api/v1/workers            — admin read.
* GET    /api/v1/workers/{id}       — admin read.
* POST   /api/v1/workers/{id}/drain — admin.
* DELETE /api/v1/workers/{id}       — admin.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict, Optional

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse, Response
from automojo.webworks.security.accesspolicy import AccessPolicy

from automojo.pychestrate.webservice.workers import (
    jobservice as worker_job_service,
    service as worker_service,
)
from automojo.pychestrate.webservice.workers.exceptions import (
    WorkerAlreadyRegisteredError,
    WorkerNotFoundError,
    WorkerStateTransitionError,
)
from automojo.pychestrate.webservice.workers.models import (
    WorkerKind,
    WorkerStatus,
)


WORKERS_BASE_PATH = "/api/v1/workers"


_ADMIN_POLICY = AccessPolicy(roles=("system-admin",))
# Workers self-heartbeat with their bearer token; admins can also
# call any of these for ops.
_WORKER_OR_ADMIN = AccessPolicy(roles=("system-admin", "agent"))


def _require_db_session(*, request: Request) -> Any:
    db_session = getattr(request, "db_session", None)
    if db_session is None:
        err_lines = [
            "Request-scoped db_session not configured.",
            "DbSessionMiddleware must be installed in the pipeline.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise HTTPException(status_code=503, detail=err_msg)
    return db_session


def _read_json_body(*, request: Request) -> Dict[str, Any]:
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")
    try:
        decoded = request.json()
    except Exception as exc:
        err_msg = "request body must be valid JSON"
        raise HTTPException(status_code=400, detail=err_msg) from exc
    if not isinstance(decoded, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object",
        )
    rtnval = decoded
    return rtnval


def _view_to_dict(*, view) -> Dict[str, Any]:
    rtnval = {
        "worker_id": view.worker_id,
        "name": view.name,
        "kind": view.kind,
        "project_id": view.project_id,
        "client_id": view.client_id,
        "status": view.status,
        "registered_at": view.registered_at,
        "last_heartbeat_at": view.last_heartbeat_at,
        "attributes": view.attributes,
    }
    return rtnval


def _parse_kind(*, raw: str) -> WorkerKind:
    try:
        rtnval = WorkerKind(raw)
    except ValueError as exc:
        err_msg = "Unknown worker kind: {}".format(raw)
        raise HTTPException(status_code=400, detail=err_msg) from exc
    return rtnval


def _parse_status(*, raw: Optional[str]) -> Optional[WorkerStatus]:
    if raw is None or len(raw) == 0:
        return None
    try:
        rtnval = WorkerStatus(raw)
    except ValueError as exc:
        err_msg = "Unknown worker status: {}".format(raw)
        raise HTTPException(status_code=400, detail=err_msg) from exc
    return rtnval


class WorkersBlueprint(RestBlueprint):
    """
        Worker registry REST surface.
    """

    base_path = WORKERS_BASE_PATH
    tags = ["workers", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/workers/register",
        methods=["POST"],
        doc=Doc(
            summary="Register a worker",
            description=(
                "Agents (bearer auth) self-register on startup; "
                "admins (cookie auth) may pre-register local-process "
                "workers. Body: ``{name, kind, project_id?, "
                "attributes?}``. The kind must be one of "
                "``local-process`` / ``remote-machine``. For "
                "remote-machine workers, the bearer's client_id is "
                "linked automatically."
            ),
        ),
        access_policy=_WORKER_OR_ADMIN,
    )
    def register_worker(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        payload = _read_json_body(request=request)

        name = str(payload.get("name", "")).strip()
        if len(name) == 0:
            raise HTTPException(
                status_code=400, detail="name is required",
            )
        kind = _parse_kind(raw=str(payload.get("kind", "")))

        project_id = payload.get("project_id", None)
        attributes = payload.get("attributes", None)

        # Auto-link client_id when an agent self-registers.
        client_id: Optional[str] = None
        auth_context = getattr(request, "auth", None)
        if auth_context is not None:
            attributes_in_ctx = getattr(auth_context, "attributes", None)
            if attributes_in_ctx is not None:
                client_id = attributes_in_ctx.get("client_id", None)
            # When self-registering as an agent, default project_id
            # to the agent's project so an agent can't create workers
            # in foreign projects.
            if "agent" in auth_context.principal.roles:
                if attributes_in_ctx is not None:
                    project_id = attributes_in_ctx.get(
                        "project_id", project_id,
                    )

        try:
            view = worker_service.register_worker(
                db_session=db_session,
                name=name,
                kind=kind,
                project_id=project_id,
                client_id=client_id,
                attributes=attributes,
            )
        except WorkerAlreadyRegisteredError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc),
            ) from exc

        body = _view_to_dict(view=view)
        rtnval = JSONResponse(content=body, status_code=201)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/workers/{worker_id}/heartbeat",
        methods=["POST"],
        doc=Doc(
            summary="Worker heartbeat",
            description=(
                "Stamp last_heartbeat_at + optionally update status. "
                "Body: ``{status?: 'idle'|'running'|'offline'}``."
            ),
        ),
        access_policy=_WORKER_OR_ADMIN,
    )
    def heartbeat_worker(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        worker_id = request.path_params.get("worker_id", "")

        # Body is optional; an empty heartbeat just stamps the time.
        status: Optional[WorkerStatus] = None
        raw_body = request.body
        if raw_body is not None:
            if len(raw_body) > 0:
                payload = _read_json_body(request=request)
                status = _parse_status(
                    raw=payload.get("status", None),
                )

        try:
            view = worker_service.heartbeat_worker(
                db_session=db_session,
                worker_id=worker_id,
                status=status,
            )
        except WorkerNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        except WorkerStateTransitionError as exc:
            raise HTTPException(
                status_code=409, detail=str(exc),
            ) from exc

        body = _view_to_dict(view=view)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/workers",
        methods=["GET"],
        doc=Doc(
            summary="List workers",
            description=(
                "List workers. Filters: kind, status, project_id."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def list_workers_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        kind_raw = request.query_params.get("kind", None)
        status_raw = request.query_params.get("status", None)
        project_id = request.query_params.get("project_id", None)

        if kind_raw is None or len(kind_raw) == 0:
            kind: Optional[WorkerKind] = None
        else:
            kind = _parse_kind(raw=kind_raw)
        status = _parse_status(raw=status_raw)

        views = worker_service.list_workers(
            db_session=db_session,
            kind=kind,
            status=status,
            project_id=project_id,
        )
        body = [_view_to_dict(view=v) for v in views]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/workers/{worker_id}",
        methods=["GET"],
        doc=Doc(
            summary="Read worker",
            description="Read one worker by id.",
        ),
        access_policy=_ADMIN_POLICY,
    )
    def read_worker_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        worker_id = request.path_params.get("worker_id", "")
        try:
            view = worker_service.read_worker(
                db_session=db_session, worker_id=worker_id,
            )
        except WorkerNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        body = _view_to_dict(view=view)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/workers/{worker_id}/drain",
        methods=["POST"],
        doc=Doc(
            summary="Drain a worker",
            description=(
                "Mark a worker as DRAINING. The worker is expected "
                "to finish its current job and exit."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def drain_worker_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        worker_id = request.path_params.get("worker_id", "")
        try:
            view = worker_service.drain_worker(
                db_session=db_session, worker_id=worker_id,
            )
        except WorkerNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        body = _view_to_dict(view=view)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/workers/{worker_id}",
        methods=["DELETE"],
        doc=Doc(
            summary="Deregister a worker",
            description="Remove the worker row.",
        ),
        access_policy=_ADMIN_POLICY,
    )
    def deregister_worker_endpoint(request: Request) -> Response:
        db_session = _require_db_session(request=request)
        worker_id = request.path_params.get("worker_id", "")
        try:
            worker_service.deregister_worker(
                db_session=db_session, worker_id=worker_id,
            )
        except WorkerNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        rtnval = Response(status_code=204, body=b"")
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/workers/{worker_id}/jobs/poll",
        methods=["POST"],
        doc=Doc(
            summary="Worker polls for next job",
            description=(
                "Atomically claim the oldest PENDING job whose "
                "selectors match this worker. Returns 200 with a "
                "JobView when one was claimed; 200 with "
                "``{job: null}`` when the queue has nothing."
            ),
        ),
        access_policy=_WORKER_OR_ADMIN,
    )
    def poll_next_job(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        worker_id = request.path_params.get("worker_id", "")
        view = worker_job_service.claim_next_job(
            db_session=db_session, worker_id=worker_id,
        )
        if view is None:
            body = {"job": None}
        else:
            body = {"job": _job_view_to_dict(view=view)}
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/workers/{worker_id}/jobs/{job_id}/result",
        methods=["POST"],
        doc=Doc(
            summary="Worker reports job result",
            description=(
                "Body: ``{result_code, stdout?, stderr?, "
                "error_text?}``. Sets the job state to SUCCEEDED "
                "(result_code == 0) or FAILED."
            ),
        ),
        access_policy=_WORKER_OR_ADMIN,
    )
    def report_job_result(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        worker_id = request.path_params.get("worker_id", "")
        job_id = request.path_params.get("job_id", "")
        payload = _read_json_body(request=request)

        result_code_raw = payload.get("result_code", None)
        if result_code_raw is None:
            raise HTTPException(
                status_code=400, detail="result_code is required",
            )
        try:
            result_code = int(result_code_raw)
        except (TypeError, ValueError) as exc:
            err_msg = "result_code must be an integer"
            raise HTTPException(status_code=400, detail=err_msg) from exc

        try:
            view = worker_job_service.report_result(
                db_session=db_session,
                worker_id=worker_id,
                job_id=job_id,
                result_code=result_code,
                stdout=str(payload.get("stdout", "")),
                stderr=str(payload.get("stderr", "")),
                error_text=payload.get("error_text", None),
            )
        except LookupError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        body = _job_view_to_dict(view=view)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval


def _job_view_to_dict(*, view) -> Dict[str, Any]:
    rtnval = {
        "job_id": view.job_id,
        "kind": view.kind,
        "payload": view.payload,
        "target_pod_name": view.target_pod_name,
        "target_kind": view.target_kind,
        "worker_id": view.worker_id,
        "state": view.state,
        "enqueued_at": view.enqueued_at,
        "claimed_at": view.claimed_at,
        "completed_at": view.completed_at,
        "result_code": view.result_code,
        "stdout": view.stdout,
        "stderr": view.stderr,
        "error_text": view.error_text,
        "attempt": view.attempt,
        "max_attempts": view.max_attempts,
        "retry_delay_seconds": view.retry_delay_seconds,
        "retry_strategy": view.retry_strategy,
        "not_before": view.not_before,
        "required_capabilities": view.required_capabilities,
    }
    return rtnval
