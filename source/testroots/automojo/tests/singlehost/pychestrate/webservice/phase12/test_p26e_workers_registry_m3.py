"""
.. module:: test_p26e_workers_registry_m3
    :synopsis: End-to-end tests for the worker registry surface.

Boots the full :class:`PychestrateApplication`, drives:

* admin POSTs /api/v1/workers/register to pre-register a
  local-process worker;
* admin lists, reads, drains, and deletes workers;
* an agent (bearer-token authed) POSTs /api/v1/workers/register +
  heartbeat for a remote-machine worker, with auto-link of
  client_id from the bearer principal;
* anonymous / non-admin requests get the expected 401/403.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import importlib.util
import json
import os
import tempfile

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
from automojo.pychestrate.webservice.secrets.secret_bytes import SecretBytes
from automojo.pychestrate.webservice.security.auth.pepper_loader import (
    reset_active_pepper_for_testing,
    set_active_pepper,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    reset_phase1_runtime,
)


def _build_app() -> Tuple[PychestrateApplication, str]:
    reset_phase1_runtime()
    reset_active_pepper_for_testing()
    set_active_pepper(pepper=SecretBytes(b"p26e-test-pepper"))
    fd, path = tempfile.mkstemp(prefix="pych_p26e_", suffix=".db")
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


def _admin_context() -> AuthenticationContext:
    return AuthenticationContext(
        principal=Principal(
            identifier="00000000-0000-4000-8000-00000000e000",
            display_name="Admin",
            roles={"system-admin"},
        ),
        scheme="test-injection",
    )


def _agent_context(*, client_id: str, project_id: str) -> AuthenticationContext:
    return AuthenticationContext(
        principal=Principal(
            identifier=client_id,
            display_name="agent:test-pod",
            roles={"agent"},
        ),
        scheme="bearer-client",
        attributes={
            "client_id": client_id,
            "project_id": project_id,
            "pod_name": "test-pod",
        },
    )


def _wrap(*, app, context: Optional[AuthenticationContext]) -> None:
    original = app.dispatcher.dispatch

    def _wrapped(*, request):
        request.auth = context
        rtnval = original(request=request)
        return rtnval

    app.dispatcher.dispatch = _wrapped
    return


def test_admin_registers_lists_reads_drains_and_deregisters_local_worker():
    """
    **Feature: P26e worker registry (M3)**
    **Property: Full lifecycle round-trip via the admin path —
    register -> list -> read -> drain -> delete.**
    """
    app, path = _build_app()
    _wrap(app=app, context=_admin_context())
    try:
        # Register
        register_response = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/register",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "name": "local-worker-1",
                "kind": "local-process",
                "attributes": {"pool": "default"},
            }).encode(),
        ))
        testbase.assert_equal(register_response.status_code, 201)
        registered = json.loads(register_response.body.decode())
        worker_id = registered["worker_id"]
        testbase.assert_equal(registered["kind"], "local-process")
        testbase.assert_equal(registered["status"], "idle")

        # List
        list_response = app.dispatcher.dispatch(request=Request(
            method="GET", path="/api/v1/workers",
        ))
        testbase.assert_equal(list_response.status_code, 200)
        listed = json.loads(list_response.body.decode())
        ids = [w["worker_id"] for w in listed]
        testbase.assert_equal(worker_id in ids, True)

        # Read
        read_response = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/workers/{0}".format(worker_id),
        ))
        testbase.assert_equal(read_response.status_code, 200)
        read_body = json.loads(read_response.body.decode())
        testbase.assert_equal(read_body["worker_id"], worker_id)

        # Drain
        drain_response = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/drain".format(worker_id),
            body=b"",
        ))
        testbase.assert_equal(drain_response.status_code, 200)
        drained = json.loads(drain_response.body.decode())
        testbase.assert_equal(drained["status"], "draining")

        # Deregister
        delete_response = app.dispatcher.dispatch(request=Request(
            method="DELETE",
            path="/api/v1/workers/{0}".format(worker_id),
        ))
        testbase.assert_equal(delete_response.status_code, 204)

        # Confirm deletion via 404
        gone_response = app.dispatcher.dispatch(request=Request(
            method="GET",
            path="/api/v1/workers/{0}".format(worker_id),
        ))
        testbase.assert_equal(gone_response.status_code, 404)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_agent_self_registration_links_client_id_from_bearer_principal():
    """
    **Feature: P26e worker registry (M3)**
    **Property: When an agent (bearer principal) registers a
    worker, the handler auto-links client_id and project_id from
    the principal attributes so the agent can't create workers in
    foreign projects.**
    """
    app, path = _build_app()
    agent = _agent_context(
        client_id="00000000-0000-4000-8000-00000000ee00",
        project_id="00000000-0000-4000-8000-00000000ee99",
    )
    _wrap(app=app, context=agent)
    try:
        register_response = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/register",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "name": "remote-worker-1",
                "kind": "remote-machine",
            }).encode(),
        ))
        testbase.assert_equal(register_response.status_code, 201)
        registered = json.loads(register_response.body.decode())
        testbase.assert_equal(registered["kind"], "remote-machine")
        testbase.assert_equal(
            registered["client_id"],
            agent.attributes["client_id"],
        )
        testbase.assert_equal(
            registered["project_id"],
            agent.attributes["project_id"],
        )
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_agent_can_heartbeat_their_worker():
    """
    **Feature: P26e worker registry (M3)**
    **Property: Heartbeat with the agent role updates
    last_heartbeat_at and accepts an optional status flip from
    idle -> running.**
    """
    app, path = _build_app()
    agent = _agent_context(
        client_id="00000000-0000-4000-8000-00000000ef00",
        project_id="00000000-0000-4000-8000-00000000ef99",
    )
    _wrap(app=app, context=agent)
    try:
        register = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/register",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "name": "remote-worker-2", "kind": "remote-machine",
            }).encode(),
        ))
        worker_id = json.loads(register.body.decode())["worker_id"]

        heartbeat = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/heartbeat".format(worker_id),
            headers={"Content-Type": "application/json"},
            body=json.dumps({"status": "running"}).encode(),
        ))
        testbase.assert_equal(heartbeat.status_code, 200)
        body = json.loads(heartbeat.body.decode())
        testbase.assert_equal(body["status"], "running")
        testbase.assert_equal(body["last_heartbeat_at"] is not None, True)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_anonymous_register_returns_401():
    """
    **Feature: P26e worker registry (M3)**
    **Property: Unauthenticated POST /api/v1/workers/register
    returns 401 (the gate accepts admin or agent only).**
    """
    app, path = _build_app()
    _wrap(app=app, context=None)
    try:
        response = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/register",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "name": "denied", "kind": "local-process",
            }).encode(),
        ))
        testbase.assert_equal(response.status_code, 401)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return


def test_agent_cannot_drain_worker():
    """
    **Feature: P26e worker registry (M3)**
    **Property: The drain endpoint is admin-only; an agent token
    that can register workers cannot drain them.**
    """
    app, path = _build_app()
    agent = _agent_context(
        client_id="00000000-0000-4000-8000-00000000eaaa",
        project_id="00000000-0000-4000-8000-00000000eaab",
    )
    _wrap(app=app, context=agent)
    try:
        register = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/register",
            headers={"Content-Type": "application/json"},
            body=json.dumps({
                "name": "blocked-from-drain",
                "kind": "remote-machine",
            }).encode(),
        ))
        worker_id = json.loads(register.body.decode())["worker_id"]

        drain = app.dispatcher.dispatch(request=Request(
            method="POST",
            path="/api/v1/workers/{0}/drain".format(worker_id),
            body=b"",
        ))
        testbase.assert_equal(drain.status_code, 403)
    finally:
        app.flow_runtime.shutdown(wait=True)
        os.unlink(path)
    return
