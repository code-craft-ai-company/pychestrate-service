"""
.. module:: test_p24l_accesspolicy_m3
    :synopsis: Tests for AccessPolicyMiddleware enforcement.

Boots a real :class:`PychestrateApplication`, points it at an
in-memory file-backed SQLite engine, and exercises gated and
ungated endpoints under three principal shapes:

* anonymous (no ``request.auth``)
* authenticated user with no relevant roles
* authenticated admin with ``system-admin``

Verifies that:

* Ungated endpoints (e.g. GET /api/v1/rbac/permissions) accept all
  three shapes with HTTP 200.
* Gated endpoints (POST /api/v1/projects, POST /api/v1/flows) reject
  anonymous with 401 and reject non-admin with 403.
* Gated endpoints accept the admin with the expected success status
  (201 / 202).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import tempfile
import time

from typing import Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.webworks.authentication.core import (
    AuthenticationContext,
    Principal,
)
from automojo.webworks.routing.request import Request

from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)
from automojo.pychestrate.webservice.pychestrateapplication import (
    PychestrateApplication,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


_FLOWS_WORKFLOW_YAML = """
name: policy-smoke
environment: {}
parameters: {}
flow:
  - task: noop
    tasktype: automojo.taskplus.tasks.runcommand@RunCommand
    command: echo policy
"""


def _make_admin_context() -> AuthenticationContext:
    rtnval = AuthenticationContext(
        principal=Principal(
            identifier="00000000-0000-4000-8000-00000000a001",
            display_name="Admin",
            roles={"system-admin"},
        ),
        scheme="test-injection",
    )
    return rtnval


def _make_user_context() -> AuthenticationContext:
    rtnval = AuthenticationContext(
        principal=Principal(
            identifier="00000000-0000-4000-8000-00000000b001",
            display_name="Bob",
            roles={"project-viewer"},
        ),
        scheme="test-injection",
    )
    return rtnval


def _build_app() -> Tuple[PychestrateApplication, str]:
    """
        Build a fresh app against a file-backed SQLite engine. Caller
        is responsible for unlinking the file.
    """
    reset_phase1_runtime()
    fd, path = tempfile.mkstemp(prefix="pych_p24l_", suffix=".db")
    os.close(fd)
    engine = sa.create_engine("sqlite:///{0}".format(path))
    PychestratePhase1Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    app = PychestrateApplication(
        session_factory=factory,
        register_extensions=False,
        debug=False,
    )
    return app, path


def _wrap_with_auth(
        *,
        app: PychestrateApplication,
        context: Optional[AuthenticationContext],
    ) -> None:
    """
        Wrap the app's dispatcher so every request lands with the
        supplied :class:`AuthenticationContext` (or with ``None``).
    """
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = context
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped
    return


def test_anonymous_request_passes_ungated_endpoint():
    """
    **Feature: P24l AccessPolicy enforcement (M3)**
    **Property: Endpoints without an attached AccessPolicy accept
    anonymous requests as 200.**
    """
    app, path = _build_app()
    _wrap_with_auth(app=app, context=None)
    try:
        request = Request(
            method="GET", path="/api/v1/rbac/permissions",
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 200)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_anonymous_request_rejected_with_401_on_gated_endpoint():
    """
    **Feature: P24l AccessPolicy enforcement (M3)**
    **Property: POST /api/v1/projects (gated by system-admin)
    rejects anonymous requests with 401.**
    """
    app, path = _build_app()
    _wrap_with_auth(app=app, context=None)
    try:
        request = Request(
            method="POST",
            path="/api/v1/projects",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "slug": "denied",
                "display_name": "Denied",
                "description": "",
            }).encode("utf-8"),
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 401)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_authenticated_non_admin_rejected_with_403_on_gated_endpoint():
    """
    **Feature: P24l AccessPolicy enforcement (M3)**
    **Property: A request authenticated with roles other than
    system-admin is rejected with 403 on POST /api/v1/projects.**
    """
    app, path = _build_app()
    _wrap_with_auth(app=app, context=_make_user_context())
    try:
        request = Request(
            method="POST",
            path="/api/v1/projects",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "slug": "denied2",
                "display_name": "Denied",
                "description": "",
            }).encode("utf-8"),
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 403)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_admin_accepted_on_gated_endpoint_create_project():
    """
    **Feature: P24l AccessPolicy enforcement (M3)**
    **Property: A request authenticated with the system-admin role
    is accepted on POST /api/v1/projects with HTTP 201.**
    """
    app, path = _build_app()
    _wrap_with_auth(app=app, context=_make_admin_context())
    try:
        request = Request(
            method="POST",
            path="/api/v1/projects",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "slug": "policy-smoke",
                "display_name": "Policy Smoke",
                "description": "",
            }).encode("utf-8"),
        )
        response = app.dispatcher.dispatch(request=request)
        testbase.assert_equal(response.status_code, 201)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_admin_accepted_on_gated_endpoint_submit_flow():
    """
    **Feature: P24l AccessPolicy enforcement (M3)**
    **Property: A request authenticated with the system-admin role
    is accepted on POST /api/v1/flows with HTTP 202; the same
    request anonymously returns 401.**
    """
    app, path = _build_app()
    _wrap_with_auth(app=app, context=_make_admin_context())
    try:
        admin_request = Request(
            method="POST",
            path="/api/v1/flows",
            headers={"Content-Type": "application/yaml"},
            body=_FLOWS_WORKFLOW_YAML.encode("utf-8"),
        )
        admin_response = app.dispatcher.dispatch(request=admin_request)
        testbase.assert_equal(admin_response.status_code, 202)
        # Wait for the worker to terminate so the test doesn't leak
        # a thread.
        flow_id = json.loads(admin_response.body.decode("utf-8"))["flow_id"]
        end = time.time() + 5.0
        while time.time() < end:
            snapshot = app.flow_runtime.status(flow_id=flow_id)
            if snapshot is None:
                break
            if snapshot.state.value in ("SUCCEEDED", "FAILED"):
                break
            time.sleep(0.05)

        # Now flip to anonymous and confirm 401. We rebuild the app
        # rather than re-wrap (re-wrapping would stack a new wrapper
        # on top of the existing admin wrapper).
        app.flow_runtime.shutdown(wait=True)
        app2, path2 = _build_app()
        _wrap_with_auth(app=app2, context=None)
        try:
            anon_request = Request(
                method="POST",
                path="/api/v1/flows",
                headers={"Content-Type": "application/yaml"},
                body=_FLOWS_WORKFLOW_YAML.encode("utf-8"),
            )
            anon_response = app2.dispatcher.dispatch(request=anon_request)
            testbase.assert_equal(anon_response.status_code, 401)
        finally:
            app2.flow_runtime.shutdown(wait=True)
            os.unlink(path2)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return
