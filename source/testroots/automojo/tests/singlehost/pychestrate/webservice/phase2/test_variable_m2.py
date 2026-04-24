"""
.. module:: test_variable_m2
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for 2-global-variables M2 scope chain + dereferencer.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.variables import service as variable_service
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


def test_effective_resolution_prefers_innermost_scope():
    """
    **Feature: 2-global-variables (M2)**
    **Property: resolve_effective prefers job → pipeline → project → system.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    pipeline_id = new_uuid()
    job_id = new_uuid()

    variable_service.set_variable(
        db_session=session, scope=VariableScope.SYSTEM, scope_id="",
        name="level", value="system",
        value_type=VariableValueType.STRING, actor_user_id=None,
    )
    variable_service.set_variable(
        db_session=session, scope=VariableScope.PROJECT, scope_id=project_id,
        name="level", value="project",
        value_type=VariableValueType.STRING, actor_user_id=None,
    )

    value = variable_service.resolve_effective(
        db_session=session, name="level",
        project_id=project_id, pipeline_id=pipeline_id, job_id=job_id,
        dereference_secrets=False,
    )
    testbase.assert_equal(value, "project")

    variable_service.set_variable(
        db_session=session, scope=VariableScope.JOB, scope_id=job_id,
        name="level", value="job",
        value_type=VariableValueType.STRING, actor_user_id=None,
    )

    value2 = variable_service.resolve_effective(
        db_session=session, name="level",
        project_id=project_id, pipeline_id=pipeline_id, job_id=job_id,
        dereference_secrets=False,
    )
    testbase.assert_equal(value2, "job")
    return


def test_trace_marks_presence_per_scope():
    """
    **Feature: 2-global-variables (M2)**
    **Property: build_trace returns an entry per scope with binding or None.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    variable_service.set_variable(
        db_session=session, scope=VariableScope.PROJECT, scope_id=project_id,
        name="key", value="v",
        value_type=VariableValueType.STRING, actor_user_id=None,
    )

    trace = variable_service.build_trace(
        db_session=session, name="key",
        project_id=project_id, pipeline_id="pipe-1", job_id="job-1",
    )
    scopes_present = [e["scope"] for e in trace if e["binding"] is not None]
    testbase.assert_equal("PROJECT" in scopes_present, True)
    return


def test_secret_ref_dereference_invokes_registered_impl():
    """
    **Feature: 2-global-variables (M2)**
    **Property: resolve_effective with dereference_secrets=True routes
    a SECRET_REF value through the registered dereferencer.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    variable_service.set_variable(
        db_session=session, scope=VariableScope.SYSTEM, scope_id="",
        name="db_password",
        value="secret://mydb#v2",
        value_type=VariableValueType.SECRET_REF,
        actor_user_id=None,
    )

    result = variable_service.resolve_effective(
        db_session=session, name="db_password",
        project_id=None, pipeline_id=None, job_id=None,
        dereference_secrets=True,
    )
    testbase.assert_equal(result["name"], "mydb")
    testbase.assert_equal(result["version"], "v2")
    testbase.assert_equal(result["resolved_via"], "VaultSecretRefDereferencer")
    return
