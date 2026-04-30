"""
.. module:: test_p24h_end_to_end_application_smoke_m3
    :synopsis: End-to-end smoke for PychestrateApplication + flow runtime.

Boots the full :class:`PychestrateApplication` against an in-memory
SQLite engine, dispatches a real REST request through every layer
(router + DbSessionMiddleware + PychestrateSessionMiddleware +
controller), and exercises the taskplus :class:`FlowRuntime` through
:class:`FlowsBlueprint`.

These tests are the canary that catches large-scale regressions when
the bootstrap, middleware order, blueprint registration, or runtime
wiring are broken.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import time

from typing import Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.orchestration.flowruntime import (
    FlowRuntime,
)
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


_SMOKE_WORKFLOW_YAML = """
name: smoke-workflow
environment: {}
parameters: {}
flow:
  - task: noop
    tasktype: automojo.taskplus.tasks.runcommand@RunCommand
    command: echo hello
"""


def _build_app() -> Tuple[PychestrateApplication, FlowRuntime]:
    """
        Construct a fresh :class:`PychestrateApplication` against an
        in-memory SQLite engine and a per-test :class:`FlowRuntime`.

        :returns: Tuple of ``(app, flow_runtime)``. The runtime is
                  attached to every request via a tiny pre-pipeline
                  shim so submissions don't leak into the module-level
                  singleton.
    """
    # Reset the phase-1 extension registry so re-registering inside
    # PychestrateApplication.__init__ does not collide with a frozen
    # state left behind by a prior test in the run.
    reset_phase1_runtime()

    engine = sa.create_engine("sqlite://")
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)

    # The fixtures reset already calls register_phase1_builtin_extensions,
    # so we tell the application not to re-register them.
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )

    flow_runtime = FlowRuntime(max_workers=2)

    # Wrap the dispatcher so every request gets a per-test runtime
    # before pipeline middleware touches it.
    original_dispatch = app.dispatcher.dispatch

    def _dispatch_with_runtime(*, request: Request):
        request.flow_runtime = flow_runtime
        rtnval = original_dispatch(request=request)
        return rtnval

    app.dispatcher.dispatch = _dispatch_with_runtime

    return app, flow_runtime


def test_application_boot_registers_full_route_surface():
    """
    **Feature: P24h end-to-end application bootstrap (M3)**
    **Property: After boot the router exposes every blueprint's
    routes, including the taskplus FlowsBlueprint surface.**
    """
    app, flow_runtime = _build_app()
    try:
        registered_paths = [route[0] for route in app.router._routes]

        # Pick representative routes from each major blueprint group.
        expected_present = [
            "/api/v1/auth/logout",
            "/api/v1/identity/users",
            "/api/v1/flags",
            "/api/v1/rbac/permissions",
            "/api/v1/clients",
            "/api/v1/enrollment-tokens",
            "/api/v1/audit",
            "/api/v1/secrets",
            "/api/v1/retention/policies",
            "/api/v1/project-templates",
            "/api/v1/notifications/channels",
            "/api/v1/clients-inventory",
            "/api/v1/tags/taxonomies",
            "/api/v1/variables/effective",
            "/api/v1/projects",
            "/api/v1/flows",
        ]

        missing = []
        for path in expected_present:
            if path not in registered_paths:
                missing.append(path)
        testbase.assert_equal(missing, [])
    finally:
        flow_runtime.shutdown(wait=True)
    return


def test_rbac_permissions_endpoint_round_trips_through_pipeline():
    """
    **Feature: P24h end-to-end application bootstrap (M3)**
    **Property: A real GET /api/v1/rbac/permissions request flows
    through the full pipeline (router + DbSessionMiddleware +
    PychestrateSessionMiddleware) and returns the registered
    permission catalog.**
    """
    app, flow_runtime = _build_app()
    try:
        request = Request(method="GET", path="/api/v1/rbac/permissions")
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 200)
        body = json.loads(response.body.decode("utf-8"))
        testbase.assert_equal(isinstance(body, list), True)
        testbase.assert_equal(len(body) > 0, True)
        first = body[0]
        testbase.assert_equal("permission_key" in first, True)
    finally:
        flow_runtime.shutdown(wait=True)
    return


def test_flow_submission_round_trips_through_taskplus_runtime():
    """
    **Feature: P24h end-to-end application bootstrap (M3)**
    **Property: POST /api/v1/flows with a one-task workflow returns
    202 with a fresh flow_id; polling GET /api/v1/flows/{id} shortly
    afterwards reports state=SUCCEEDED, populated started_at /
    completed_at, and result_code=0.**
    """
    app, flow_runtime = _build_app()
    try:
        submit_request = Request(
            method="POST",
            path="/api/v1/flows",
            headers={"Content-Type": "application/yaml"},
            body=_SMOKE_WORKFLOW_YAML.encode("utf-8"),
        )
        submit_response = app.dispatcher.dispatch(request=submit_request)
        testbase.assert_equal(submit_response.status_code, 202)
        submit_body = json.loads(submit_response.body.decode("utf-8"))
        flow_id = submit_body["flow_id"]
        # The worker pool may have already picked the submission up
        # by the time the response is read back, so accept either.
        testbase.assert_equal(
            submit_body["state"] in ("PENDING", "RUNNING"), True,
        )

        # Poll until the worker finishes (echo finishes quickly).
        # Cap at 5 seconds so a stuck worker fails the test loudly.
        deadline = time.time() + 5.0
        final_state = None
        while time.time() < deadline:
            read_request = Request(
                method="GET",
                path="/api/v1/flows/{}".format(flow_id),
            )
            read_response = app.dispatcher.dispatch(request=read_request)
            testbase.assert_equal(read_response.status_code, 200)
            read_body = json.loads(read_response.body.decode("utf-8"))
            final_state = read_body["state"]
            if final_state in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(0.05)

        testbase.assert_equal(final_state, "SUCCEEDED")
        testbase.assert_equal(read_body["result_code"], 0)
        testbase.assert_equal(read_body["started_at"] is not None, True)
        testbase.assert_equal(read_body["completed_at"] is not None, True)
        testbase.assert_equal(read_body["error_text"] is None, True)
    finally:
        flow_runtime.shutdown(wait=True)
    return


def test_flow_list_returns_submitted_flow():
    """
    **Feature: P24h end-to-end application bootstrap (M3)**
    **Property: After a submission, GET /api/v1/flows includes the
    new flow_id in the list.**
    """
    app, flow_runtime = _build_app()
    try:
        submit_request = Request(
            method="POST",
            path="/api/v1/flows",
            headers={"Content-Type": "application/yaml"},
            body=_SMOKE_WORKFLOW_YAML.encode("utf-8"),
        )
        submit_response = app.dispatcher.dispatch(request=submit_request)
        testbase.assert_equal(submit_response.status_code, 202)
        flow_id = json.loads(submit_response.body.decode("utf-8"))["flow_id"]

        list_request = Request(method="GET", path="/api/v1/flows")
        list_response = app.dispatcher.dispatch(request=list_request)
        testbase.assert_equal(list_response.status_code, 200)
        list_body = json.loads(list_response.body.decode("utf-8"))
        testbase.assert_equal(isinstance(list_body, list), True)
        ids = [entry["flow_id"] for entry in list_body]
        testbase.assert_equal(flow_id in ids, True)
    finally:
        flow_runtime.shutdown(wait=True)
    return


def test_unknown_flow_id_returns_404():
    """
    **Feature: P24h end-to-end application bootstrap (M3)**
    **Property: GET /api/v1/flows/{unknown} returns 404 with the
    flow-submission-not-found detail.**
    """
    app, flow_runtime = _build_app()
    try:
        request = Request(
            method="GET",
            path="/api/v1/flows/00000000-0000-0000-0000-000000000000",
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 404)
    finally:
        flow_runtime.shutdown(wait=True)
    return
