"""
.. module:: workers.restapi.v1.queueblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/queue.

.. moduleauthor:: Automation Mojo LLC

Endpoints (all gated ``system-admin``):

* GET /api/v1/queue/stats — operator dashboard payload:
  job depth by state, worker count by status, oldest pending
  age, retry-scheduled count.
* GET /api/v1/queue/jobs — list jobs newest-first with optional
  ``state`` / ``target_pod_name`` / ``target_kind`` /
  ``worker_id`` filters and a ``limit`` capped at 500.
* GET /api/v1/queue/jobs/{job_id} — read one job.
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
    artifactservice,
    joblogservice,
    jobservice,
    service as worker_service,
    testresultservice,
)
from automojo.pychestrate.webservice.workers.artifactservice import (
    ArtifactJobMismatchError,
    ArtifactNotFoundError,
)


QUEUE_BASE_PATH = "/api/v1/queue"


_ADMIN_POLICY = AccessPolicy(roles=("system-admin",))


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
        "lease_holder": view.lease_holder,
        "lease_ttl_seconds": view.lease_ttl_seconds,
        "priority": view.priority,
        "project_id": view.project_id,
    }
    return rtnval


class QueueBlueprint(RestBlueprint):
    """
        Worker-queue inspection REST surface.
    """

    base_path = QUEUE_BASE_PATH
    tags = ["queue", "workers", "v1"]

    @RestBlueprint.attach_at(
        path="/api/v1/queue/stats",
        methods=["GET"],
        doc=Doc(
            summary="Queue + worker stats",
            description=(
                "One-shot operator-dashboard payload: job depth "
                "by state, worker count by status, the age of "
                "the oldest claimable PENDING job, and the count "
                "of retry-scheduled jobs (PENDING with "
                "``not_before`` still in the future)."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def queue_stats(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        jobs_by_state = jobservice.count_jobs_by_state(
            db_session=db_session,
        )
        retry_pending = jobservice.count_retry_scheduled_jobs(
            db_session=db_session,
        )
        oldest_age = jobservice.oldest_pending_age_seconds(
            db_session=db_session,
        )
        in_flight = (
            jobs_by_state.get("claimed", 0)
            + jobs_by_state.get("running", 0)
        )
        workers_by_status = worker_service.count_workers_by_status(
            db_session=db_session,
        )
        body = {
            "jobs": {
                "by_state": jobs_by_state,
                "in_flight": in_flight,
                "retry_scheduled": retry_pending,
                "oldest_pending_age_seconds": oldest_age,
            },
            "workers": {
                "by_status": workers_by_status,
            },
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/queue/jobs",
        methods=["GET"],
        doc=Doc(
            summary="List worker jobs",
            description=(
                "List worker-job rows newest-first. Filters: "
                "``state``, ``target_pod_name``, ``target_kind``, "
                "``worker_id``, ``limit`` (clamped to 500)."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def list_queue_jobs(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        state_raw = request.query_params.get("state", None)
        target_pod_name = request.query_params.get(
            "target_pod_name", None,
        )
        target_kind = request.query_params.get("target_kind", None)
        worker_id = request.query_params.get("worker_id", None)
        project_id = request.query_params.get("project_id", None)
        limit_raw = request.query_params.get("limit", None)
        if limit_raw is None or len(limit_raw) == 0:
            limit_value = 50
        else:
            try:
                limit_value = int(limit_raw)
            except (TypeError, ValueError):
                err_msg = "limit must be an integer"
                raise HTTPException(
                    status_code=400, detail=err_msg,
                ) from None
        views = jobservice.list_jobs(
            db_session=db_session,
            state=state_raw,
            target_pod_name=target_pod_name,
            target_kind=target_kind,
            worker_id=worker_id,
            project_id=project_id,
            limit=limit_value,
        )
        body = [_job_view_to_dict(view=v) for v in views]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/queue/jobs/{job_id}",
        methods=["GET"],
        doc=Doc(
            summary="Read one queue job",
            description="Inspect one ``worker_jobs`` row by id.",
        ),
        access_policy=_ADMIN_POLICY,
    )
    def read_queue_job(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        job_id = request.path_params.get("job_id", "")
        view = jobservice.read_job(
            db_session=db_session, job_id=job_id,
        )
        if view is None:
            raise HTTPException(
                status_code=404,
                detail="job not found: {0}".format(job_id),
            ) from None
        body = _job_view_to_dict(view=view)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/queue/jobs/{job_id}/artifacts",
        methods=["GET"],
        doc=Doc(
            summary="List artifacts attached to a job",
            description=(
                "Returns the artifact metadata records (no "
                "content) attached to ``job_id`` oldest-first. "
                "Use ``GET /api/v1/queue/artifacts/{id}/content`` "
                "to download the bytes."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def list_job_artifacts(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        job_id = request.path_params.get("job_id", "")
        views = artifactservice.list_artifacts_for_job(
            db_session=db_session, job_id=job_id,
        )
        body = [_artifact_view_to_dict(view=v) for v in views]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/queue/artifacts/{artifact_id}",
        methods=["GET"],
        doc=Doc(
            summary="Read artifact metadata",
            description=(
                "Returns the metadata record (no content). "
                "Use ``.../content`` for the bytes."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def read_artifact_metadata_endpoint(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        artifact_id = request.path_params.get("artifact_id", "")
        try:
            view = artifactservice.read_artifact_metadata(
                db_session=db_session, artifact_id=artifact_id,
            )
        except ArtifactNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        body = _artifact_view_to_dict(view=view)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/queue/artifacts/{artifact_id}/content",
        methods=["GET"],
        doc=Doc(
            summary="Download artifact content",
            description=(
                "Returns the raw bytes with the recorded "
                "``content_type``. The body is the stored "
                "blob; size is bounded by the inline-storage "
                "cap configured at upload time."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def read_artifact_content_endpoint(request: Request) -> Response:
        db_session = _require_db_session(request=request)
        artifact_id = request.path_params.get("artifact_id", "")
        try:
            view = artifactservice.read_artifact_metadata(
                db_session=db_session, artifact_id=artifact_id,
            )
            content = artifactservice.read_artifact_content(
                db_session=db_session, artifact_id=artifact_id,
            )
        except ArtifactNotFoundError as exc:
            raise HTTPException(
                status_code=404, detail=str(exc),
            ) from exc
        rtnval = Response(
            status_code=200,
            body=content,
            headers={
                "Content-Type": view.content_type,
                "Content-Length": str(view.size_bytes),
                "X-Artifact-Hash": view.content_hash,
                "X-Artifact-Name": view.name,
            },
        )
        return rtnval


    @RestBlueprint.attach_at(
        path="/api/v1/queue/jobs/{job_id}/log/stream",
        methods=["GET"],
        doc=Doc(
            summary="Tail a job's live log",
            description=(
                "Long-poll cursor-based tail. Returns "
                "``{chunks: [...], next_since: N}``. The "
                "consumer persists ``next_since`` and supplies "
                "it as ``?since=N`` on the next call. "
                "Filters: ``since`` (default 0), ``limit`` "
                "(default 200, max 1000)."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def stream_job_log(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        job_id = request.path_params.get("job_id", "")
        since_raw = request.query_params.get("since", None)
        if since_raw is None or len(since_raw) == 0:
            since_value = 0
        else:
            try:
                since_value = int(since_raw)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail="since must be an integer",
                ) from None
        limit_raw = request.query_params.get("limit", None)
        if limit_raw is None or len(limit_raw) == 0:
            limit_value = 200
        else:
            try:
                limit_value = int(limit_raw)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail="limit must be an integer",
                ) from None
        # 404 a missing job so the dashboard can distinguish
        # "no chunks yet" (200 + empty list) from
        # "you've got the wrong job_id".
        job_view = jobservice.read_job(
            db_session=db_session, job_id=job_id,
        )
        if job_view is None:
            raise HTTPException(
                status_code=404,
                detail="job not found: {0}".format(job_id),
            ) from None
        chunks = joblogservice.read_log_chunks(
            db_session=db_session,
            job_id=job_id,
            since_seq=since_value,
            limit=limit_value,
        )
        if len(chunks) > 0:
            next_since = chunks[-1].seq
        else:
            next_since = since_value
        body = {
            "chunks": [
                _log_chunk_view_to_dict(view=v) for v in chunks
            ],
            "next_since": next_since,
        }
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval


    @RestBlueprint.attach_at(
        path="/api/v1/queue/jobs/{job_id}/test-results",
        methods=["GET"],
        doc=Doc(
            summary="List a job's test results",
            description=(
                "Returns every test result attached to the "
                "job, oldest first. Filters: ``outcome`` "
                "(passed/failed/skipped/errored or any custom "
                "value), ``attempt`` (1-indexed)."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def list_job_test_results(request: Request) -> JSONResponse:
        db_session = _require_db_session(request=request)
        job_id = request.path_params.get("job_id", "")
        outcome = request.query_params.get("outcome", None)
        attempt_raw = request.query_params.get("attempt", None)
        attempt_value: Optional[int]
        if attempt_raw is None or len(attempt_raw) == 0:
            attempt_value = None
        else:
            try:
                attempt_value = int(attempt_raw)
            except (TypeError, ValueError):
                raise HTTPException(
                    status_code=400,
                    detail="attempt must be an integer",
                ) from None
        views = testresultservice.list_test_results_for_job(
            db_session=db_session,
            job_id=job_id,
            outcome=outcome,
            attempt=attempt_value,
        )
        body = [_test_result_view_to_dict(view=v) for v in views]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/queue/jobs/{job_id}/test-results/summary",
        methods=["GET"],
        doc=Doc(
            summary="Summarise a job's test results",
            description=(
                "Returns ``{by_outcome, total, passed, failed, "
                "skipped, errored}`` aggregated across every "
                "attempt of the job. Conventional outcomes are "
                "always present (zero buckets included)."
            ),
        ),
        access_policy=_ADMIN_POLICY,
    )
    def summarise_job_test_results(
            request: Request,
        ) -> JSONResponse:
        db_session = _require_db_session(request=request)
        job_id = request.path_params.get("job_id", "")
        body = testresultservice.summarize_test_results_for_job(
            db_session=db_session, job_id=job_id,
        )
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval


def _test_result_view_to_dict(*, view) -> Dict[str, Any]:
    rtnval = {
        "result_id": view.result_id,
        "job_id": view.job_id,
        "worker_id": view.worker_id,
        "attempt": view.attempt,
        "suite_name": view.suite_name,
        "case_name": view.case_name,
        "outcome": view.outcome,
        "duration_seconds": view.duration_seconds,
        "started_at": view.started_at,
        "completed_at": view.completed_at,
        "failure_message": view.failure_message,
        "failure_trace": view.failure_trace,
        "attributes": view.attributes,
    }
    return rtnval


def _log_chunk_view_to_dict(*, view) -> Dict[str, Any]:
    rtnval = {
        "chunk_id": view.chunk_id,
        "job_id": view.job_id,
        "worker_id": view.worker_id,
        "attempt": view.attempt,
        "seq": view.seq,
        "stream": view.stream,
        "text": view.text,
        "created_at": view.created_at,
    }
    return rtnval


def _artifact_view_to_dict(*, view) -> Dict[str, Any]:
    rtnval = {
        "artifact_id": view.artifact_id,
        "job_id": view.job_id,
        "worker_id": view.worker_id,
        "attempt": view.attempt,
        "name": view.name,
        "kind": view.kind,
        "content_type": view.content_type,
        "size_bytes": view.size_bytes,
        "content_hash": view.content_hash,
        "storage_kind": view.storage_kind,
        "attributes": view.attributes,
        "created_at": view.created_at,
    }
    return rtnval
