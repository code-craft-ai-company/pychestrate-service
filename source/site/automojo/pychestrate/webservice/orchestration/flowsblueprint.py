"""
.. module:: pychestrate.webservice.orchestration.flowsblueprint
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: REST API v1 controller for /api/v1/flows.

.. moduleauthor:: Automation Mojo LLC

Bridges the pychestrate REST surface to :class:`FlowRuntime`, which in
turn drives :mod:`automojo.taskplus`.

Endpoints:

* ``POST   /api/v1/flows`` — submit a workflow (YAML in body).
* ``GET    /api/v1/flows`` — list every tracked submission.
* ``GET    /api/v1/flows/{flow_id}`` — read one submission's status.

Submission state lives in the :data:`default_flow_runtime` singleton
unless callers override the dependency in tests.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import Any, Dict

from automojo.errors.exceptions import ConfigurationError

from automojo.webworks.endpoints.doc import Doc
from automojo.webworks.endpoints.restblueprint import RestBlueprint
from automojo.webworks.routing.exceptions import HTTPException
from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import JSONResponse

from automojo.pychestrate.webservice.orchestration.flowruntime import (
    FlowRuntime,
    FlowSubmission,
    default_flow_runtime,
)


FLOWS_BASE_PATH = "/api/v1/flows"


def _submission_to_dict(*, submission: FlowSubmission) -> Dict[str, Any]:
    """
        Render a :class:`FlowSubmission` as the REST response dict.
    """
    rtnval = {
        "flow_id": submission.flow_id,
        "name": submission.name,
        "state": submission.state.value,
        "submitted_at": submission.submitted_at,
        "started_at": submission.started_at,
        "completed_at": submission.completed_at,
        "result_code": submission.result_code,
        "error_text": submission.error_text,
    }
    return rtnval


def _resolve_runtime(*, request: Request) -> FlowRuntime:
    """
        Return the :class:`FlowRuntime` to use for this request.

        Tests may attach an override via ``request.flow_runtime`` to
        avoid sharing the module-level singleton across runs. The
        production path uses :data:`default_flow_runtime`.
    """
    override = getattr(request, "flow_runtime", None)
    if override is not None:
        return override
    rtnval = default_flow_runtime
    return rtnval


def _read_workflow_yaml(*, request: Request) -> str:
    """
        Pull the workflow YAML body from the request.

        Accepts either ``Content-Type: application/yaml`` /
        ``text/yaml`` (raw body) or
        ``Content-Type: application/json`` (with a ``workflow_yaml``
        string field).

        :raises HTTPException: 400 when the body is empty or the JSON
                               envelope is missing the field.
    """
    raw_body = request.body
    if raw_body is None:
        raise HTTPException(status_code=400, detail="request body required")
    if len(raw_body) == 0:
        raise HTTPException(status_code=400, detail="request body required")

    content_type = request.content_type
    if content_type is None:
        content_type = ""
    lower_content_type = content_type.lower()

    if "application/json" in lower_content_type:
        try:
            decoded = request.json()
        except Exception as exc:
            err_msg = "request body must be valid JSON"
            raise HTTPException(
                status_code=400, detail=err_msg,
            ) from exc
        if not isinstance(decoded, dict):
            raise HTTPException(
                status_code=400,
                detail="JSON body must be an object with workflow_yaml",
            )
        workflow_yaml = decoded.get("workflow_yaml", None)
        if workflow_yaml is None:
            raise HTTPException(
                status_code=400,
                detail="JSON body must include 'workflow_yaml'",
            )
        if not isinstance(workflow_yaml, str):
            raise HTTPException(
                status_code=400,
                detail="'workflow_yaml' must be a string",
            )
        rtnval = workflow_yaml
        return rtnval

    # Default: treat the raw body as the YAML document
    rtnval = raw_body.decode("utf-8")
    return rtnval


class FlowsBlueprint(RestBlueprint):
    """
        Blueprint grouping the v1 ``/api/v1/flows`` endpoints.
    """

    base_path = FLOWS_BASE_PATH
    tags = ["flows", "v1", "orchestration"]

    @RestBlueprint.attach_at(
        path="/api/v1/flows",
        methods=["POST"],
        doc=Doc(
            summary="Submit workflow for execution",
            description=(
                "Submit a taskplus workflow for asynchronous execution. "
                "The body is either raw YAML (Content-Type: application"
                "/yaml or text/yaml) or a JSON envelope "
                "{\"workflow_yaml\": \"...\"}. The endpoint returns 202 "
                "immediately with a flow_id; poll "
                "GET /api/v1/flows/{flow_id} to read status."
            ),
        ),
    )
    def submit_flow(request: Request) -> JSONResponse:
        """
            Submit a workflow for asynchronous execution.
        """
        runtime = _resolve_runtime(request=request)
        workflow_yaml = _read_workflow_yaml(request=request)

        try:
            flow_id = runtime.submit_workflow_yaml(
                workflow_yaml=workflow_yaml,
            )
        except ConfigurationError as exc:
            raise HTTPException(
                status_code=400, detail=str(exc),
            ) from exc

        submission = runtime.status(flow_id=flow_id)
        if submission is None:
            err_lines = [
                "Workflow accepted but immediate status read failed.",
                "FLOW_ID: {}".format(flow_id),
            ]
            err_msg = os.linesep.join(err_lines)
            raise HTTPException(status_code=500, detail=err_msg)

        body = _submission_to_dict(submission=submission)
        rtnval = JSONResponse(content=body, status_code=202)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/flows",
        methods=["GET"],
        doc=Doc(
            summary="List flow submissions",
            description=(
                "Return every submission tracked by the runtime, "
                "ordered by submitted_at descending."
            ),
        ),
    )
    def list_flows(request: Request) -> JSONResponse:
        """
            List every tracked submission.
        """
        runtime = _resolve_runtime(request=request)
        submissions = runtime.list_submissions()

        body = [
            _submission_to_dict(submission=s) for s in submissions
        ]
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/flows/{flow_id}",
        methods=["GET"],
        doc=Doc(
            summary="Read flow submission",
            description=(
                "Return the tracked state of one submission. The "
                "state field cycles PENDING -> RUNNING -> SUCCEEDED "
                "/ FAILED."
            ),
        ),
    )
    def read_flow(request: Request) -> JSONResponse:
        """
            Read a single submission's state.
        """
        runtime = _resolve_runtime(request=request)
        flow_id = request.path_params.get("flow_id", "")

        submission = runtime.status(flow_id=flow_id)
        if submission is None:
            err_msg = "Flow submission not found: {}".format(flow_id)
            raise HTTPException(status_code=404, detail=err_msg)

        body = _submission_to_dict(submission=submission)
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval

    @RestBlueprint.attach_at(
        path="/api/v1/flows/{flow_id}/log",
        methods=["GET"],
        doc=Doc(
            summary="Read flow log",
            description=(
                "Return captured stdout / log output for one "
                "submission. Available only when the runtime is "
                "wired with a DB session_factory; in-memory-only "
                "runtimes return 404 here."
            ),
        ),
    )
    def read_flow_log(request: Request) -> JSONResponse:
        """
            Return the log_text persisted alongside a submission.
        """
        runtime = _resolve_runtime(request=request)
        flow_id = request.path_params.get("flow_id", "")

        # Confirm the submission exists first so we can distinguish
        # "unknown id" from "log capture not enabled".
        submission = runtime.status(flow_id=flow_id)
        if submission is None:
            err_msg = "Flow submission not found: {}".format(flow_id)
            raise HTTPException(status_code=404, detail=err_msg)

        log_text = runtime.read_log(flow_id=flow_id)
        if log_text is None:
            log_text = ""
        body = {"flow_id": flow_id, "log_text": log_text}
        rtnval = JSONResponse(content=body, status_code=200)
        return rtnval
