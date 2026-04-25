"""
.. module:: test_p13a_retention_selectors_m2
    :synopsis: Tests for P13a — 2-retention-policies selector
               compiler + action dispatcher.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import Any, ClassVar, Mapping

from automojo import testbase

from automojo.errors.exceptions import SemanticError

from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
    reset_registry_for_testing,
    unregister_factory_implementation,
)
from automojo.pychestrate.webservice.retention.dispatcher import (
    ChainResult,
    StepOutcome,
    dispatch_action_chain,
)
from automojo.pychestrate.webservice.retention.factories.action import (
    ActionApplication,
    RetentionActionProtocol,
)
from automojo.pychestrate.webservice.retention.models import (
    ActionStep,
    SelectorClause,
)
from automojo.pychestrate.webservice.retention.selectors import (
    CandidateAttributes,
    SUPPORTED_DATA_CLASSES,
    compile_selector,
    compile_selector_for_data_class,
)


def _candidate(
        *,
        entity_id: str = "x",
        age_days: int = 0,
        size_bytes: int = 0,
        project_id=None,
        tags=()
    ) -> CandidateAttributes:
    return CandidateAttributes(
        entity_id=entity_id, age_days=age_days,
        size_bytes=size_bytes, project_id=project_id, tags=tags,
    )


# -------------------------------------
# Selector compiler
# -------------------------------------

def test_empty_selector_matches_everything():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: an empty SelectorClause compiles to a
    predicate that returns True for every candidate.**
    """
    predicate = compile_selector(selector=SelectorClause())
    testbase.assert_equal(predicate(_candidate()), True)
    testbase.assert_equal(
        predicate(_candidate(entity_id="y", age_days=999)),
        True,
    )
    return


def test_age_days_threshold_excludes_young_candidates():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: age_days threshold matches only candidates
    whose age_days is >= the threshold.**
    """
    predicate = compile_selector(selector=SelectorClause(age_days=30))
    testbase.assert_equal(
        predicate(_candidate(age_days=29)), False,
    )
    testbase.assert_equal(
        predicate(_candidate(age_days=30)), True,
    )
    testbase.assert_equal(
        predicate(_candidate(age_days=365)), True,
    )
    return


def test_size_threshold_is_strict_greater_than():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: size_bytes_over uses strict greater-than;
    candidates equal to the threshold do NOT match.**
    """
    predicate = compile_selector(
        selector=SelectorClause(size_bytes_over=1024),
    )
    testbase.assert_equal(
        predicate(_candidate(size_bytes=1024)), False,
    )
    testbase.assert_equal(
        predicate(_candidate(size_bytes=1025)), True,
    )
    return


def test_project_filter_requires_membership():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: when project_ids is non-empty, candidates
    without a project_id or with one outside the set are
    excluded.**
    """
    predicate = compile_selector(
        selector=SelectorClause(project_ids=("proj-a", "proj-b")),
    )
    testbase.assert_equal(
        predicate(_candidate(project_id="proj-a")), True,
    )
    testbase.assert_equal(
        predicate(_candidate(project_id="proj-c")), False,
    )
    testbase.assert_equal(
        predicate(_candidate(project_id=None)), False,
    )
    return


def test_tag_expression_combines_with_other_fields():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: tag_expression participates in the AND chain
    so the candidate must satisfy both the age threshold and
    the tag expression.**
    """
    predicate = compile_selector(
        selector=SelectorClause(
            tag_expression="environment:prod",
            age_days=30,
        ),
    )
    testbase.assert_equal(
        predicate(_candidate(age_days=60, tags=("environment:prod",))),
        True,
    )
    testbase.assert_equal(
        predicate(_candidate(age_days=60, tags=("environment:dev",))),
        False,
    )
    testbase.assert_equal(
        predicate(_candidate(age_days=10, tags=("environment:prod",))),
        False,
    )
    return


def test_compile_selector_for_data_class_validates_class_name():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: compile_selector_for_data_class rejects
    unknown classes with SemanticError.**
    """
    raised = False
    try:
        compile_selector_for_data_class(
            data_class="not-a-real-class",
            selector=SelectorClause(),
        )
    except SemanticError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_supported_data_classes_set_has_expected_members():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: the M2 data-class set covers artifact /
    run_result / log_stream / audit_record / metric_sample.**
    """
    expected = {
        "artifact", "run_result", "log_stream",
        "audit_record", "metric_sample",
    }
    testbase.assert_equal(set(SUPPORTED_DATA_CLASSES), expected)
    return


# -------------------------------------
# Dispatcher — fixtures
# -------------------------------------

class _AppliesAction(RetentionActionProtocol):
    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "p13a_applies"
    terminal: ClassVar[bool] = False
    PRECEDENCE: ClassVar[int] = 1000

    @classmethod
    def apply(cls, *, entity_kind, entity_id, parameters, dry_run):
        return ActionApplication(
            outcome="applied",
            reason="ok",
            terminal=False,
        )


class _TerminalAction(RetentionActionProtocol):
    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "p13a_terminal"
    terminal: ClassVar[bool] = True
    PRECEDENCE: ClassVar[int] = 1000

    @classmethod
    def apply(cls, *, entity_kind, entity_id, parameters, dry_run):
        return ActionApplication(
            outcome="applied",
            reason="archived",
            terminal=True,
        )


class _CrashingAction(RetentionActionProtocol):
    factory_protocol_name: ClassVar[str] = "retention_action"
    action_name: ClassVar[str] = "p13a_crashes"
    terminal: ClassVar[bool] = False
    PRECEDENCE: ClassVar[int] = 1000

    @classmethod
    def apply(cls, *, entity_kind, entity_id, parameters, dry_run):
        raise RuntimeError("simulated_action_crash")


def _setup_dispatcher_fixtures() -> None:
    reset_registry_for_testing()
    register_factory_implementation(implementation=_AppliesAction)
    register_factory_implementation(implementation=_TerminalAction)
    register_factory_implementation(implementation=_CrashingAction)
    return


def _teardown_dispatcher_fixtures() -> None:
    for impl in (_AppliesAction, _TerminalAction, _CrashingAction):
        unregister_factory_implementation(implementation=impl)
    return


# -------------------------------------
# Dispatcher tests
# -------------------------------------

def test_dispatch_runs_chain_in_order():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: dispatch_action_chain walks every step in
    order and reports per-step outcomes.**
    """
    _setup_dispatcher_fixtures()
    try:
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(
                    action_name="p13a_applies",
                    parameters={},
                ),
                ActionStep(
                    action_name="p13a_applies",
                    parameters={"step": "second"},
                ),
            ],
            dry_run=False,
        )
        testbase.assert_equal(len(result.steps), 2)
        testbase.assert_equal(result.steps[0].outcome, "applied")
        testbase.assert_equal(result.steps[1].outcome, "applied")
        testbase.assert_equal(result.halted_terminal, False)
        testbase.assert_equal(result.final_outcome, "applied")
    finally:
        _teardown_dispatcher_fixtures()
    return


def test_dispatch_halts_after_terminal_action_on_real_run():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: a terminal action ends the chain on a real
    run; subsequent steps do not execute.**
    """
    _setup_dispatcher_fixtures()
    try:
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(action_name="p13a_terminal", parameters={}),
                ActionStep(action_name="p13a_applies", parameters={}),
            ],
            dry_run=False,
        )
        testbase.assert_equal(len(result.steps), 1)
        testbase.assert_equal(result.halted_terminal, True)
    finally:
        _teardown_dispatcher_fixtures()
    return


def test_dispatch_dry_run_skips_terminal_short_circuit():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: on a dry run, the dispatcher reports every
    step even when an earlier step is terminal so operators
    see the full hypothetical plan.**
    """
    _setup_dispatcher_fixtures()
    try:
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(action_name="p13a_terminal", parameters={}),
                ActionStep(action_name="p13a_applies", parameters={}),
            ],
            dry_run=True,
        )
        testbase.assert_equal(len(result.steps), 2)
        testbase.assert_equal(result.halted_terminal, False)
    finally:
        _teardown_dispatcher_fixtures()
    return


def test_dispatch_defers_step_until_wait_days_elapses():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: a step with wait_days_after_previous > 0
    surfaces as 'deferred' when now < prior + wait, and the
    chain stops at that step.**
    """
    _setup_dispatcher_fixtures()
    try:
        anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(action_name="p13a_applies", parameters={}),
                ActionStep(
                    action_name="p13a_applies",
                    parameters={},
                    wait_days_after_previous=7,
                ),
            ],
            dry_run=False,
            now=anchor,
        )
        testbase.assert_equal(len(result.steps), 2)
        testbase.assert_equal(result.steps[1].outcome, "deferred")
        expected_wait = anchor + timedelta(days=7)
        testbase.assert_equal(
            result.steps[1].wait_until, expected_wait,
        )
        testbase.assert_equal(result.final_outcome, "deferred")
    finally:
        _teardown_dispatcher_fixtures()
    return


def test_dispatch_skips_wait_check_on_dry_run():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: a dry-run honors the chain shape but does
    not enforce the wait-days check so operators preview the
    full plan.**
    """
    _setup_dispatcher_fixtures()
    try:
        anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(action_name="p13a_applies", parameters={}),
                ActionStep(
                    action_name="p13a_applies",
                    parameters={},
                    wait_days_after_previous=7,
                ),
            ],
            dry_run=True,
            now=anchor,
        )
        testbase.assert_equal(len(result.steps), 2)
        testbase.assert_equal(result.steps[1].outcome, "applied")
    finally:
        _teardown_dispatcher_fixtures()
    return


def test_dispatch_records_action_crash_as_failed():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: an action that raises is reclassified as
    outcome='failed' with the exception class + message in
    reason, and the chain stops.**
    """
    _setup_dispatcher_fixtures()
    try:
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(action_name="p13a_crashes", parameters={}),
                ActionStep(action_name="p13a_applies", parameters={}),
            ],
            dry_run=False,
        )
        testbase.assert_equal(len(result.steps), 1)
        testbase.assert_equal(result.steps[0].outcome, "failed")
        testbase.assert_equal(
            "RuntimeError" in result.steps[0].reason,
            True,
        )
        testbase.assert_equal(result.final_outcome, "failed")
    finally:
        _teardown_dispatcher_fixtures()
    return


def test_dispatch_unknown_action_records_failed():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: a step naming an unregistered action is
    recorded as outcome='failed' with reason='action_not_registered'.**
    """
    _setup_dispatcher_fixtures()
    try:
        result = dispatch_action_chain(
            entity_kind="artifact",
            entity_id="art-1",
            steps=[
                ActionStep(action_name="never_registered", parameters={}),
            ],
            dry_run=False,
        )
        testbase.assert_equal(len(result.steps), 1)
        testbase.assert_equal(result.steps[0].outcome, "failed")
        testbase.assert_equal(
            result.steps[0].reason, "action_not_registered",
        )
    finally:
        _teardown_dispatcher_fixtures()
    return


def test_dispatch_empty_chain_raises_semantic_error():
    """
    **Feature: 2-retention-policies (M2)**
    **Property: dispatch_action_chain with no steps raises
    SemanticError so the configuration bug surfaces loudly.**
    """
    _setup_dispatcher_fixtures()
    try:
        raised = False
        try:
            dispatch_action_chain(
                entity_kind="artifact",
                entity_id="art-1",
                steps=[],
                dry_run=False,
            )
        except SemanticError:
            raised = True
        testbase.assert_equal(raised, True)
    finally:
        _teardown_dispatcher_fixtures()
    return
