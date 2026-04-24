"""
.. module:: test_variable_service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-global-variables M1 service surface.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.messaging.event_bus import subscribe
from automojo.pychestrate.webservice.variables import service as variable_service
from automojo.pychestrate.webservice.variables.exceptions import (
    InvalidVariableScopeError,
    InvalidVariableValueError,
    VariableNotFoundError,
)
from automojo.pychestrate.webservice.variables.models import (
    VariableScope,
    VariableValueType,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)
from automojo.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


def test_set_variable_system_scope_round_trip_and_event():
    """
    **Feature: 2-global-variables (M1)**
    **Property: set_variable at SYSTEM scope persists + publishes
    entity.variable.set.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    received = []
    subscribe(topic="entity.variable.set", subscriber=lambda e: received.append(e))

    binding = variable_service.set_variable(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="max_concurrency",
        value=42,
        value_type=VariableValueType.INTEGER,
        actor_user_id=None,
    )

    testbase.assert_equal(binding.name, "max_concurrency")
    testbase.assert_equal(binding.value_text, "42")
    testbase.assert_equal(len(received), 1)
    testbase.assert_equal(received[0].payload["name"], "max_concurrency")

    fetched = variable_service.get_variable(
        db_session=session,
        scope=VariableScope.SYSTEM,
        scope_id="",
        name="max_concurrency",
    )
    testbase.assert_equal(variable_service.decode_binding_value(binding=fetched), 42)
    return


def test_set_variable_project_scope_requires_id():
    """
    **Feature: 2-global-variables (M1)**
    **Property: PROJECT scope with empty scope_id raises
    InvalidVariableScopeError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        variable_service.set_variable(
            db_session=session,
            scope=VariableScope.PROJECT,
            scope_id="",
            name="needs_project",
            value="hello",
            value_type=VariableValueType.STRING,
            actor_user_id=None,
        )
    except InvalidVariableScopeError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_set_variable_type_mismatch_raises():
    """
    **Feature: 2-global-variables (M1)**
    **Property: value_type=INTEGER with a non-int value raises
    InvalidVariableValueError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    raised = False
    try:
        variable_service.set_variable(
            db_session=session,
            scope=VariableScope.SYSTEM,
            scope_id="",
            name="bad_int",
            value="not-an-int",
            value_type=VariableValueType.INTEGER,
            actor_user_id=None,
        )
    except InvalidVariableValueError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_unset_variable_emits_and_is_idempotent():
    """
    **Feature: 2-global-variables (M1)**
    **Property: unset_variable emits entity.variable.unset; a second
    call raises VariableNotFoundError.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    variable_service.set_variable(
        db_session=session,
        scope=VariableScope.PROJECT,
        scope_id=project_id,
        name="feature_a",
        value=True,
        value_type=VariableValueType.BOOLEAN,
        actor_user_id=None,
    )

    received = []
    subscribe(topic="entity.variable.unset", subscriber=lambda e: received.append(e))

    variable_service.unset_variable(
        db_session=session,
        scope=VariableScope.PROJECT,
        scope_id=project_id,
        name="feature_a",
        actor_user_id=None,
    )

    testbase.assert_equal(len(received), 1)

    raised = False
    try:
        variable_service.unset_variable(
            db_session=session,
            scope=VariableScope.PROJECT,
            scope_id=project_id,
            name="feature_a",
            actor_user_id=None,
        )
    except VariableNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
