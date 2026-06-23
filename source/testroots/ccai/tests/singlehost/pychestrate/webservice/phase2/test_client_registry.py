"""
.. module:: test_client_registry
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 3-client-registry M1 service surface.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.clients.enums import (
    ClientStatus,
    LivenessState,
)
from ccai.pychestrate.webservice.clients.exceptions import (
    ClientAlreadyExistsError,
    ClientNotFoundError,
    InvalidAttributeValueError,
    UnknownAttributeKindError,
)
from ccai.pychestrate.webservice.clients.registry.service import (
    AttributeUpdate,
    get_client,
    get_client_by_scope,
    list_clients,
    record_heartbeat,
    register_client,
    set_liveness_state,
    update_attributes,
)
from ccai.pychestrate.webservice.messaging.event_bus import subscribe

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    reset_phase1_runtime,
)


def test_register_client_round_trip_and_event():
    """
    **Feature: 3-client-registry (M1)**
    **Property: register_client persists a row and publishes
    entity.client.registered.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.client.registered", subscriber=lambda e: received.append(e))

    project_id = new_uuid()
    client = register_client(
        db_session=session,
        project_id=project_id,
        pod_name="test-pod-a",
        bearer_token_hash=b"fake-digest",
        agent_version="1.0.0",
        transport_name="http",
    )

    testbase.assert_equal(str(client.project_id), project_id)
    testbase.assert_equal(client.pod_name, "test-pod-a")
    testbase.assert_equal(client.status, ClientStatus.ACTIVE)
    testbase.assert_equal(client.liveness_state, LivenessState.ALIVE)
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["pod_name"], "test-pod-a")
    return


def test_register_client_duplicate_scope_raises():
    """
    **Feature: 3-client-registry (M1)**
    **Property: A second register_client for the same (project, pod)
    pair raises ClientAlreadyExistsError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()
    project_id = new_uuid()

    register_client(
        db_session=session, project_id=project_id, pod_name="dup-pod",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )

    raised = False
    try:
        register_client(
            db_session=session, project_id=project_id, pod_name="dup-pod",
            bearer_token_hash=None, agent_version=None, transport_name=None,
        )
    except ClientAlreadyExistsError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_record_heartbeat_updates_last_seen():
    """
    **Feature: 3-client-registry (M1)**
    **Property: record_heartbeat updates last_seen + last_agent_version
    and publishes entity.client.heartbeat.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.client.heartbeat", subscriber=lambda e: received.append(e))

    project_id = new_uuid()
    client = register_client(
        db_session=session, project_id=project_id, pod_name="hb-pod",
        bearer_token_hash=None, agent_version="1.0.0", transport_name="http",
    )
    client_id = str(client.client_id)

    now = datetime.now(timezone.utc)
    record_heartbeat(
        db_session=session, client_id=client_id,
        received_at=now, agent_version="1.1.0", transport_name="ws",
    )

    view = get_client(db_session=session, client_id=client_id)
    testbase.assert_equal(view.last_agent_version, "1.1.0")
    testbase.assert_equal(view.transport_name, "ws")
    testbase.assert_equal(len(received), 1)
    return


def test_stale_heartbeat_is_ignored():
    """
    **Feature: 3-client-registry (M1)**
    **Property: A heartbeat with received_at <= stored last_seen is a
    no-op (monotonic guard).**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    client = register_client(
        db_session=session, project_id=project_id, pod_name="stale-pod",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )
    client_id = str(client.client_id)

    t_newer = datetime.now(timezone.utc)
    t_older = t_newer - timedelta(seconds=60)

    record_heartbeat(
        db_session=session, client_id=client_id, received_at=t_newer,
        agent_version="new", transport_name="http",
    )
    record_heartbeat(
        db_session=session, client_id=client_id, received_at=t_older,
        agent_version="older", transport_name="http",
    )

    view = get_client(db_session=session, client_id=client_id)
    testbase.assert_equal(view.last_agent_version, "new")
    return


def test_heartbeat_reheals_degraded():
    """
    **Feature: 3-client-registry (M1)**
    **Property: A heartbeat on a DEGRADED client transitions it back
    to ALIVE and clears degraded_at.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    client = register_client(
        db_session=session, project_id=project_id, pod_name="heal-pod",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )
    client_id = str(client.client_id)

    set_liveness_state(
        db_session=session, client_id=client_id,
        liveness_state=LivenessState.DEGRADED,
    )

    record_heartbeat(
        db_session=session, client_id=client_id,
        received_at=datetime.now(timezone.utc),
        agent_version="x", transport_name=None,
    )

    view = get_client(db_session=session, client_id=client_id)
    testbase.assert_equal(view.liveness_state, LivenessState.ALIVE)
    testbase.assert_equal(view.degraded_at_iso, None)
    return


def test_set_liveness_state_publishes_and_idempotent():
    """
    **Feature: 3-client-registry (M1)**
    **Property: set_liveness_state publishes on real transition and
    is a no-op on the same state.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.client.liveness_changed", subscriber=lambda e: received.append(e))

    project_id = new_uuid()
    client = register_client(
        db_session=session, project_id=project_id, pod_name="liveness-pod",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )
    client_id = str(client.client_id)

    set_liveness_state(
        db_session=session, client_id=client_id,
        liveness_state=LivenessState.DEGRADED,
    )
    set_liveness_state(
        db_session=session, client_id=client_id,
        liveness_state=LivenessState.DEGRADED,
    )

    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["new_state"], "DEGRADED")
    return


def test_update_attributes_validates_and_publishes():
    """
    **Feature: 3-client-registry (M1)**
    **Property: update_attributes validates values against the registered
    ClientAttributeExtension schema, upserts on success, and publishes
    entity.client.attributes_changed.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.client.attributes_changed", subscriber=lambda e: received.append(e))

    project_id = new_uuid()
    client = register_client(
        db_session=session, project_id=project_id, pod_name="attr-pod",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )
    client_id = str(client.client_id)

    update_attributes(
        db_session=session, client_id=client_id,
        updates=[
            AttributeUpdate(kind="os", value={"family": "linux", "version": "6.1"}),
            AttributeUpdate(kind="cpu_arch", value="arm64"),
        ],
    )

    view = get_client(db_session=session, client_id=client_id)
    testbase.assert_equal(view.attributes["cpu_arch"], "arm64")
    testbase.assert_equal(view.attributes["os"]["family"], "linux")
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(sorted(received[0].payload["kinds"]), ["cpu_arch", "os"])
    return


def test_update_attributes_rejects_unknown_kind():
    """
    **Feature: 3-client-registry (M1)**
    **Property: An update for a kind that has no registered
    ClientAttributeExtension raises UnknownAttributeKindError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    client = register_client(
        db_session=session, project_id=project_id, pod_name="unknown-attr",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )

    raised = False
    try:
        update_attributes(
            db_session=session, client_id=str(client.client_id),
            updates=[AttributeUpdate(kind="does.not.exist", value="x")],
        )
    except UnknownAttributeKindError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_update_attributes_rejects_schema_violations():
    """
    **Feature: 3-client-registry (M1)**
    **Property: An update whose value violates the declared schema
    raises InvalidAttributeValueError and no row is written.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    client = register_client(
        db_session=session, project_id=project_id, pod_name="bad-attr",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )

    raised = False
    try:
        update_attributes(
            db_session=session, client_id=str(client.client_id),
            updates=[AttributeUpdate(kind="cpu_arch", value="not-a-real-arch")],
        )
    except InvalidAttributeValueError:
        raised = True
    testbase.assert_equal(raised, True)

    view = get_client(db_session=session, client_id=str(client.client_id))
    testbase.assert_equal("cpu_arch" in view.attributes, False)
    return


def test_update_attributes_revision_token_mismatch():
    """
    **Feature: 3-client-registry (M1)**
    **Property: A caller that passes the wrong expected_revision_token
    is rejected with InvalidAttributeValueError.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    client = register_client(
        db_session=session, project_id=project_id, pod_name="rev-pod",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )

    raised = False
    try:
        update_attributes(
            db_session=session, client_id=str(client.client_id),
            updates=[AttributeUpdate(kind="cpu_arch", value="x86_64")],
            expected_revision_token="this-is-not-the-real-token",
        )
    except InvalidAttributeValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_clients_filters():
    """
    **Feature: 3-client-registry (M1)**
    **Property: list_clients honors project_id + status + liveness filters.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    project_a = new_uuid()
    project_b = new_uuid()

    register_client(
        db_session=session, project_id=project_a, pod_name="a-1",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )
    register_client(
        db_session=session, project_id=project_a, pod_name="a-2",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )
    register_client(
        db_session=session, project_id=project_b, pod_name="b-1",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )

    only_a = list_clients(db_session=session, project_id=project_a)
    testbase.assert_equal(len(only_a), 2)

    only_alive = list_clients(db_session=session, liveness_state=LivenessState.ALIVE)
    testbase.assert_equal(len(only_alive), 3)
    return


def test_get_client_by_scope_and_not_found():
    """
    **Feature: 3-client-registry (M1)**
    **Property: get_client_by_scope resolves; a missing scope raises.**
    """
    reset_phase1_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    register_client(
        db_session=session, project_id=project_id, pod_name="scope-pod",
        bearer_token_hash=None, agent_version=None, transport_name=None,
    )

    view = get_client_by_scope(
        db_session=session, project_id=project_id, pod_name="scope-pod",
    )
    testbase.assert_equal(view.pod_name, "scope-pod")

    raised = False
    try:
        get_client_by_scope(
            db_session=session, project_id=project_id, pod_name="does-not-exist",
        )
    except ClientNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
