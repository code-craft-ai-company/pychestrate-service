"""
.. module:: test_m2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for Layer-3 M2 behavior.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.agents import (
    capability_service,
    protocol_service,
    upgrade_service,
)
from ccai.pychestrate.webservice.agents.bus_subscriber import (
    wire_bus_subscribers as wire_agents_bus,
)
from ccai.pychestrate.webservice.agents.capability_matcher import (
    find_clients_matching,
)
from ccai.pychestrate.webservice.agents.inventory_service import read_inventory
from ccai.pychestrate.webservice.agents.models import (
    ClientInventoryChangeLog,
    RolloutStageState,
    RolloutState,
    UpgradeOfferOutcome,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent, publish
from ccai.pychestrate.webservice.pods import (
    bus_subscriber as pods_bus,
    definitions_service,
    lifecycle_service,
    scoped_config_service,
    static_service,
    topology_service,
)
from ccai.pychestrate.webservice.pods.lifecycle_service import LifecycleEventKind
from ccai.pychestrate.webservice.pods.models import (
    PodState,
    RegistrationState,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    session_for,
)
from ccai.tests.singlehost.pychestrate.webservice.phase3.fixtures import (
    reset_phase3_runtime,
)


def _spec():
    rtnval = {
        "members": [
            {"name": "host-a", "kind": "linux_host", "hostname": "a.example.com"},
        ],
        "links": [],
    }
    return rtnval


def test_pod_definition_update_bumps_version():
    """
    **Feature: 3-pod-definitions (M2)**
    **Property: update_pod_definition appends version 2 and bumps
    current_version.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="u-pod", spec=_spec(), actor_user_id=None,
    )

    new_spec = {
        "members": [
            {"name": "host-a", "kind": "linux_host", "hostname": "b.example.com"},
            {"name": "host-b", "kind": "linux_host", "hostname": "c.example.com"},
        ],
        "links": [],
    }
    version = definitions_service.update_pod_definition(
        db_session=session, pod_id=str(definition.pod_id),
        spec=new_spec, actor_user_id=None,
    )
    testbase.assert_equal(int(version.version), 2)
    fresh = definitions_service.read_pod_definition(
        db_session=session, pod_id=str(definition.pod_id),
    )
    testbase.assert_equal(int(fresh.current_version), 2)
    return


def test_pod_definition_soft_delete_emits_event():
    """
    **Feature: 3-pod-definitions (M2)**
    **Property: soft_delete_pod_definition emits entity.pod.definition_deleted.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    received = []
    from ccai.pychestrate.webservice.messaging.event_bus import subscribe
    subscribe(topic="entity.pod.definition_deleted", subscriber=lambda e: received.append(e))

    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="del-pod", spec=_spec(), actor_user_id=None,
    )
    definitions_service.soft_delete_pod_definition(
        db_session=session, pod_id=str(definition.pod_id), actor_user_id=None,
    )
    testbase.assert_equal(len(received), 1)
    return


def test_pod_registration_drives_lifecycle_to_ready():
    """
    **Feature: 3-pod-lifecycle + 3-static-pods (M2)**
    **Property: entity.pod.registered subscriber initializes runtime state
    and drives DEFINED → READY.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    def factory():
        return session_for(engine=_engine)

    pods_bus.wire_bus_subscribers(session_factory=factory)

    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="life-pod", spec=_spec(), actor_user_id=None,
    )
    static_service.register_static_pod(
        db_session=session, pod_id=str(definition.pod_id), client_id=None,
        member_reports=[{"name": "host-a", "kind": "linux_host"}],
        actor=None,
    )

    fresh = session_for(engine=_engine)
    state_row = lifecycle_service.read_state(db_session=fresh, pod_id=str(definition.pod_id))
    testbase.assert_equal(state_row.state, PodState.READY)
    return


def test_client_liveness_lost_marks_registration_client_lost():
    """
    **Feature: 3-static-pods (M2)**
    **Property: entity.client.liveness_changed{LOST} transitions the
    matching registration to CLIENT_LOST.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    def factory():
        return session_for(engine=_engine)

    pods_bus.wire_bus_subscribers(session_factory=factory)

    client_id = new_uuid()
    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="lost-pod", spec=_spec(), actor_user_id=None,
    )
    static_service.register_static_pod(
        db_session=session, pod_id=str(definition.pod_id), client_id=client_id,
        member_reports=[{"name": "host-a", "kind": "linux_host"}], actor=None,
    )

    publish(event=EntityEvent(
        topic="entity.client.liveness_changed",
        payload={"client_id": client_id, "new_state": "LOST"},
        source_event_id=new_uuid(),
    ))

    fresh = session_for(engine=_engine)
    active = (
        fresh.query(static_service.PodRegistration)
        .filter(static_service.PodRegistration.pod_id == definition.pod_id)
        .first()
    )
    testbase.assert_equal(active.state, RegistrationState.CLIENT_LOST)
    return


def test_topology_cache_is_invalidated_by_definition_change():
    """
    **Feature: 3-pod-topology-view (M2)**
    **Property: The cache is invalidated when a new definition version
    is created.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    def factory():
        return session_for(engine=_engine)

    pods_bus.wire_bus_subscribers(session_factory=factory)
    topology_service.reset_cache_for_testing()

    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="cache-pod", spec=_spec(), actor_user_id=None,
    )
    graph_v1 = topology_service.compose_topology(
        db_session=session, pod_id=str(definition.pod_id),
    )

    definitions_service.update_pod_definition(
        db_session=session, pod_id=str(definition.pod_id),
        spec={
            "members": [
                {"name": "host-a", "kind": "linux_host", "hostname": "a.example.com"},
                {"name": "host-b", "kind": "linux_host", "hostname": "b.example.com"},
            ],
            "links": [],
        },
        actor_user_id=None,
    )

    fresh = session_for(engine=_engine)
    graph_v2 = topology_service.compose_topology(db_session=fresh, pod_id=str(definition.pod_id))
    testbase.assert_equal(graph_v2.etag != graph_v1.etag, True)
    testbase.assert_equal(len(graph_v2.members), 2)
    return


def test_scoped_config_bearer_issuance():
    """
    **Feature: 3-pod-scoped-config (M2)**
    **Property: issue_bearer persists a :class:`PodScopedBearer` row.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    bearer = scoped_config_service.issue_bearer(
        db_session=session, run_id=new_uuid(), pod_id=new_uuid(),
        secret_ref="secret://db-root#v1", policy={"reason": "test"},
        expires_at=None,
    )
    testbase.assert_equal(bearer.secret_ref, "secret://db-root#v1")
    testbase.assert_equal(bearer.consumed, False)
    return


def test_capability_matcher_predicates():
    """
    **Feature: 3-client-capability-advertisement (M2)**
    **Property: find_clients_matching honors has(kind) + kind.path=value.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    a = new_uuid()
    b = new_uuid()
    capability_service.apply_advertisement(
        db_session=session, client_id=a,
        advertisements=[
            {"kind": "toolchain", "value": {"gcc": "13"}},
            {"kind": "concurrency", "value": {"max_parallel_jobs": 8}},
        ],
        actor_user_id=None,
    )
    capability_service.apply_advertisement(
        db_session=session, client_id=b,
        advertisements=[
            {"kind": "toolchain", "value": {"gcc": "12"}},
            {"kind": "concurrency", "value": {"max_parallel_jobs": 2}},
        ],
        actor_user_id=None,
    )

    matched = find_clients_matching(
        db_session=session, predicates=["has(toolchain)", "concurrency.max_parallel_jobs=8"],
    )
    testbase.assert_equal(matched, [a])
    return


def test_heartbeat_subscriber_appends_inventory_change_log():
    """
    **Feature: 3-client-inventory-ui (M2)**
    **Property: entity.client.heartbeat appends a change-log row.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    def factory():
        return session_for(engine=_engine)

    wire_agents_bus(session_factory=factory)

    client_id = new_uuid()
    publish(event=EntityEvent(
        topic="entity.client.heartbeat",
        payload={"client_id": client_id, "agent_version": "1.0.0"},
        source_event_id=new_uuid(),
    ))

    fresh = session_for(engine=_engine)
    rows = fresh.query(ClientInventoryChangeLog).filter(
        ClientInventoryChangeLog.client_id == client_id,
    ).all()
    testbase.assert_equal(len(rows) >= 1, True)
    return


def test_rollout_stage_and_halt_resume_flow():
    """
    **Feature: 3-agent-upgrade-channel (M2)**
    **Property: add_rollout_stage + start_rollout_stage + halt/resume
    move through the expected state transitions.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    rollout = upgrade_service.draft_rollout(
        db_session=session, version="2.3.4",
        artifact_source="object_store",
        artifact_ref="objstore://a.tar.gz", signature=None,
        actor_user_id=None,
    )
    # Set rollout ACTIVE manually for the halt test path.
    rollout.state = RolloutState.ACTIVE
    session.add(rollout)
    session.commit()

    stage = upgrade_service.add_rollout_stage(
        db_session=session, rollout_id=str(rollout.rollout_id),
        rollout_policy="fixed_set", target_size=2,
    )
    testbase.assert_equal(stage.state, RolloutStageState.PENDING)

    candidates = [new_uuid() for _ in range(4)]
    offers = upgrade_service.start_rollout_stage(
        db_session=session, stage_id=str(stage.stage_id),
        candidate_client_ids=candidates,
    )
    testbase.assert_equal(len(offers), 2)

    halted = upgrade_service.halt_rollout(
        db_session=session, rollout_id=str(rollout.rollout_id),
        actor_user_id=None,
    )
    testbase.assert_equal(halted.state, RolloutState.HALTED)

    resumed = upgrade_service.resume_rollout(
        db_session=session, rollout_id=str(rollout.rollout_id),
        actor_user_id=None,
    )
    testbase.assert_equal(resumed.state, RolloutState.ACTIVE)
    return


def test_heartbeat_marks_upgrade_offer_succeeded():
    """
    **Feature: 3-agent-upgrade-channel (M2)**
    **Property: A heartbeat carrying the rolled-out agent_version marks
    the outstanding offer for that client SUCCEEDED.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    def factory():
        return session_for(engine=_engine)

    wire_agents_bus(session_factory=factory)

    rollout = upgrade_service.draft_rollout(
        db_session=session, version="9.9.9",
        artifact_source="object_store",
        artifact_ref="objstore://9.9.9.tar.gz", signature=None,
        actor_user_id=None,
    )
    client_id = new_uuid()
    offers = upgrade_service.start_rollout(
        db_session=session, rollout_id=str(rollout.rollout_id),
        candidate_client_ids=[client_id], target_size=1,
        actor_user_id=None,
    )
    testbase.assert_equal(len(offers), 1)

    publish(event=EntityEvent(
        topic="entity.client.heartbeat",
        payload={"client_id": client_id, "agent_version": "9.9.9"},
        source_event_id=new_uuid(),
    ))

    fresh = session_for(engine=_engine)
    updated = (
        fresh.query(upgrade_service.AgentUpgradeOffer)
        .filter(upgrade_service.AgentUpgradeOffer.offer_id == offers[0].offer_id)
        .first()
    )
    testbase.assert_equal(updated.outcome, UpgradeOfferOutcome.SUCCEEDED)
    return
