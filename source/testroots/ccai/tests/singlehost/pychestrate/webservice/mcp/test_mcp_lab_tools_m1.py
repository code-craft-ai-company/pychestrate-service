"""
.. module:: tests.singlehost.pychestrate.webservice.mcp.test_mcp_lab_tools_m1
    :synopsis: Tests for the MCP lab tools and the Streamable HTTP rules
               the endpoint follows.

.. moduleauthor:: Code Craft AI LLC

Audit finding ORG-F19: the MCP endpoint offered four project and health
tools and nothing an AI agent needs to work the lab, and its GET answered
with a JSON descriptor where the transport expects an SSE stream or 405.
The endpoint now offers runs and failures, queue status, RPA jobs and lab
devices, gated like the REST API and the web UI, and answers GET with 405.

Each test drives the tools through ``tools/call`` against a real
in-memory database; only the RBAC decision is patched.

**Feature: MCP lab tools (ORG-F19)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import uuid

from typing import Any, Dict, Iterable, List, Optional, Tuple

import sqlalchemy as sa

from sqlalchemy.orm import sessionmaker

from ccai import testbase
from ccai.testbase.mocking import create_module_patch

from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import (
    Allocation,
    Project as CoreProject,
    PychestrateModelBase,
    Resource,
)
from ccai.pychestrate.webservice.clients.enums import ClientStatus, LivenessState
from ccai.pychestrate.webservice.clients.models import Client
from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.jobs.dispatch import (
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import DispatchCandidate
from ccai.pychestrate.webservice.jobs.dispatch.models import DispatchAttempt, DispatchAttemptStatus
from ccai.pychestrate.webservice.jobs.envelope import (
    EnvelopeSignerBootstrapConfig,
    install_envelope_signer,
)
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.jobs.run.state.enums import RunEvent, RunState
from ccai.pychestrate.webservice.jobs.run.state.models import Run, RunStateAudit
from ccai.pychestrate.webservice.mcp import lab_tools, service_endpoint
from ccai.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus
from ccai.pychestrate.webservice.orchestration.rpa import (
    RpaJobTypeInputs,
    RpaSpecInputs,
    RpaVersionInputs,
    create_spec,
    publish_version,
    register_builtin_extensions as rpa_register,
    register_job_type,
)
from ccai.pychestrate.webservice.orchestration.rpa import service as rpa_service
from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base
from ccai.pychestrate.webservice.security.rbac import rbac_evaluator


ACTOR_ID = "00000000-0000-4000-8000-0000000429a1"
OTHER_USER_ID = "00000000-0000-4000-8000-0000000429b2"
PROJECT_UUID = "00000000-0000-4000-8000-0000000429c3"
LEGACY_PROJECT_REF = "7"
ALL_KEYS = ("system:runs.read", "system:clients.read", "system:rpa.read", "system:rpa.create")


# ===========================================================================
# Harness
# ===========================================================================


class _Principal:
    def __init__(self, user_id: str) -> None:
        self.user_id = user_id
        return


class _Request:
    def __init__(self, *, db_session: Any, user_id: Optional[str] = ACTOR_ID, body: Any = None) -> None:
        self.db_session = db_session
        self.auth_principal = _Principal(user_id) if user_id is not None else None
        self.actor_user_id = user_id
        self.path = service_endpoint.MCP_SERVICE_PATH
        self._body = body
        return

    def json(self) -> Any:
        return self._body


class _Decision:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed
        return


class _Granting:
    """
        Patch the RBAC evaluator so the caller holds exactly ``keys``.
    """

    def __init__(self, keys: Iterable[str]) -> None:
        self._keys = set(keys)
        self._patch = create_module_patch(rbac_evaluator, "check_permission")
        return

    def __enter__(self) -> "_Granting":
        keys = self._keys
        self._patch.activate().configure(
            side_effect=lambda *, db_session, principal, permission_key, now: _Decision(permission_key in keys)
        )
        return self

    def __exit__(self, *exc: Any) -> None:
        self._patch.deactivate()
        return


def _database() -> Any:
    engine = sa.create_engine("sqlite://")
    PychestratePhase1Base.metadata.create_all(engine)
    PychestrateModelBase.metadata.create_all(engine)
    rtnval = sessionmaker(bind=engine)()
    return rtnval


def _call(session: Any, name: str, arguments: Dict[str, Any], *, keys: Iterable[str] = ALL_KEYS,
          user_id: Optional[str] = ACTOR_ID) -> Dict[str, Any]:
    """
        ``tools/call`` ``name`` as a caller holding ``keys``; returns the
        tool result (``structuredContent`` plus ``isError``/``text``).
    """
    message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    with _Granting(keys):
        response = service_endpoint._dispatch_message(
            request=_Request(db_session=session, user_id=user_id), message=message,
        )
    result = response["result"]
    rtnval = dict(result.get("structuredContent") or {})
    rtnval["isError"] = result["isError"]
    rtnval["text"] = result["content"][0]["text"]
    return rtnval


def _run(session: Any, state: RunState, *, project_id: str = PROJECT_UUID, reason: Optional[str] = None) -> str:
    run_id = str(uuid.uuid4())
    session.add(Run(run_id=run_id, project_id=project_id, job_type="rpa", state=state, entered_state_at=utc_now()))
    if reason is not None:
        session.add(RunStateAudit(
            audit_id=str(uuid.uuid4()), run_id=run_id, from_state=RunState.RUNNING, to_state=state,
            event=RunEvent.PROGRESS_OBSERVED,
            actor="client", reason=reason, transitioned_at=utc_now(),
        ))
    session.commit()
    return run_id


def _device(session: Any, *, name: str = "phone-7", metadata: Optional[Dict[str, Any]] = None,
            sensitive: Optional[List[str]] = None) -> int:
    resource = Resource(
        name=name, resource_type="device", metadata_json=metadata or {}, sensitive_fields=sensitive or [],
    )
    session.add(resource)
    session.commit()
    return resource.id


# ===========================================================================
# Transport
# ===========================================================================


def test_get_on_the_endpoint_is_405_and_allows_post():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: GET on the MCP endpoint answers 405 with Allow: POST, as
    the Streamable HTTP transport requires of a server without an SSE
    stream.**
    """
    response = service_endpoint.handle_mcp_service_descriptor(_Request(db_session=None))
    testbase.assert_equal((response.status_code, response.headers.get("Allow")), (405, "POST"))
    return


def test_a_post_of_only_notifications_is_202_with_no_body():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: a POST carrying only notifications is answered 202 with an
    empty body.**
    """
    request = _Request(db_session=None, body={"jsonrpc": "2.0", "method": "notifications/initialized"})
    response = service_endpoint.handle_mcp_service(request)
    testbase.assert_equal((response.status_code, response.body), (202, b""))
    return


def test_tools_that_change_things_are_not_advertised_as_read_only():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: tools/list marks exactly the tools that change state
    (create_project, trigger_rpa_job, check_out_device, check_in_device)
    with readOnlyHint false.**
    """
    response = service_endpoint._dispatch_message(
        request=_Request(db_session=None), message={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    )
    writers = sorted(
        tool["name"] for tool in response["result"]["tools"] if tool["annotations"]["readOnlyHint"] is False
    )
    testbase.assert_equal(writers, ["check_in_device", "check_out_device", "create_project", "trigger_rpa_job"])
    return


# ===========================================================================
# Runs and the queue
# ===========================================================================


def test_list_runs_can_return_only_the_failures():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: list_runs with failed_only returns the failed, lost and
    needs-investigation runs and none of the running or completed ones.**
    """
    session = _database()
    failed = {_run(session, RunState.FAILED), _run(session, RunState.DISPATCH_LOST),
              _run(session, RunState.NEEDS_INVESTIGATION)}
    _run(session, RunState.RUNNING)
    _run(session, RunState.COMPLETED)
    result = _call(session, "list_runs", {"failed_only": True})
    testbase.assert_equal({item["run_id"] for item in result["items"]}, failed)
    return


def test_list_runs_needs_the_runs_read_permission():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: a caller without system:runs.read gets a permission-denied
    tool error naming the permission.**
    """
    session = _database()
    result = _call(session, "list_runs", {}, keys=())
    testbase.assert_equal(
        (result["isError"], "system:runs.read" in result["text"]), (True, True),
    )
    return


def test_get_run_explains_why_a_run_failed():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: get_run returns the run with its state history, including
    the reason recorded when it failed.**
    """
    session = _database()
    run_id = _run(session, RunState.FAILED, reason="pytest exited 2: 3 tests failed")
    result = _call(session, "get_run", {"run_id": run_id})
    testbase.assert_equal(
        (result["state"], [entry["reason"] for entry in result["state_history"]]),
        ("failed", ["pytest exited 2: 3 tests failed"]),
    )
    return


def test_queue_status_counts_what_is_in_flight_and_waiting():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: queue_status counts active runs by state, dispatches still
    waiting for a pod, and failures in the last day.**
    """
    session = _database()
    _run(session, RunState.RUNNING)
    _run(session, RunState.RUNNING)
    _run(session, RunState.PENDING)
    _run(session, RunState.FAILED)
    _run(session, RunState.COMPLETED)
    for status in (DispatchAttemptStatus.PENDING, DispatchAttemptStatus.ACKED):
        session.add(DispatchAttempt(
            attempt_id=str(uuid.uuid4()), run_id=str(uuid.uuid4()), project_id=PROJECT_UUID,
            client_id=str(uuid.uuid4()), pod_id=str(uuid.uuid4()), envelope_id=str(uuid.uuid4()),
            status=status,
        ))
    session.commit()
    result = _call(session, "queue_status", {})
    testbase.assert_equal(
        (result["active_runs"]["running"], result["active_runs"]["pending"], result["active_run_total"],
         result["queued_dispatches"]["pending"], result["failures_last_24h"]),
        (2, 1, 3, 1, 1),
    )
    return


def test_queue_status_reports_client_liveness_only_with_clients_read():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: client liveness counts appear for a caller with
    system:clients.read and are withheld (null) without it.**
    """
    session = _database()
    session.add(Client(
        client_id=str(uuid.uuid4()), project_id=PROJECT_UUID, pod_name="pod-a",
        status=ClientStatus.ACTIVE, liveness_state=LivenessState.ALIVE,
    ))
    session.commit()
    with_permission = _call(session, "queue_status", {})
    without_permission = _call(session, "queue_status", {}, keys=("system:runs.read",))
    testbase.assert_equal(
        (with_permission["clients"]["alive"], without_permission["clients"]), (1, None),
    )
    return


# ===========================================================================
# Lab devices
# ===========================================================================


def test_list_devices_masks_sensitive_metadata():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: a device's sensitive metadata fields are masked in
    list_devices while the rest of its metadata is returned.**
    """
    session = _database()
    _device(session, metadata={"ip": "10.0.4.21", "admin_password": "hunter2"}, sensitive=["admin_password"])
    result = _call(session, "list_devices", {})
    metadata = result["items"][0]["metadata"]
    testbase.assert_equal(
        (metadata["ip"], metadata["admin_password"] != "hunter2"), ("10.0.4.21", True),
    )
    return


def test_a_device_checked_out_through_mcp_can_be_checked_back_in():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: check_out_device allocates the device to the caller and
    check_in_device with the returned allocation id releases it.**
    """
    session = _database()
    resource_id = _device(session)
    checked_out = _call(session, "check_out_device", {"resource_id": resource_id, "timeout_minutes": 60})
    checked_in = _call(session, "check_in_device", {"allocation_id": checked_out["allocation_id"]})
    testbase.assert_equal(
        (checked_out["status"], checked_in["status"], checked_in["allocation_id"]),
        ("active", "released", checked_out["allocation_id"]),
    )
    return


def test_a_device_held_by_someone_else_cannot_be_checked_out():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: check_out_device on a device another user holds
    exclusively is a conflict tool error, not a second allocation.**
    """
    session = _database()
    resource_id = _device(session)
    _call(session, "check_out_device", {"resource_id": resource_id}, user_id=OTHER_USER_ID)
    result = _call(session, "check_out_device", {"resource_id": resource_id})
    active = session.query(Allocation).filter(Allocation.resource_id == resource_id,
                                              Allocation.status == "active").count()
    testbase.assert_equal((result["isError"], active), (True, 1))
    return


def test_only_the_holder_can_check_a_device_in():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: check_in_device for an allocation someone else holds is
    refused and the allocation stays active.**
    """
    session = _database()
    resource_id = _device(session)
    held = _call(session, "check_out_device", {"resource_id": resource_id}, user_id=OTHER_USER_ID)
    result = _call(session, "check_in_device", {"allocation_id": held["allocation_id"]})
    stored = session.get(Allocation, held["allocation_id"])
    testbase.assert_equal((result["isError"], stored.status), (True, "active"))
    return


# ===========================================================================
# RPA
# ===========================================================================


SCHEMA = {"type": "object", "required": ["customer_id"], "properties": {"customer_id": {"type": "integer"}}}


def _prepare_rpa_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    envelope_signer.reset_for_testing()
    rpa_service.set_active_job_dispatcher(dispatcher=None)
    dispatch_register()
    rpa_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev", file_path=None, env_var=None, key_id="test-mcp-lab-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    rpa_service.set_active_job_dispatcher(dispatcher=JobDispatcher(transport=InMemoryTransport()))
    return


def _seed_rpa(session: Any) -> str:
    session.add(CoreProject(id=int(LEGACY_PROJECT_REF), name="demo", owner_id=uuid.UUID(ACTOR_ID), metadata_json={}))
    session.commit()
    register_job_type(
        db_session=session,
        inputs=RpaJobTypeInputs(type_id="invoice-import", display_name="Invoice Import", packet_schema=SCHEMA),
        actor_id=ACTOR_ID,
    )
    publish_version(
        db_session=session, type_id="invoice-import",
        inputs=RpaVersionInputs(version="1.0.0", source_kind="package", source_ref="jobs==1",
                                entrypoint={"command": ["job"]}),
        actor_id=ACTOR_ID,
    )
    spec = create_spec(
        db_session=session, project_id=LEGACY_PROJECT_REF,
        inputs=RpaSpecInputs(name="nightly", type_id="invoice-import"),
        actor_id=ACTOR_ID,
    )
    rtnval = spec.spec_id
    return rtnval


class _Candidates:
    """
        Patch the dispatch candidate resolver the trigger tool uses.
    """

    def __init__(self, candidates: Tuple[DispatchCandidate, ...]) -> None:
        self._candidates = candidates
        self._patch = create_module_patch(lab_tools, "resolve_dispatch_candidates")
        return

    def __enter__(self) -> "_Candidates":
        candidates = self._candidates
        self._patch.activate().configure(
            side_effect=lambda *, db_session, project_id, target_pod_id=None: list(candidates)
        )
        return self

    def __exit__(self, *exc: Any) -> None:
        self._patch.deactivate()
        return


ONE_POD = (
    DispatchCandidate(
        client_id="11111111-1111-4000-8000-0000000429d4",
        pod_id="22222222-2222-4000-8000-0000000429e5",
        capability_tags=tuple(),
        inflight_dispatch_count=0,
        last_dispatched_at_iso="",
    ),
)


def test_trigger_rpa_job_starts_a_job_from_a_specification():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: trigger_rpa_job with a valid packet starts a job for the
    specification, visible to get_rpa_job.**
    """
    _prepare_rpa_runtime()
    session = _database()
    spec_id = _seed_rpa(session)
    with _Candidates(ONE_POD):
        started = _call(session, "trigger_rpa_job", {
            "project_id": LEGACY_PROJECT_REF, "spec_id": spec_id, "work_packet": {"customer_id": 42},
        })
    read_back = _call(session, "get_rpa_job", {"job_id": started["job_id"]})
    testbase.assert_equal(
        (started["isError"], started["spec_id"], read_back["job_id"], read_back["work_packet"]["customer_id"]),
        (False, spec_id, started["job_id"], 42),
    )
    return


def test_trigger_rpa_job_reports_packet_errors_before_looking_for_a_pod():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: a packet that fails the job type's schema is an
    invalid-argument tool error naming the bad path, even with no pod
    available.**
    """
    _prepare_rpa_runtime()
    session = _database()
    spec_id = _seed_rpa(session)
    with _Candidates(tuple()):
        result = _call(session, "trigger_rpa_job", {
            "project_id": LEGACY_PROJECT_REF, "spec_id": spec_id, "work_packet": {"customer_id": "x"},
        })
    testbase.assert_equal((result["isError"], "/customer_id" in result["text"]), (True, True))
    return


def test_trigger_rpa_job_needs_the_rpa_create_permission():
    """
    **Feature: MCP lab tools (ORG-F19)**
    **Property: a caller with only system:rpa.read cannot trigger a job.**
    """
    _prepare_rpa_runtime()
    session = _database()
    spec_id = _seed_rpa(session)
    with _Candidates(ONE_POD):
        result = _call(session, "trigger_rpa_job", {
            "project_id": LEGACY_PROJECT_REF, "spec_id": spec_id, "work_packet": {"customer_id": 42},
        }, keys=("system:rpa.read",))
    testbase.assert_equal((result["isError"], "system:rpa.create" in result["text"]), (True, True))
    return
