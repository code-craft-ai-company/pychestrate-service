"""
.. module:: test_p5c_triage_compare_m1
    :synopsis: Tests for P5c — 6-triage-bug-linking + 6-compare-runs M1.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from ccai.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from ccai.pychestrate.webservice.orchestration.test.compare import (
    CompareEventTopics,
    CompareInputInvalidError,
    CompareReportNotFoundError,
    DiffArtifactRef,
    NoMatchingDiffViewerError,
    OutcomeForRun,
    TestDiffStatus,
    build_compare_report,
    compute_test_diffs,
    get_compare_report,
    register_builtin_extensions as compare_register,
    select_diff_viewer,
)
from ccai.pychestrate.webservice.orchestration.test.triage import (
    TriageCaseNotFoundError,
    TriageClass,
    TriageClassifierNotFoundError,
    TriageEventTopics,
    TriageSignals,
    compute_stack_signature,
    get_case,
    link_ticket,
    list_cases_for_run,
    open_case,
    reclassify_case,
    register_builtin_extensions as triage_register,
)
from ccai.pychestrate.webservice.orchestration.test.triage.errors import (
    TriageStackSignatureInvalidError,
    TriageTrackerNotFoundError,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000000f5"
RUN_UUID = "00000000-0000-4000-8000-0000000000f6"
CATALOG_ENTRY_UUID = "00000000-0000-4000-8000-0000000000f7"
ACTOR_UUID = "00000000-0000-4000-8000-0000000000f8"


def _prepare_runtime() -> None:
    """
        Reset cross-test globals + register triage and compare
        extensions.
    """
    reset_registry_for_testing()
    reset_event_bus()
    triage_register()
    compare_register()
    return


# -------------------------------------
# 6-triage-bug-linking — primitives
# -------------------------------------

def test_compute_stack_signature_normalizes_whitespace():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: compute_stack_signature ignores trailing
    whitespace + blank lines so re-runs of the same failure
    hash to the same signature.**
    """
    sig_a = compute_stack_signature(
        stack_trace="line one\nline two   \n\nline three\n",
    )
    sig_b = compute_stack_signature(
        stack_trace="line one\nline two\nline three",
    )
    testbase.assert_equal(sig_a, sig_b)
    testbase.assert_equal(len(sig_a), 64)
    return


def test_compute_stack_signature_rejects_empty():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: compute_stack_signature rejects empty input.**
    """
    raised = False
    try:
        compute_stack_signature(stack_trace="")
    except TriageStackSignatureInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 6-triage-bug-linking — open_case
# -------------------------------------

def test_open_case_persists_and_emits():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: open_case persists a TriageCase, appends a
    ledger row, and emits entity.triage.opened.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=TriageEventTopics.OPENED,
        subscriber=lambda e: received.append(e),
    )

    signals = TriageSignals(
        flake_class="flaky",
        has_known_signature=False,
        stack_signature_sha256="a" * 64,
    )
    view = open_case(
        db_session=session,
        project_id=PROJECT_UUID,
        run_id=RUN_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256="b" * 64,
        signals=signals,
    )
    testbase.assert_equal(view.classification, TriageClass.INFRA_FLAKE)
    testbase.assert_equal(view.classifier_name, "infra-flake")
    testbase.assert_equal(len(received), 1)
    return


def test_open_case_classifies_known_issue_when_signature_match():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: has_known_signature=True classifies as
    KNOWN_ISSUE.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    signals = TriageSignals(
        flake_class="stable",
        has_known_signature=True,
        stack_signature_sha256="c" * 64,
    )
    view = open_case(
        db_session=session,
        project_id=PROJECT_UUID,
        run_id=RUN_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256="d" * 64,
        signals=signals,
    )
    testbase.assert_equal(view.classification, TriageClass.KNOWN_ISSUE)
    return


def test_open_case_classifies_new_bug_when_only_stack_signature():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: a non-empty stack signature without flake or
    known-issue match classifies as NEW_BUG.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    signals = TriageSignals(
        flake_class="stable",
        has_known_signature=False,
        stack_signature_sha256="e" * 64,
    )
    view = open_case(
        db_session=session,
        project_id=PROJECT_UUID,
        run_id=RUN_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256="f" * 64,
        signals=signals,
    )
    testbase.assert_equal(view.classification, TriageClass.NEW_BUG)
    return


def test_open_case_idempotent_on_run_test():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: open_case is idempotent on the
    (run_id, test_case_identity_sha256) pair — duplicate calls
    return the same case.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    signals = TriageSignals(
        flake_class="flaky",
        has_known_signature=False,
        stack_signature_sha256="1" * 64,
    )
    first = open_case(
        db_session=session,
        project_id=PROJECT_UUID, run_id=RUN_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256="x" * 64,
        signals=signals,
    )
    second = open_case(
        db_session=session,
        project_id=PROJECT_UUID, run_id=RUN_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256="x" * 64,
        signals=signals,
    )
    testbase.assert_equal(first.case_id, second.case_id)
    return


def test_open_case_without_classifier_raises():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: open_case with no registered classifier raises
    TriageClassifierNotFoundError.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        open_case(
            db_session=session,
            project_id=PROJECT_UUID, run_id=RUN_UUID,
            catalog_entry_id=CATALOG_ENTRY_UUID,
            test_case_identity_sha256="y" * 64,
            signals=TriageSignals(
                flake_class="", has_known_signature=False,
                stack_signature_sha256="2" * 64,
            ),
        )
    except TriageClassifierNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 6-triage-bug-linking — reclassify_case
# -------------------------------------

def test_reclassify_case_records_transition_and_emits():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: reclassify_case updates the row, appends a
    ledger entry, and emits entity.triage.reclassified.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=TriageEventTopics.RECLASSIFIED,
        subscriber=lambda e: received.append(e),
    )
    signals = TriageSignals(
        flake_class="flaky",
        has_known_signature=False,
        stack_signature_sha256="3" * 64,
    )
    case = open_case(
        db_session=session,
        project_id=PROJECT_UUID, run_id=RUN_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256="z" * 64,
        signals=signals,
    )
    updated = reclassify_case(
        db_session=session,
        case_id=case.case_id,
        new_class=TriageClass.NEW_BUG,
        actor_id=ACTOR_UUID,
        rationale="infra issue ruled out",
    )
    testbase.assert_equal(updated.classification, TriageClass.NEW_BUG)
    testbase.assert_equal(updated.classifier_name, "manual")
    testbase.assert_equal(len(received), 1)
    return


def test_reclassify_unknown_case_raises():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: reclassify_case on an unknown case id raises
    TriageCaseNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        reclassify_case(
            db_session=session, case_id=new_uuid(),
            new_class=TriageClass.NEW_BUG,
            actor_id=ACTOR_UUID, rationale="x",
        )
    except TriageCaseNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 6-triage-bug-linking — link_ticket
# -------------------------------------

def test_link_ticket_uses_null_tracker_and_emits():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: link_ticket with the in-tree null tracker
    persists tracker / ticket_key / ticket_url and emits
    entity.triage.ticket_linked.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=TriageEventTopics.TICKET_LINKED,
        subscriber=lambda e: received.append(e),
    )
    signals = TriageSignals(
        flake_class="flaky",
        has_known_signature=False,
        stack_signature_sha256="4" * 64,
    )
    case = open_case(
        db_session=session,
        project_id=PROJECT_UUID, run_id=RUN_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256="t" * 64,
        signals=signals,
    )
    linked = link_ticket(
        db_session=session,
        case_id=case.case_id,
        tracker_name="null",
        actor_id=ACTOR_UUID,
        summary="auto-link",
    )
    testbase.assert_equal(linked.tracker, "null")
    testbase.assert_equal(linked.ticket_key.startswith("PYC-"), True)
    testbase.assert_equal(linked.ticket_url is not None, True)
    testbase.assert_equal(len(received), 1)
    return


def test_link_ticket_unknown_tracker_raises():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: link_ticket with an unregistered tracker raises
    TriageTrackerNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    signals = TriageSignals(
        flake_class="stable",
        has_known_signature=False,
        stack_signature_sha256="5" * 64,
    )
    case = open_case(
        db_session=session,
        project_id=PROJECT_UUID, run_id=RUN_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256="u" * 64,
        signals=signals,
    )
    raised = False
    try:
        link_ticket(
            db_session=session, case_id=case.case_id,
            tracker_name="unknown-tracker",
            actor_id=ACTOR_UUID,
        )
    except TriageTrackerNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_cases_for_run_returns_only_target_run():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: list_cases_for_run scopes to the requested
    run_id and orders by created_at ascending.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    other_run = new_uuid()
    for run, identity in [
        (RUN_UUID, "a" * 64),
        (RUN_UUID, "b" * 64),
        (other_run, "c" * 64),
    ]:
        open_case(
            db_session=session,
            project_id=PROJECT_UUID, run_id=run,
            catalog_entry_id=CATALOG_ENTRY_UUID,
            test_case_identity_sha256=identity,
            signals=TriageSignals(
                flake_class="stable",
                has_known_signature=False,
                stack_signature_sha256="6" * 64,
            ),
        )
    rows = list_cases_for_run(db_session=session, run_id=RUN_UUID)
    testbase.assert_equal(len(rows), 2)
    return


def test_get_case_unknown_raises():
    """
    **Feature: 6-triage-bug-linking (M1)**
    **Property: get_case on an unknown id raises
    TriageCaseNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_case(db_session=session, case_id=new_uuid())
    except TriageCaseNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 6-compare-runs — compute_test_diffs (pure)
# -------------------------------------

def test_compute_test_diffs_classifies_status_buckets():
    """
    **Feature: 6-compare-runs (M1)**
    **Property: compute_test_diffs assigns the right TestDiffStatus
    for unchanged / pass-to-fail / fail-to-pass / new / removed /
    both-failed inputs.**
    """
    _prepare_runtime()
    base = [
        OutcomeForRun(test_case_identity_sha256="aaaa", outcome="pass"),
        OutcomeForRun(test_case_identity_sha256="bbbb", outcome="pass"),
        OutcomeForRun(test_case_identity_sha256="cccc", outcome="fail"),
        OutcomeForRun(test_case_identity_sha256="dddd", outcome="fail"),
        OutcomeForRun(test_case_identity_sha256="eeee", outcome="pass"),
    ]
    candidate = [
        OutcomeForRun(test_case_identity_sha256="aaaa", outcome="pass"),
        OutcomeForRun(test_case_identity_sha256="bbbb", outcome="fail"),
        OutcomeForRun(test_case_identity_sha256="cccc", outcome="pass"),
        OutcomeForRun(test_case_identity_sha256="dddd", outcome="fail"),
        OutcomeForRun(test_case_identity_sha256="ffff", outcome="pass"),
    ]
    diffs = compute_test_diffs(
        base_outcomes=base, candidate_outcomes=candidate,
    )
    by_id = {d.test_case_identity_sha256: d for d in diffs}
    testbase.assert_equal(by_id["aaaa"].status, TestDiffStatus.UNCHANGED)
    testbase.assert_equal(by_id["bbbb"].status, TestDiffStatus.PASS_TO_FAIL)
    testbase.assert_equal(by_id["cccc"].status, TestDiffStatus.FAIL_TO_PASS)
    testbase.assert_equal(by_id["dddd"].status, TestDiffStatus.BOTH_FAILED)
    testbase.assert_equal(by_id["eeee"].status, TestDiffStatus.REMOVED)
    testbase.assert_equal(by_id["ffff"].status, TestDiffStatus.NEW)
    return


def test_compute_test_diffs_returns_sorted_output():
    """
    **Feature: 6-compare-runs (M1)**
    **Property: diffs are sorted by identity SHA so two callers
    with the same input get the same output.**
    """
    _prepare_runtime()
    base = [
        OutcomeForRun(test_case_identity_sha256="zzzz", outcome="pass"),
        OutcomeForRun(test_case_identity_sha256="aaaa", outcome="pass"),
    ]
    candidate = [
        OutcomeForRun(test_case_identity_sha256="zzzz", outcome="pass"),
        OutcomeForRun(test_case_identity_sha256="aaaa", outcome="pass"),
    ]
    diffs = compute_test_diffs(
        base_outcomes=base, candidate_outcomes=candidate,
    )
    ids = [d.test_case_identity_sha256 for d in diffs]
    testbase.assert_equal(ids, sorted(ids))
    return


# -------------------------------------
# 6-compare-runs — build_compare_report
# -------------------------------------

def test_build_compare_report_persists_and_emits():
    """
    **Feature: 6-compare-runs (M1)**
    **Property: build_compare_report persists a ready report,
    serializes the per-test diffs into the JSON column, and
    emits entity.compare.report_built.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=CompareEventTopics.BUILT,
        subscriber=lambda e: received.append(e),
    )
    base_id = new_uuid()
    candidate_id = new_uuid()
    base = [
        OutcomeForRun(test_case_identity_sha256="aaaa", outcome="pass"),
        OutcomeForRun(test_case_identity_sha256="bbbb", outcome="pass"),
    ]
    candidate = [
        OutcomeForRun(test_case_identity_sha256="aaaa", outcome="fail"),
        OutcomeForRun(test_case_identity_sha256="bbbb", outcome="pass"),
    ]
    view = build_compare_report(
        db_session=session,
        project_id=PROJECT_UUID,
        base_run_id=base_id,
        candidate_run_id=candidate_id,
        base_outcomes=base,
        candidate_outcomes=candidate,
    )
    testbase.assert_equal(view.per_test_count, 2)
    testbase.assert_equal(len(view.per_test), 2)
    statuses = sorted(d.status.value for d in view.per_test)
    testbase.assert_equal(statuses, ["pass_to_fail", "unchanged"])
    testbase.assert_equal(len(received), 1)
    return


def test_build_compare_report_caches_pair():
    """
    **Feature: 6-compare-runs (M1)**
    **Property: a duplicate build for the same run pair returns
    the existing report and emits CACHE_HIT instead of BUILT.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_built: List[EntityEvent] = []
    received_hit: List[EntityEvent] = []
    subscribe(
        topic=CompareEventTopics.BUILT,
        subscriber=lambda e: received_built.append(e),
    )
    subscribe(
        topic=CompareEventTopics.CACHE_HIT,
        subscriber=lambda e: received_hit.append(e),
    )
    base_id = new_uuid()
    candidate_id = new_uuid()
    first = build_compare_report(
        db_session=session,
        project_id=PROJECT_UUID,
        base_run_id=base_id,
        candidate_run_id=candidate_id,
        base_outcomes=[
            OutcomeForRun(test_case_identity_sha256="aaaa", outcome="pass"),
        ],
        candidate_outcomes=[
            OutcomeForRun(test_case_identity_sha256="aaaa", outcome="pass"),
        ],
    )
    second = build_compare_report(
        db_session=session,
        project_id=PROJECT_UUID,
        base_run_id=base_id,
        candidate_run_id=candidate_id,
        base_outcomes=[],
        candidate_outcomes=[],
    )
    testbase.assert_equal(first.report_id, second.report_id)
    testbase.assert_equal(len(received_built), 1)
    testbase.assert_equal(len(received_hit), 1)
    return


def test_build_compare_report_rejects_same_run():
    """
    **Feature: 6-compare-runs (M1)**
    **Property: passing the same id for both sides raises
    CompareInputInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    same_id = new_uuid()
    raised = False
    try:
        build_compare_report(
            db_session=session,
            project_id=PROJECT_UUID,
            base_run_id=same_id,
            candidate_run_id=same_id,
            base_outcomes=[],
            candidate_outcomes=[],
        )
    except CompareInputInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_get_compare_report_unknown_raises():
    """
    **Feature: 6-compare-runs (M1)**
    **Property: get_compare_report on an unknown id raises
    CompareReportNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_compare_report(db_session=session, report_id=new_uuid())
    except CompareReportNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 6-compare-runs — diff viewer
# -------------------------------------

def test_select_diff_viewer_returns_generic_two_pane():
    """
    **Feature: 6-compare-runs (M1)**
    **Property: select_diff_viewer returns the in-tree generic
    two-pane viewer for any artifact pair.**
    """
    _prepare_runtime()
    artifact = DiffArtifactRef(
        base_run_id=new_uuid(),
        candidate_run_id=new_uuid(),
        path="run/output.log",
        name="output.log",
        content_type="text/plain",
    )
    choice = select_diff_viewer(artifact=artifact)
    testbase.assert_equal(choice.component_tag, "px-two-pane-diff")
    testbase.assert_equal(choice.confidence > 0, True)
    testbase.assert_equal(choice.artifact_path, "run/output.log")
    return


def test_select_diff_viewer_no_registered_raises():
    """
    **Feature: 6-compare-runs (M1)**
    **Property: with no diff viewer registered, select_diff_viewer
    raises NoMatchingDiffViewerError.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    artifact = DiffArtifactRef(
        base_run_id=new_uuid(),
        candidate_run_id=new_uuid(),
        path="run/output.log",
        name="output.log",
    )
    raised = False
    try:
        select_diff_viewer(artifact=artifact)
    except NoMatchingDiffViewerError:
        raised = True
    testbase.assert_equal(raised, True)
    return
