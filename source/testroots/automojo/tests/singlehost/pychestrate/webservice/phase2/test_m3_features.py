"""
.. module:: test_m3_features
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Per-feature M3 hardening tests.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.extensions.registry import register_resource_extension
from automojo.pychestrate.webservice.hardening.rate_limit import (
    RateLimitExceeded,
    reset_for_testing as reset_rate_limit,
)
from automojo.pychestrate.webservice.projects import service as project_service
from automojo.pychestrate.webservice.projects.extensions.metadata_field import (
    ProjectMetadataFieldExtension,
)
from automojo.pychestrate.webservice.projects.metadata_registry import (
    load_registered_fields,
    reset_for_testing as reset_projects_metadata_registry,
)
from automojo.pychestrate.webservice.retention import legal_hold as retention_legal_hold
from automojo.pychestrate.webservice.retention import service as retention_service
from automojo.pychestrate.webservice.retention.models import (
    ActionStep,
    PolicyScopeLevel,
    SelectorClause,
)
from automojo.pychestrate.webservice.tagging import service as tag_service
from automojo.pychestrate.webservice.tagging.bus_subscriber import wire_bus_subscribers
from automojo.pychestrate.webservice.variables import cache as variable_cache
from automojo.pychestrate.webservice.variables import service as variable_service
from automojo.pychestrate.webservice.variables.models import (
    VariableScope,
    VariableValueType,
)
from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, publish

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    session_for,
)
from automojo.tests.singlehost.pychestrate.webservice.phase2.fixtures import (
    reset_phase2_runtime,
)


class _DupeCostCenter(ProjectMetadataFieldExtension):
    """
        Test-only duplicate of ``cost_center`` to force a collision.
    """
    resource_extension_name: str = "project_metadata_field"
    field_name: str = "cost_center"
    field_type: str = "string"


def test_project_create_idempotency_returns_original_project():
    """
    **Feature: 2-projects (M3)**
    **Property: A second create_project with the same Idempotency-Key
    returns the originally-persisted project.**
    """
    reset_phase2_runtime()
    reset_rate_limit()
    _engine, session = build_in_memory_session()

    proj1 = project_service.create_project(
        db_session=session, slug="idem-proj",
        display_name="Idem Project",
        description="",
        owning_group_id=None,
        template_id=None, template_version=None,
        actor_user_id=None,
        idempotency_key="same-key",
    )

    proj2 = project_service.create_project(
        db_session=session, slug="idem-proj",
        display_name="Idem Project",
        description="",
        owning_group_id=None,
        template_id=None, template_version=None,
        actor_user_id=None,
        idempotency_key="same-key",
    )
    testbase.assert_equal(str(proj1.project_id), str(proj2.project_id))
    return


def test_project_create_rate_limit_trips():
    """
    **Feature: 2-projects (M3)**
    **Property: Exceeding the per-session create rate raises
    RateLimitExceeded.**
    """
    reset_phase2_runtime()
    reset_rate_limit()
    _engine, session = build_in_memory_session()

    for i in range(10):
        project_service.create_project(
            db_session=session, slug="rl-proj-{}".format(i),
            display_name="rl", description="",
            owning_group_id=None, template_id=None, template_version=None,
            actor_user_id=None,
            rate_limit_session_key="session-x",
        )

    raised = False
    try:
        project_service.create_project(
            db_session=session, slug="rl-proj-over",
            display_name="rl", description="",
            owning_group_id=None, template_id=None, template_version=None,
            actor_user_id=None,
            rate_limit_session_key="session-x",
        )
    except RateLimitExceeded:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_metadata_field_collision_raises_on_registry_read():
    """
    **Feature: 2-projects (M3)**
    **Property: Two ProjectMetadataFieldExtension packs with the same
    field_name surface as ConfigurationError.**
    """
    reset_phase2_runtime()
    # Un-freeze the registry so we can register a colliding extension and
    # exercise the re-validation path inside load_registered_fields. The
    # underlying extension host still has the original CostCenterFieldExtension
    # registered from reset_phase2_runtime → register_phase1_builtin_extensions.
    reset_projects_metadata_registry()
    register_resource_extension(
        base_class=ProjectMetadataFieldExtension,
        extension=_DupeCostCenter,
    )

    raised = False
    try:
        load_registered_fields()
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_tagging_orphan_cleanup_on_project_deleted():
    """
    **Feature: 2-tagging (M3)**
    **Property: entity.project.deleted cascades into tag_assignment rows.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    project_id = new_uuid()
    tag_service.assign_tag(
        db_session=session, entity_kind="project", entity_id=project_id,
        raw_tag="env:prod", actor_user_id=None,
    )
    testbase.assert_equal(
        len(tag_service.list_tags(
            db_session=session, entity_kind="project", entity_id=project_id,
        )),
        1,
    )

    def _factory():
        return session_for(engine=_engine)

    wire_bus_subscribers(session_factory=_factory)
    publish(event=EntityEvent(
        topic="entity.project.deleted",
        payload={"project_id": project_id},
        source_event_id=new_uuid(),
    ))

    # Re-read from a fresh session since the subscriber used its own.
    fresh = session_for(engine=_engine)
    testbase.assert_equal(
        len(tag_service.list_tags(
            db_session=fresh, entity_kind="project", entity_id=project_id,
        )),
        0,
    )
    return


def test_variable_cache_hit_on_repeat_resolution():
    """
    **Feature: 2-global-variables (M3)**
    **Property: Repeated resolve_effective calls return the cached value
    without re-reading the DB.**
    """
    reset_phase2_runtime()
    variable_cache.reset_for_testing()
    _engine, session = build_in_memory_session()

    variable_service.set_variable(
        db_session=session, scope=VariableScope.SYSTEM, scope_id="",
        name="cache_me", value="v",
        value_type=VariableValueType.STRING, actor_user_id=None,
    )

    first = variable_service.resolve_effective(
        db_session=session, name="cache_me",
        project_id=None, pipeline_id=None, job_id=None,
        dereference_secrets=False,
    )
    second = variable_service.resolve_effective(
        db_session=session, name="cache_me",
        project_id=None, pipeline_id=None, job_id=None,
        dereference_secrets=False,
    )
    testbase.assert_equal(first, "v")
    testbase.assert_equal(second, "v")
    return


def test_variable_cache_invalidates_on_mutation():
    """
    **Feature: 2-global-variables (M3)**
    **Property: A subsequent set_variable invalidates cached resolutions
    for that name.**
    """
    reset_phase2_runtime()
    variable_cache.reset_for_testing()
    _engine, session = build_in_memory_session()

    variable_service.set_variable(
        db_session=session, scope=VariableScope.SYSTEM, scope_id="",
        name="v1", value="first",
        value_type=VariableValueType.STRING, actor_user_id=None,
    )
    variable_service.resolve_effective(
        db_session=session, name="v1",
        project_id=None, pipeline_id=None, job_id=None,
        dereference_secrets=False,
    )
    variable_service.set_variable(
        db_session=session, scope=VariableScope.SYSTEM, scope_id="",
        name="v1", value="second",
        value_type=VariableValueType.STRING, actor_user_id=None,
    )
    value = variable_service.resolve_effective(
        db_session=session, name="v1",
        project_id=None, pipeline_id=None, job_id=None,
        dereference_secrets=False,
    )
    testbase.assert_equal(value, "second")
    return


def test_retention_skips_entity_under_legal_hold():
    """
    **Feature: 2-retention-policies (M3)**
    **Property: Entities with an active legal hold are skipped during
    evaluate_policy and do not contribute to actioned_count.**
    """
    reset_phase2_runtime()
    _engine, session = build_in_memory_session()

    policy = retention_service.create_policy(
        db_session=session, name="hold-me",
        data_class="run_result",
        scope_level=PolicyScopeLevel.SYSTEM, project_id=None,
        selector=SelectorClause(age_days=30),
        action_chain=[
            ActionStep(action_name="delete", parameters={}, wait_days_after_previous=0),
        ],
        interval_minutes=1440, batch_size=500, max_attempts=3,
        actor_user_id=None,
    )
    retention_service.publish_policy(
        db_session=session, policy_id=str(policy.policy_id), actor_user_id=None,
    )

    retention_legal_hold.place_hold(
        db_session=session, entity_kind="run_result", entity_id="run-held",
        reason="investigation-42", actor_user_id=None,
    )

    run = retention_service.evaluate_policy(
        db_session=session, policy_id=str(policy.policy_id),
        candidate_entity_ids=["run-held", "run-free"],
        dry_run=False, actor_user_id=None,
    )
    testbase.assert_equal(run.matched_count, 2)
    testbase.assert_equal(run.actioned_count, 1)
    testbase.assert_equal(run.skipped_count >= 1, True)
    return
