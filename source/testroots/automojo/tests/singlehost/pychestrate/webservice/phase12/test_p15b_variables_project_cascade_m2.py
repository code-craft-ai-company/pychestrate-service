"""
.. module:: test_p15b_variables_project_cascade_m2
    :synopsis: Tests for P15b — 2-global-variables M2
               project-deleted cascade purge.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from sqlalchemy.orm import sessionmaker

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    publish,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.variables import (
    bus_subscriber as variable_bus_subscriber,
    repository as variable_repository,
    service as variable_service,
)
from automojo.pychestrate.webservice.variables.events import (
    VariableEventTopics,
)
from automojo.pychestrate.webservice.variables.models import (
    VariableScope,
    VariableValueType,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


def _prepare_runtime() -> None:
    reset_event_bus()
    variable_bus_subscriber.reset_for_testing()
    return


def _seed_project_variables(*, session, project_id: str) -> None:
    variable_service.set_variable(
        db_session=session,
        scope=VariableScope.PROJECT,
        scope_id=project_id,
        name="ENV",
        value="prod",
        value_type=VariableValueType.STRING,
        actor_user_id=None,
    )
    variable_service.set_variable(
        db_session=session,
        scope=VariableScope.PROJECT,
        scope_id=project_id,
        name="MAX_REPLICAS",
        value=10,
        value_type=VariableValueType.INTEGER,
        actor_user_id=None,
    )
    return


# -------------------------------------
# cascade_project_deleted (direct call)
# -------------------------------------

def test_cascade_purges_every_project_scoped_binding():
    """
    **Feature: 2-global-variables (M2)**
    **Property: cascade_project_deleted purges every
    PROJECT-scoped binding for the given project and emits
    VARIABLE_UNSET per row.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    project_id = "proj-" + new_uuid()
    _seed_project_variables(session=session, project_id=project_id)
    received: List[EntityEvent] = []
    subscribe(
        topic=VariableEventTopics.VARIABLE_UNSET,
        subscriber=lambda e: received.append(e),
    )

    purged = variable_bus_subscriber.cascade_project_deleted(
        db_session=session,
        project_id=project_id,
    )
    testbase.assert_equal(purged, 2)
    remaining = variable_repository.list_for_scope(
        db_session=session,
        scope=VariableScope.PROJECT,
        scope_id=project_id,
    )
    testbase.assert_equal(len(remaining), 0)
    testbase.assert_equal(len(received), 2)
    return


def test_cascade_no_op_when_no_bindings():
    """
    **Feature: 2-global-variables (M2)**
    **Property: cascade_project_deleted on a project with no
    PROJECT-scoped bindings is a no-op and emits nothing.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=VariableEventTopics.VARIABLE_UNSET,
        subscriber=lambda e: received.append(e),
    )
    purged = variable_bus_subscriber.cascade_project_deleted(
        db_session=session,
        project_id="proj-empty",
    )
    testbase.assert_equal(purged, 0)
    testbase.assert_equal(len(received), 0)
    return


def test_cascade_does_not_touch_other_projects():
    """
    **Feature: 2-global-variables (M2)**
    **Property: cascade_project_deleted only purges bindings
    for the named project; bindings on other projects stay
    intact.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    project_a = "proj-a-" + new_uuid()
    project_b = "proj-b-" + new_uuid()
    _seed_project_variables(session=session, project_id=project_a)
    _seed_project_variables(session=session, project_id=project_b)
    purged = variable_bus_subscriber.cascade_project_deleted(
        db_session=session,
        project_id=project_a,
    )
    testbase.assert_equal(purged, 2)
    remaining_b = variable_repository.list_for_scope(
        db_session=session,
        scope=VariableScope.PROJECT,
        scope_id=project_b,
    )
    testbase.assert_equal(len(remaining_b), 2)
    return


def test_cascade_does_not_touch_system_scoped_bindings():
    """
    **Feature: 2-global-variables (M2)**
    **Property: SYSTEM-scoped bindings are immune to
    project-deletion cascades.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    project_id = "proj-" + new_uuid()
    _seed_project_variables(session=session, project_id=project_id)
    variable_service.set_variable(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="GLOBAL_FLAG",
        value="on",
        value_type=VariableValueType.STRING,
        actor_user_id=None,
    )
    variable_bus_subscriber.cascade_project_deleted(
        db_session=session,
        project_id=project_id,
    )
    remaining_system = variable_repository.list_for_scope(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
    )
    testbase.assert_equal(len(remaining_system), 1)
    return


def test_cascade_emit_carries_canonical_payload():
    """
    **Feature: 2-global-variables (M2)**
    **Property: each VARIABLE_UNSET emit carries scope /
    scope_id / name / reason='project_deleted' /
    actor_user_id.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    project_id = "proj-" + new_uuid()
    _seed_project_variables(session=session, project_id=project_id)
    received: List[EntityEvent] = []
    subscribe(
        topic=VariableEventTopics.VARIABLE_UNSET,
        subscriber=lambda e: received.append(e),
    )
    actor_id = new_uuid()
    variable_bus_subscriber.cascade_project_deleted(
        db_session=session,
        project_id=project_id,
        actor_user_id=actor_id,
    )
    for evt in received:
        testbase.assert_equal(evt.payload["scope"], "PROJECT")
        testbase.assert_equal(evt.payload["scope_id"], project_id)
        testbase.assert_equal(evt.payload["reason"], "project_deleted")
        testbase.assert_equal(evt.payload["actor_user_id"], actor_id)
    return


# -------------------------------------
# wire_bus_subscribers — end-to-end
# -------------------------------------

def test_wire_bus_subscribers_runs_cascade_on_publish():
    """
    **Feature: 2-global-variables (M2)**
    **Property: a published entity.project.deleted event is
    consumed by the registered handler and purges the
    project's variables.**
    """
    _prepare_runtime()
    engine, session = build_in_memory_session()
    project_id = "proj-" + new_uuid()
    _seed_project_variables(session=session, project_id=project_id)

    def _factory():
        return sessionmaker(bind=engine)()

    variable_bus_subscriber.wire_bus_subscribers(
        session_factory=_factory,
    )
    publish(event=EntityEvent(
        topic="entity.project.deleted",
        payload={
            "project_id": project_id,
            "actor_user_id": None,
        },
        source_event_id=new_uuid(),
    ))

    fresh = sessionmaker(bind=engine)()
    try:
        remaining = variable_repository.list_for_scope(
            db_session=fresh,
            scope=VariableScope.PROJECT,
            scope_id=project_id,
        )
        testbase.assert_equal(len(remaining), 0)
    finally:
        fresh.close()
    return


def test_wire_bus_subscribers_idempotent():
    """
    **Feature: 2-global-variables (M2)**
    **Property: wire_bus_subscribers can be called twice
    without double-handling — a single project.deleted emit
    only purges the bindings once.**
    """
    _prepare_runtime()
    engine, session = build_in_memory_session()
    project_id = "proj-" + new_uuid()
    _seed_project_variables(session=session, project_id=project_id)

    def _factory():
        return sessionmaker(bind=engine)()

    variable_bus_subscriber.wire_bus_subscribers(
        session_factory=_factory,
    )
    variable_bus_subscriber.wire_bus_subscribers(
        session_factory=_factory,
    )
    received: List[EntityEvent] = []
    subscribe(
        topic=VariableEventTopics.VARIABLE_UNSET,
        subscriber=lambda e: received.append(e),
    )
    publish(event=EntityEvent(
        topic="entity.project.deleted",
        payload={"project_id": project_id, "actor_user_id": None},
        source_event_id=new_uuid(),
    ))
    # Two seeded bindings → two emits even if subscriber is
    # registered twice the cascade is gated by the install
    # latch so the cascade runs once.
    testbase.assert_equal(len(received), 2)
    return


def test_wire_handler_skips_payload_without_project_id():
    """
    **Feature: 2-global-variables (M2)**
    **Property: a project.deleted emit without a project_id
    in the payload is silently skipped — no crash, no
    cascade.**
    """
    _prepare_runtime()
    engine, _session = build_in_memory_session()

    def _factory():
        return sessionmaker(bind=engine)()

    variable_bus_subscriber.wire_bus_subscribers(
        session_factory=_factory,
    )
    received: List[EntityEvent] = []
    subscribe(
        topic=VariableEventTopics.VARIABLE_UNSET,
        subscriber=lambda e: received.append(e),
    )
    publish(event=EntityEvent(
        topic="entity.project.deleted",
        payload={"actor_user_id": None},
        source_event_id=new_uuid(),
    ))
    testbase.assert_equal(len(received), 0)
    return
