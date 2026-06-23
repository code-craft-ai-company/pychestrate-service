"""
.. module:: test_p7b_infra_orchestration_m1
    :synopsis: Tests for P7b — 6-infra-orchestration M1.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from typing import List, Tuple

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.jobs.dispatch import (
    InMemoryTransport,
    JobDispatcher,
    register_builtin_extensions as dispatch_register,
)
from ccai.pychestrate.webservice.jobs.dispatch.factories.strategy import (
    DispatchCandidate,
)
from ccai.pychestrate.webservice.jobs.envelope import (
    EnvelopeSignerBootstrapConfig,
    install_envelope_signer,
)
from ccai.pychestrate.webservice.jobs.envelope import signer as envelope_signer
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.orchestration.infra.runs import (
    set_active_job_dispatcher,
    set_active_results_backend,
)

# Side-effect imports so the Layer-5 model tables attach to the shared
# Phase-1 metadata before ``create_all`` runs in the fixture.
from ccai.pychestrate.webservice.jobs.run.state import models as _run_state_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.dispatch import models as _dispatch_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.envelope import models as _envelope_models  # noqa: F401
from ccai.pychestrate.webservice.jobs.results import models as _results_models  # noqa: F401
from ccai.pychestrate.webservice.orchestration.infra.environment import (
    EnvironmentDeclareInputs,
    archive_environment,
    declare_environment,
    freeze_environment,
    register_builtin_extensions as environment_register,
)
from ccai.pychestrate.webservice.orchestration.infra.runs import (
    InfraAction,
    InfraDriverUnknownError,
    InfraEnvironmentStateError,
    InfraEventTopics,
    InfraInputsInvalidError,
    InfraRunInputs,
    InfraRunNotFoundError,
    InfraRunState,
    InfraTriggerAspects,
    PlanSummary,
    ResourceOp,
    ResourceOpKind,
    apply_run_terminal,
    get_infra_run,
    list_infra_runs_for_environment,
    record_plan_summary,
    register_builtin_extensions as infra_runs_register,
    trigger_run,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000050001"
ACTOR_UUID = "00000000-0000-4000-8000-000000050002"
LAYER5_UUID = "00000000-0000-4000-8000-000000050003"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    envelope_signer.reset_for_testing()
    set_active_job_dispatcher(dispatcher=None)
    set_active_results_backend(backend=None)
    dispatch_register()
    environment_register()
    infra_runs_register()
    os.environ["PYCHESTRATE_DEV_MODE"] = "1"
    try:
        install_envelope_signer(
            config=EnvelopeSignerBootstrapConfig(
                source="dev",
                file_path=None,
                env_var=None,
                key_id="test-provision-dispatch-ed25519",
            ),
        )
    finally:
        del os.environ["PYCHESTRATE_DEV_MODE"]
    return


def _one_candidate() -> Tuple[DispatchCandidate, ...]:
    """
        A single eligible dispatch candidate.

        :returns: One-element tuple of :class:`DispatchCandidate`.
    """
    rtnval = (
        DispatchCandidate(
            client_id="11111111-1111-4000-8000-000000050011",
            pod_id="22222222-2222-4000-8000-000000050012",
            capability_tags=tuple(),
            inflight_dispatch_count=0,
            last_dispatched_at_iso="",
        ),
    )
    return rtnval


def _wire_dispatcher() -> JobDispatcher:
    """
        Wire an in-memory :class:`JobDispatcher` on the infra-runs
        service seam and return it.

        :returns: The wired :class:`JobDispatcher`.
    """
    dispatcher = JobDispatcher(transport=InMemoryTransport())
    set_active_job_dispatcher(dispatcher=dispatcher)
    rtnval = dispatcher
    return rtnval


def _declare_environment(*, session, name: str = "prod-east") -> str:
    view = declare_environment(
        db_session=session, project_id=PROJECT_UUID,
        inputs=EnvironmentDeclareInputs(
            name=name, kind_name="k8s-cluster",
            attrs={
                "cluster_id": "cluster-001",
                "region": "us-east-1",
                "api_endpoint": "https://api.example.com",
            },
        ),
    )
    rtnval = view.environment_id
    return rtnval


def _valid_terraform_inputs(
        *,
        environment_id: str,
        action: InfraAction = InfraAction.PLAN
    ) -> InfraRunInputs:
    rtnval = InfraRunInputs(
        environment_id=environment_id,
        driver_name="terraform",
        action=action,
        driver_inputs={
            "working_directory": "/repo/infra",
            "var_file": "prod.tfvars",
            "backend_config": {"bucket": "tfstate"},
            "parallelism": 4,
        },
    )
    return rtnval


# -------------------------------------
# trigger_run
# -------------------------------------

def test_trigger_run_dispatches_and_emits():
    """
    **Feature: 6-infra-orchestration (PR p20l)**
    **Property: trigger_run resolves env + driver, validates
    inputs, dispatches a job_kind=provision envelope and flips the
    InfraRun PENDING -> RUNNING while emitting TRIGGERED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _wire_dispatcher()
    received: List[EntityEvent] = []
    subscribe(
        topic=InfraEventTopics.TRIGGERED,
        subscriber=lambda e: received.append(e),
    )
    env_id = _declare_environment(session=session)
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(environment_id=env_id),
        aspects=InfraTriggerAspects(
            actor_id=ACTOR_UUID,
            actor_role_set=("infra-operator", "viewer"),
            candidates=_one_candidate(),
            project_slug="prod-east",
        ),
    )
    testbase.assert_equal(view.state, InfraRunState.RUNNING)
    testbase.assert_equal(view.driver_name, "terraform")
    testbase.assert_equal(view.action, InfraAction.PLAN)
    testbase.assert_equal(view.actor_role_set, ("infra-operator", "viewer"))
    testbase.assert_equal(len(view.inputs_canonical_sha256), 64)
    testbase.assert_equal(view.dispatch_attempt_id is not None, True)
    testbase.assert_equal(len(received), 1)
    return


def test_trigger_run_unknown_driver_raises():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: an unknown driver_name raises
    InfraDriverUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    bad = InfraRunInputs(
        environment_id=env_id, driver_name="unknown-tool",
        action=InfraAction.PLAN,
        driver_inputs={"working_directory": "/repo"},
    )
    raised = False
    try:
        trigger_run(
            db_session=session, project_id=PROJECT_UUID, inputs=bad,
        )
    except InfraDriverUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_trigger_run_invalid_inputs_aggregate():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: a driver-rejection raises
    InfraInputsInvalidError listing every issue.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    bad = InfraRunInputs(
        environment_id=env_id, driver_name="terraform",
        action=InfraAction.PLAN,
        driver_inputs={
            # missing working_directory
            "var_file": "",
            "parallelism": -2,
        },
    )
    raised = False
    try:
        trigger_run(
            db_session=session, project_id=PROJECT_UUID, inputs=bad,
        )
    except InfraInputsInvalidError as xcpt:
        raised = True
        msg = str(xcpt)
        testbase.assert_equal("working_directory" in msg, True)
        testbase.assert_equal("var_file" in msg, True)
        testbase.assert_equal("parallelism" in msg, True)
    testbase.assert_equal(raised, True)
    return


def test_trigger_run_unknown_environment_raises():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: an unknown environment_id raises
    InfraEnvironmentStateError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    bad = InfraRunInputs(
        environment_id=new_uuid(), driver_name="terraform",
        action=InfraAction.PLAN,
        driver_inputs={"working_directory": "/repo"},
    )
    raised = False
    try:
        trigger_run(
            db_session=session, project_id=PROJECT_UUID, inputs=bad,
        )
    except InfraEnvironmentStateError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_trigger_run_archived_environment_raises():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: triggering against an archived env raises
    InfraEnvironmentStateError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    archive_environment(
        db_session=session, environment_id=env_id, reason="x",
    )
    raised = False
    try:
        trigger_run(
            db_session=session,
            project_id=PROJECT_UUID,
            inputs=_valid_terraform_inputs(environment_id=env_id),
        )
    except InfraEnvironmentStateError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_frozen_env_only_allows_plan():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: a frozen environment accepts plan but rejects
    apply / destroy with InfraEnvironmentStateError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _wire_dispatcher()
    env_id = _declare_environment(session=session)
    freeze_environment(
        db_session=session, environment_id=env_id, reason="frozen",
    )

    # plan is allowed
    plan_view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(
            environment_id=env_id, action=InfraAction.PLAN,
        ),
        aspects=InfraTriggerAspects(
            candidates=_one_candidate(),
            project_slug="prod-east",
        ),
    )
    testbase.assert_equal(plan_view.action, InfraAction.PLAN)

    # apply is rejected
    raised_apply = False
    try:
        trigger_run(
            db_session=session,
            project_id=PROJECT_UUID,
            inputs=_valid_terraform_inputs(
                environment_id=env_id, action=InfraAction.APPLY,
            ),
        )
    except InfraEnvironmentStateError:
        raised_apply = True
    testbase.assert_equal(raised_apply, True)

    # destroy is rejected
    raised_destroy = False
    try:
        trigger_run(
            db_session=session,
            project_id=PROJECT_UUID,
            inputs=_valid_terraform_inputs(
                environment_id=env_id, action=InfraAction.DESTROY,
            ),
        )
    except InfraEnvironmentStateError:
        raised_destroy = True
    testbase.assert_equal(raised_destroy, True)
    return


def test_environment_project_mismatch_raises():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: triggering against an env owned by a different
    project raises InfraEnvironmentStateError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    raised = False
    try:
        trigger_run(
            db_session=session,
            project_id=new_uuid(),
            inputs=_valid_terraform_inputs(environment_id=env_id),
        )
    except InfraEnvironmentStateError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# record_plan_summary
# -------------------------------------

def test_record_plan_summary_stamps_and_emits():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: record_plan_summary persists the summary +
    artifact ref + diff digest + stamps plan_issued_at; emits
    PLAN_RECORDED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=InfraEventTopics.PLAN_RECORDED,
        subscriber=lambda e: received.append(e),
    )
    _wire_dispatcher()
    env_id = _declare_environment(session=session)
    plan = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(environment_id=env_id),
        aspects=InfraTriggerAspects(candidates=_one_candidate(), project_slug="prod-east"),
    )
    summary = PlanSummary(
        resources_to_add=2,
        resources_to_change=1,
        resources_to_destroy=0,
        resource_ops=(
            ResourceOp(
                resource_address="aws_s3_bucket.example",
                op=ResourceOpKind.ADD,
                module_path="root",
            ),
        ),
    )
    updated = record_plan_summary(
        db_session=session, run_id=plan.run_id,
        summary=summary,
        plan_artifact_ref="s3://plan-artifacts/abc.tfplan",
        plan_diff_digest_sha256="d" * 64,
    )
    testbase.assert_equal(updated.plan_summary.resources_to_add, 2)
    testbase.assert_equal(updated.plan_artifact_ref, "s3://plan-artifacts/abc.tfplan")
    testbase.assert_equal(updated.plan_diff_digest_sha256, "d" * 64)
    testbase.assert_equal(updated.plan_issued_at is not None, True)
    testbase.assert_equal(len(received), 1)
    return


def test_record_plan_summary_on_apply_run_raises():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: record_plan_summary against an APPLY run raises
    InfraInputsInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _wire_dispatcher()
    env_id = _declare_environment(session=session)
    apply_view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(
            environment_id=env_id, action=InfraAction.APPLY,
        ),
        aspects=InfraTriggerAspects(candidates=_one_candidate(), project_slug="prod-east"),
    )
    raised = False
    try:
        record_plan_summary(
            db_session=session, run_id=apply_view.run_id,
            summary=PlanSummary(
                resources_to_add=0, resources_to_change=0,
                resources_to_destroy=0,
            ),
        )
    except InfraInputsInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_record_plan_summary_unknown_run_raises():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: record_plan_summary on an unknown run raises
    InfraRunNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        record_plan_summary(
            db_session=session, run_id=new_uuid(),
            summary=PlanSummary(
                resources_to_add=0, resources_to_change=0,
                resources_to_destroy=0,
            ),
        )
    except InfraRunNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# apply_run_terminal
# -------------------------------------

def test_apply_run_terminal_completed_emits_kind_specific_topic():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: completing an infra run emits STATE_CHANGED +
    COMPLETED; layer5_run_id + output_digest get stamped.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_state: List[EntityEvent] = []
    received_completed: List[EntityEvent] = []
    subscribe(
        topic=InfraEventTopics.STATE_CHANGED,
        subscriber=lambda e: received_state.append(e),
    )
    subscribe(
        topic=InfraEventTopics.COMPLETED,
        subscriber=lambda e: received_completed.append(e),
    )
    _wire_dispatcher()
    env_id = _declare_environment(session=session)
    plan = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(environment_id=env_id),
        aspects=InfraTriggerAspects(candidates=_one_candidate(), project_slug="prod-east"),
    )
    completed = apply_run_terminal(
        db_session=session, run_id=plan.run_id,
        final_state=InfraRunState.COMPLETED,
        layer5_run_id=LAYER5_UUID,
        output_digest_sha256="e" * 64,
    )
    testbase.assert_equal(completed.state, InfraRunState.COMPLETED)
    testbase.assert_equal(completed.layer5_run_id, LAYER5_UUID)
    testbase.assert_equal(completed.output_digest_sha256, "e" * 64)
    testbase.assert_equal(len(received_state), 1)
    testbase.assert_equal(len(received_completed), 1)
    return


def test_apply_run_terminal_rejected_by_guard_emits_kind():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: REJECTED_BY_GUARD records the failing rule id
    and emits the dedicated topic.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=InfraEventTopics.REJECTED_BY_GUARD,
        subscriber=lambda e: received.append(e),
    )
    _wire_dispatcher()
    env_id = _declare_environment(session=session)
    plan = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(
            environment_id=env_id, action=InfraAction.APPLY,
        ),
        aspects=InfraTriggerAspects(candidates=_one_candidate(), project_slug="prod-east"),
    )
    rejected = apply_run_terminal(
        db_session=session, run_id=plan.run_id,
        final_state=InfraRunState.REJECTED_BY_GUARD,
        failing_guard_rule_id="ProdDestroyRequiresTwoPersonRule",
        reason="missing two-person review",
    )
    testbase.assert_equal(rejected.state, InfraRunState.REJECTED_BY_GUARD)
    testbase.assert_equal(
        rejected.failing_guard_rule_id,
        "ProdDestroyRequiresTwoPersonRule",
    )
    testbase.assert_equal(len(received), 1)
    return


def test_apply_run_terminal_idempotent():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: a second apply_run_terminal on a terminal row
    is a no-op (no new events fire).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=InfraEventTopics.COMPLETED,
        subscriber=lambda e: received.append(e),
    )
    _wire_dispatcher()
    env_id = _declare_environment(session=session)
    plan = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(environment_id=env_id),
        aspects=InfraTriggerAspects(candidates=_one_candidate(), project_slug="prod-east"),
    )
    apply_run_terminal(
        db_session=session, run_id=plan.run_id,
        final_state=InfraRunState.COMPLETED,
    )
    apply_run_terminal(
        db_session=session, run_id=plan.run_id,
        final_state=InfraRunState.COMPLETED,
    )
    testbase.assert_equal(len(received), 1)
    return


def test_apply_run_terminal_non_terminal_state_raises():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: passing a non-terminal state to
    apply_run_terminal raises InfraInputsInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _wire_dispatcher()
    env_id = _declare_environment(session=session)
    plan = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(environment_id=env_id),
        aspects=InfraTriggerAspects(candidates=_one_candidate(), project_slug="prod-east"),
    )
    raised = False
    try:
        apply_run_terminal(
            db_session=session, run_id=plan.run_id,
            final_state=InfraRunState.RUNNING,
        )
    except InfraInputsInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# read helpers
# -------------------------------------

def test_get_infra_run_unknown_raises():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: get_infra_run on an unknown id raises
    InfraRunNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_infra_run(db_session=session, run_id=new_uuid())
    except InfraRunNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_infra_runs_for_environment_scopes():
    """
    **Feature: 6-infra-orchestration (M1)**
    **Property: list_infra_runs_for_environment scopes to the
    target environment.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    _wire_dispatcher()
    env_a = _declare_environment(session=session, name="a")
    env_b = _declare_environment(session=session, name="b")
    aspects = InfraTriggerAspects(candidates=_one_candidate(), project_slug="prod-east")
    trigger_run(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(environment_id=env_a),
        aspects=aspects,
    )
    trigger_run(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(environment_id=env_a),
        aspects=aspects,
    )
    trigger_run(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_terraform_inputs(environment_id=env_b),
        aspects=aspects,
    )
    rows_a = list_infra_runs_for_environment(
        db_session=session, environment_id=env_a,
    )
    testbase.assert_equal(len(rows_a), 2)
    rows_b = list_infra_runs_for_environment(
        db_session=session, environment_id=env_b,
    )
    testbase.assert_equal(len(rows_b), 1)
    return
