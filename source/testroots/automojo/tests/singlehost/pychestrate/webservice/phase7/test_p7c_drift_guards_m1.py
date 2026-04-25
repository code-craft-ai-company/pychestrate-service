"""
.. module:: test_p7c_drift_guards_m1
    :synopsis: Tests for P7c — 6-drift-detection + 6-blast-radius-guards M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import timedelta
from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.orchestration.infra.drift import (
    DriftCheckerUnknownError,
    DriftEventTopics,
    DriftReport,
    DriftRunNotFoundError,
    DriftRunState,
    DriftScheduleInvalidError,
    DriftScheduleNotFoundError,
    DriftTickAlreadyRecordedError,
    DriftTriggerKind,
    disable_schedule,
    get_drift_run,
    get_schedule,
    ingest_report,
    list_drift_runs_for_environment,
    record_tick,
    register_builtin_extensions as drift_register,
    run_now,
    set_schedule,
)
from automojo.pychestrate.webservice.orchestration.infra.environment import (
    EnvironmentDeclareInputs,
    archive_environment,
    declare_environment,
    freeze_environment,
    register_builtin_extensions as environment_register,
)
from automojo.pychestrate.webservice.orchestration.infra.guards import (
    GuardEventTopics,
    GuardRuleUnknownError,
    GuardVerdict,
    allow,
    disable_attachment,
    explain,
    list_attachments_for_environment,
    list_rule_records,
    register_builtin_extensions as guards_register,
    set_attachment,
)
from automojo.pychestrate.webservice.orchestration.infra.guards.errors import (
    GuardAttachmentNotFoundError,
    GuardEnvironmentNotFoundError,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000060001"
ACTOR_UUID = "00000000-0000-4000-8000-000000060002"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    environment_register()
    drift_register()
    guards_register()
    return


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


# -------------------------------------
# 6-drift-detection
# -------------------------------------

def test_set_schedule_persists_and_emits():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: set_schedule upserts the row, validates the
    checker name + env-kind support, and emits SCHEDULE_SET.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=DriftEventTopics.SCHEDULE_SET,
        subscriber=lambda e: received.append(e),
    )
    env_id = _declare_environment(session=session)
    view = set_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id,
        checker_name="terraform",
        cron_expression="0 */4 * * *",
        actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.checker_name, "terraform")
    testbase.assert_equal(view.cron_expression, "0 */4 * * *")
    testbase.assert_equal(view.enabled, True)
    testbase.assert_equal(len(received), 1)
    return


def test_set_schedule_unknown_checker_raises():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: an unknown checker raises
    DriftCheckerUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    raised = False
    try:
        set_schedule(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=env_id, checker_name="unknown",
            cron_expression="0 0 * * *",
        )
    except DriftCheckerUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_set_schedule_empty_cron_raises():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: empty cron_expression raises
    DriftScheduleInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    raised = False
    try:
        set_schedule(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=env_id, checker_name="terraform",
            cron_expression="",
        )
    except DriftScheduleInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_disable_schedule_emits_and_idempotent():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: disable_schedule flips enabled=False + emits
    SCHEDULE_DISABLED; second call is idempotent.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=DriftEventTopics.SCHEDULE_DISABLED,
        subscriber=lambda e: received.append(e),
    )
    env_id = _declare_environment(session=session)
    set_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, checker_name="terraform",
        cron_expression="0 0 * * *",
    )
    disabled = disable_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id,
    )
    testbase.assert_equal(disabled.enabled, False)
    disable_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id,
    )
    testbase.assert_equal(len(received), 1)
    return


def test_get_schedule_unknown_raises():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: get_schedule on a non-existent (project, env)
    raises DriftScheduleNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_schedule(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=new_uuid(),
        )
    except DriftScheduleNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_run_now_creates_pending_drift_run_and_emits():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: run_now persists a manual PENDING DriftRun and
    emits RUN_TRIGGERED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=DriftEventTopics.RUN_TRIGGERED,
        subscriber=lambda e: received.append(e),
    )
    env_id = _declare_environment(session=session)
    set_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, checker_name="terraform",
        cron_expression="0 0 * * *",
    )
    view = run_now(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.state, DriftRunState.PENDING)
    testbase.assert_equal(view.trigger_kind, DriftTriggerKind.MANUAL)
    testbase.assert_equal(view.checker_name, "terraform")
    testbase.assert_equal(len(received), 1)
    return


def test_run_now_without_schedule_raises():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: run_now on an env without a schedule raises
    DriftScheduleNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    raised = False
    try:
        run_now(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=env_id,
        )
    except DriftScheduleNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_record_tick_is_exactly_once():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: record_tick inserts a PENDING DriftRun + ledger
    row on the first call; the second call for the same
    (project, env, scheduled_for) raises
    DriftTickAlreadyRecordedError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    set_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, checker_name="terraform",
        cron_expression="0 0 * * *",
    )
    when = utc_now()
    first = record_tick(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, scheduled_for=when,
    )
    testbase.assert_equal(first.is_new, True)
    raised = False
    try:
        record_tick(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=env_id, scheduled_for=when,
        )
    except DriftTickAlreadyRecordedError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_record_tick_disabled_schedule_raises():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: record_tick against a disabled schedule raises
    DriftScheduleInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    set_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, checker_name="terraform",
        cron_expression="0 0 * * *",
    )
    disable_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id,
    )
    raised = False
    try:
        record_tick(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=env_id, scheduled_for=utc_now(),
        )
    except DriftScheduleInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_ingest_report_emits_drift_detected_when_drifted():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: ingest_report stamps counts + diff digest +
    emits REPORT_INGESTED + DRIFT_DETECTED when drift_count>0.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_ingested: List[EntityEvent] = []
    received_drifted: List[EntityEvent] = []
    subscribe(
        topic=DriftEventTopics.REPORT_INGESTED,
        subscriber=lambda e: received_ingested.append(e),
    )
    subscribe(
        topic=DriftEventTopics.DRIFT_DETECTED,
        subscriber=lambda e: received_drifted.append(e),
    )
    env_id = _declare_environment(session=session)
    set_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, checker_name="terraform",
        cron_expression="0 0 * * *",
    )
    run = run_now(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id,
    )
    completed = ingest_report(
        db_session=session, run_id=run.run_id,
        report=DriftReport(
            drift_count=3, added=1, changed=2, destroyed=0,
            diff_digest_sha256="d" * 64,
            payload={"summary": "drift detected"},
        ),
    )
    testbase.assert_equal(completed.state, DriftRunState.COMPLETED)
    testbase.assert_equal(completed.drift_count, 3)
    testbase.assert_equal(completed.diff_digest_sha256, "d" * 64)
    testbase.assert_equal(len(received_ingested), 1)
    testbase.assert_equal(len(received_drifted), 1)
    return


def test_ingest_report_no_drift_skips_drifted_emit():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: ingest_report with drift_count=0 emits
    REPORT_INGESTED but not DRIFT_DETECTED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_drifted: List[EntityEvent] = []
    subscribe(
        topic=DriftEventTopics.DRIFT_DETECTED,
        subscriber=lambda e: received_drifted.append(e),
    )
    env_id = _declare_environment(session=session)
    set_schedule(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, checker_name="terraform",
        cron_expression="0 0 * * *",
    )
    run = run_now(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id,
    )
    ingest_report(
        db_session=session, run_id=run.run_id,
        report=DriftReport(drift_count=0, added=0, changed=0, destroyed=0),
    )
    testbase.assert_equal(len(received_drifted), 0)
    return


def test_get_drift_run_unknown_raises():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: get_drift_run on an unknown id raises
    DriftRunNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_drift_run(db_session=session, run_id=new_uuid())
    except DriftRunNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_drift_runs_scopes_to_environment():
    """
    **Feature: 6-drift-detection (M1)**
    **Property: list_drift_runs_for_environment scopes results
    to the target env.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_a = _declare_environment(session=session, name="a")
    env_b = _declare_environment(session=session, name="b")
    for env in (env_a, env_b):
        set_schedule(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=env, checker_name="terraform",
            cron_expression="0 0 * * *",
        )
    run_now(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_a,
    )
    run_now(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_a,
    )
    run_now(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_b,
    )
    rows_a = list_drift_runs_for_environment(
        db_session=session, environment_id=env_a,
    )
    testbase.assert_equal(len(rows_a), 2)
    return


# -------------------------------------
# 6-blast-radius-guards
# -------------------------------------

def test_list_rule_records_returns_in_tree_rules():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: list_rule_records exposes both reference rules
    in PRECEDENCE order.**
    """
    _prepare_runtime()
    records = list_rule_records()
    rule_ids = [r.rule_id for r in records]
    testbase.assert_equal("FrozenEnvBlockRule" in rule_ids, True)
    testbase.assert_equal(
        "ApplyRequiresInfraOperatorRoleRule" in rule_ids, True,
    )
    return


def test_set_attachment_persists_and_emits():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: set_attachment upserts the row + emits
    ATTACHMENT_SET.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=GuardEventTopics.ATTACHMENT_SET,
        subscriber=lambda e: received.append(e),
    )
    env_id = _declare_environment(session=session)
    view = set_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, rule_id="FrozenEnvBlockRule",
        enabled=True, actor_id=ACTOR_UUID,
    )
    testbase.assert_equal(view.enabled, True)
    testbase.assert_equal(len(received), 1)
    return


def test_set_attachment_unknown_rule_raises():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: set_attachment with an unregistered rule_id
    raises GuardRuleUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    raised = False
    try:
        set_attachment(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=env_id, rule_id="UnknownRule",
            enabled=True,
        )
    except GuardRuleUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_set_attachment_unknown_environment_raises():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: set_attachment against an unknown env raises
    GuardEnvironmentNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        set_attachment(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=new_uuid(), rule_id="FrozenEnvBlockRule",
            enabled=True,
        )
    except GuardEnvironmentNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_disable_attachment_idempotent_and_unknown_raises():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: disable_attachment flips enabled=False; second
    call is idempotent. An unknown attachment raises
    GuardAttachmentNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=GuardEventTopics.ATTACHMENT_DISABLED,
        subscriber=lambda e: received.append(e),
    )
    env_id = _declare_environment(session=session)
    set_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, rule_id="FrozenEnvBlockRule",
        enabled=True,
    )
    disable_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, rule_id="FrozenEnvBlockRule",
    )
    disable_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, rule_id="FrozenEnvBlockRule",
    )
    testbase.assert_equal(len(received), 1)

    raised = False
    try:
        disable_attachment(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=env_id,
            rule_id="ApplyRequiresInfraOperatorRoleRule",
        )
    except GuardAttachmentNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_allow_with_no_attachments_is_allowed():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: allow returns allowed=True when no
    attachments are configured for the env (empty rule set).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    trace = allow(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, action="apply",
        actor_role_set=("infra-operator",),
    )
    testbase.assert_equal(trace.allowed, True)
    testbase.assert_equal(len(trace.entries), 0)
    return


def test_frozen_env_block_rule_denies_apply_on_frozen_env():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: with FrozenEnvBlockRule attached to a frozen
    env, allow returns DENY for apply with the rule recorded
    as failing_rule_id.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_decided: List[EntityEvent] = []
    subscribe(
        topic=GuardEventTopics.DECIDED,
        subscriber=lambda e: received_decided.append(e),
    )
    env_id = _declare_environment(session=session)
    set_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, rule_id="FrozenEnvBlockRule",
        enabled=True,
    )
    freeze_environment(
        db_session=session, environment_id=env_id, reason="x",
    )
    trace = allow(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, action="apply",
        actor_role_set=("infra-operator",),
    )
    testbase.assert_equal(trace.allowed, False)
    testbase.assert_equal(trace.failing_rule_id, "FrozenEnvBlockRule")
    testbase.assert_equal(len(received_decided), 1)

    # plan is allowed on a frozen env
    trace_plan = allow(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, action="plan",
    )
    testbase.assert_equal(trace_plan.allowed, True)
    return


def test_apply_requires_role_rule_denies_without_role():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: ApplyRequiresInfraOperatorRoleRule denies
    apply / destroy when 'infra-operator' is missing from the
    role set.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    set_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id,
        rule_id="ApplyRequiresInfraOperatorRoleRule",
        enabled=True,
    )

    denied = allow(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, action="apply",
        actor_role_set=("viewer",),
    )
    testbase.assert_equal(denied.allowed, False)
    testbase.assert_equal(
        denied.failing_rule_id, "ApplyRequiresInfraOperatorRoleRule",
    )

    allowed = allow(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, action="apply",
        actor_role_set=("viewer", "infra-operator"),
    )
    testbase.assert_equal(allowed.allowed, True)
    return


def test_disabled_attachment_does_not_evaluate():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: a disabled attachment is skipped during
    allow().**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    set_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, rule_id="FrozenEnvBlockRule",
        enabled=True,
    )
    freeze_environment(
        db_session=session, environment_id=env_id, reason="x",
    )
    disable_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, rule_id="FrozenEnvBlockRule",
    )
    trace = allow(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, action="apply",
        actor_role_set=("infra-operator",),
    )
    testbase.assert_equal(trace.allowed, True)
    return


def test_allow_unknown_environment_raises():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: allow against an unknown env raises
    GuardEnvironmentNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        allow(
            db_session=session, project_id=PROJECT_UUID,
            environment_id=new_uuid(), action="apply",
        )
    except GuardEnvironmentNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_explain_evaluates_every_registered_rule():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: explain returns one trace entry per registered
    rule regardless of attachment state.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    trace = explain(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, action="apply",
        actor_role_set=("viewer",),
    )
    testbase.assert_equal(len(trace.entries) >= 2, True)
    # Without infra-operator role, apply is denied by the role rule.
    testbase.assert_equal(trace.allowed, False)
    return


def test_list_attachments_for_environment_filters_enabled():
    """
    **Feature: 6-blast-radius-guards (M1)**
    **Property: list_attachments_for_environment can filter to
    enabled-only rows.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    env_id = _declare_environment(session=session)
    set_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, rule_id="FrozenEnvBlockRule",
        enabled=True,
    )
    set_attachment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id,
        rule_id="ApplyRequiresInfraOperatorRoleRule",
        enabled=False,
    )
    all_rows = list_attachments_for_environment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id,
    )
    testbase.assert_equal(len(all_rows), 2)
    enabled_rows = list_attachments_for_environment(
        db_session=session, project_id=PROJECT_UUID,
        environment_id=env_id, enabled_only=True,
    )
    testbase.assert_equal(len(enabled_rows), 1)
    testbase.assert_equal(enabled_rows[0].rule_id, "FrozenEnvBlockRule")
    return
