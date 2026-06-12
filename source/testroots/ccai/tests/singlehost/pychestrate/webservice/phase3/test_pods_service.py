"""
.. module:: test_pods_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the Layer-3 pod services.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.messaging.event_bus import subscribe
from ccai.pychestrate.webservice.pods import definitions_service
from ccai.pychestrate.webservice.pods import dynamic_service
from ccai.pychestrate.webservice.pods import lifecycle_service
from ccai.pychestrate.webservice.pods import scoped_config_service
from ccai.pychestrate.webservice.pods import static_service
from ccai.pychestrate.webservice.pods import topology_service
from ccai.pychestrate.webservice.pods.exceptions import (
    PodRegistrationRejectedError,
    PodSpecValidationError,
    PodStateTransitionError,
)
from ccai.pychestrate.webservice.pods.lifecycle_service import LifecycleEventKind
from ccai.pychestrate.webservice.pods.models import PodState

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from ccai.tests.singlehost.pychestrate.webservice.phase3.fixtures import (
    reset_phase3_runtime,
)


def _simple_spec():
    rtnval = {
        "members": [
            {"name": "host-a", "kind": "linux_host", "hostname": "a.example.com"},
            {"name": "switch-1", "kind": "network_switch", "vendor": "generic"},
        ],
        "links": [{"source": "host-a", "target": "switch-1", "label": "eth0"}],
    }
    return rtnval


def test_create_pod_definition_round_trip_and_event():
    """
    **Feature: 3-pod-definitions (M1)**
    **Property: create_pod_definition persists version 1 and publishes
    entity.pod.definition_created.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.pod.definition_created", subscriber=lambda e: received.append(e))

    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="alpha-pod", spec=_simple_spec(),
        actor_user_id=None,
    )
    testbase.assert_equal(definition.pod_name, "alpha-pod")
    testbase.assert_equal(int(definition.current_version), 1)
    testbase.assert_equal(len(received), 1)
    return


def test_create_pod_definition_rejects_invalid_spec():
    """
    **Feature: 3-pod-definitions (M1)**
    **Property: Specs lacking members fail validation.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        definitions_service.create_pod_definition(
            db_session=session, project_id=new_uuid(),
            pod_name="bad-pod", spec={"foo": "bar"},
            actor_user_id=None,
        )
    except PodSpecValidationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_lifecycle_transitions_and_state_changed_event():
    """
    **Feature: 3-pod-lifecycle (M1)**
    **Property: apply_transition walks DEFINED → READY → IN_USE →
    RELEASED and publishes entity.pod.state_changed.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.pod.state_changed", subscriber=lambda e: received.append(e))

    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="life-pod", spec=_simple_spec(), actor_user_id=None,
    )
    lifecycle_service.initialize_pod_state(db_session=session, pod_id=definition.pod_id)
    lifecycle_service.apply_transition(
        db_session=session, pod_id=definition.pod_id,
        event_kind=LifecycleEventKind.REGISTERED, event_payload={}, actor=None,
    )
    lifecycle_service.apply_transition(
        db_session=session, pod_id=definition.pod_id,
        event_kind=LifecycleEventKind.ACQUIRE, event_payload={"run_id": "r1"},
        actor=None,
    )
    lifecycle_service.apply_transition(
        db_session=session, pod_id=definition.pod_id,
        event_kind=LifecycleEventKind.DRAIN, event_payload={}, actor=None,
    )
    lifecycle_service.apply_transition(
        db_session=session, pod_id=definition.pod_id,
        event_kind=LifecycleEventKind.DEREGISTER, event_payload={}, actor=None,
    )

    final = lifecycle_service.read_state(db_session=session, pod_id=definition.pod_id)
    testbase.assert_equal(final.state, PodState.RELEASED)
    testbase.assert_equal(len(received), 4)
    return


def test_lifecycle_rejects_impossible_transition():
    """
    **Feature: 3-pod-lifecycle (M1)**
    **Property: An invalid transition raises PodStateTransitionError.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="reject-pod", spec=_simple_spec(), actor_user_id=None,
    )
    lifecycle_service.initialize_pod_state(db_session=session, pod_id=definition.pod_id)

    raised = False
    try:
        lifecycle_service.apply_transition(
            db_session=session, pod_id=definition.pod_id,
            event_kind=LifecycleEventKind.ACQUIRE, event_payload={}, actor=None,
        )
    except PodStateTransitionError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_static_pod_registration_happy_path_and_mismatch():
    """
    **Feature: 3-static-pods (M1)**
    **Property: register_static_pod succeeds when report matches and
    raises PodRegistrationRejectedError on mismatch.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.pod.registered", subscriber=lambda e: received.append(e))

    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="reg-pod", spec=_simple_spec(), actor_user_id=None,
    )
    registration = static_service.register_static_pod(
        db_session=session, pod_id=definition.pod_id, client_id=None,
        member_reports=[
            {"name": "host-a", "kind": "linux_host"},
            {"name": "switch-1", "kind": "network_switch"},
        ],
        actor=None,
    )
    testbase.assert_equal(str(registration.pod_id), str(definition.pod_id))
    testbase.assert_equal(len(received), 1)

    raised = False
    try:
        static_service.register_static_pod(
            db_session=session, pod_id=definition.pod_id, client_id=None,
            member_reports=[{"name": "host-a", "kind": "linux_host"}],
            actor=None,
        )
    except PodRegistrationRejectedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_topology_composition_embeds_renderer_hints():
    """
    **Feature: 3-pod-topology-view (M1)**
    **Property: compose_topology builds a graph with a member per spec
    entry and matched renderer hints.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    definition = definitions_service.create_pod_definition(
        db_session=session, project_id=new_uuid(),
        pod_name="topo-pod", spec=_simple_spec(), actor_user_id=None,
    )
    graph = topology_service.compose_topology(
        db_session=session, pod_id=definition.pod_id,
    )
    kinds = sorted([m.kind for m in graph.members])
    testbase.assert_equal(kinds, ["linux_host", "network_switch"])
    testbase.assert_equal(graph.members[0].hint.get("icon") in ("server", "switch", "generic"), True)
    testbase.assert_equal(len(graph.etag) > 0, True)
    return


def test_scoped_config_set_and_purge_on_released():
    """
    **Feature: 3-pod-scoped-config (M1)**
    **Property: set_scoped_variable persists + publishes, purge_for_run
    removes rows.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    run_id = new_uuid()
    pod_id = new_uuid()
    scoped_config_service.set_scoped_variable(
        db_session=session, run_id=run_id, pod_id=pod_id,
        name="k", value=1, value_schema=None, locked=False,
        actor_user_id=None,
    )
    rows = scoped_config_service.list_scoped_variables(
        db_session=session, run_id=run_id, pod_id=pod_id,
    )
    testbase.assert_equal(len(rows), 1)

    removed = scoped_config_service.purge_for_run(db_session=session, run_id=run_id)
    testbase.assert_equal(removed, 1)
    rows = scoped_config_service.list_scoped_variables(
        db_session=session, run_id=run_id, pod_id=None,
    )
    testbase.assert_equal(len(rows), 0)
    return


def test_dynamic_pod_materialization_inline_creates_definition():
    """
    **Feature: 3-dynamic-pods (M1)**
    **Property: start_materialization inline-renders a template and
    reaches READY, creating a pod definition.**
    """
    reset_phase3_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    template = dynamic_service.create_pod_template(
        db_session=session, project_id=project_id,
        name="tpl", template_kind="json_substitute",
        source_json={
            "members": [
                {"name": "host-$param.suffix", "kind": "linux_host",
                 "hostname": "host-$param.suffix.example.com"},
            ],
        },
        parameter_schema=None,
        actor_user_id=None,
    )

    materialization = dynamic_service.start_materialization(
        db_session=session, template_id=str(template.template_id),
        parameters={"suffix": "zzz"}, actor_user_id=None,
    )
    testbase.assert_equal(materialization.state.value, "READY")
    testbase.assert_equal(materialization.pod_id is not None, True)
    return
