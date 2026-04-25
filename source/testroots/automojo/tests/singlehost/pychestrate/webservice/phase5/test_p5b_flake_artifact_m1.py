"""
.. module:: test_p5b_flake_artifact_m1
    :synopsis: Tests for P5b — 6-flake-tracking + 6-artifact-browser M1.
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
from automojo.pychestrate.webservice.orchestration.test.artifact_browser import (
    ArtifactPathInvalidError,
    ArtifactRef,
    NoMatchingRendererError,
    list_renderer_records,
    register_builtin_extensions as artifact_register,
    select_renderer,
)
from automojo.pychestrate.webservice.orchestration.test.flake import (
    FlakeClass,
    FlakeClassificationNotFoundError,
    FlakeClassifierNotFoundError,
    FlakeEventTopics,
    Outcome,
    OutcomeIdentityInvalidError,
    classify_for_test_case,
    clear_quarantine,
    get_classification,
    list_history_for_test_case,
    record_outcome,
    register_builtin_extensions as flake_register,
    set_quarantine,
)
from automojo.pychestrate.webservice.orchestration.test.flake.service import (
    hash_test_case_identity,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-0000000000e5"
CATALOG_ENTRY_UUID = "00000000-0000-4000-8000-0000000000e6"
ACTOR_UUID = "00000000-0000-4000-8000-0000000000e7"


def _prepare_runtime_with_flake() -> None:
    """
        Reset cross-test globals + register the flake +
        artifact-browser extensions.
    """
    reset_registry_for_testing()
    reset_event_bus()
    flake_register()
    artifact_register()
    return


def _seed_outcomes(*, session, identity_sha: str, outcomes: List[Outcome]):
    """
        Helper: seed a sequence of outcomes spaced 1 minute
        apart, oldest first.
    """
    base = utc_now() - timedelta(minutes=len(outcomes))
    for index, outcome in enumerate(outcomes):
        record_outcome(
            db_session=session,
            project_id=PROJECT_UUID,
            catalog_entry_id=CATALOG_ENTRY_UUID,
            test_case_identity_sha256=identity_sha,
            run_id=new_uuid(),
            runtime_env_digest="",
            outcome=outcome,
            duration_ms=100,
            started_at=base + timedelta(minutes=index),
        )
    return


# -------------------------------------
# 6-flake-tracking — primitives
# -------------------------------------

def test_hash_test_case_identity_rejects_empty_and_oversized():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: hash_test_case_identity rejects empty + oversized
    raw identities; otherwise returns a 64-char SHA-256 hex.**
    """
    digest = hash_test_case_identity(
        raw_identity="suite::module::case[matrix=linux]",
    )
    testbase.assert_equal(len(digest), 64)

    raised_empty = False
    try:
        hash_test_case_identity(raw_identity="")
    except OutcomeIdentityInvalidError:
        raised_empty = True
    testbase.assert_equal(raised_empty, True)

    raised_long = False
    try:
        hash_test_case_identity(raw_identity="x" * 5000)
    except OutcomeIdentityInvalidError:
        raised_long = True
    testbase.assert_equal(raised_long, True)
    return


# -------------------------------------
# 6-flake-tracking — record_outcome
# -------------------------------------

def test_record_outcome_persists_and_emits():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: record_outcome persists a TestOutcome row and
    emits entity.flake.outcome_recorded.**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=FlakeEventTopics.OUTCOME_RECORDED,
        subscriber=lambda e: received.append(e),
    )

    identity = hash_test_case_identity(raw_identity="case::a")
    row = record_outcome(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
        run_id=new_uuid(),
        runtime_env_digest="",
        outcome=Outcome.PASS,
        duration_ms=42,
    )
    testbase.assert_equal(row.outcome, Outcome.PASS)
    testbase.assert_equal(row.duration_ms, 42)
    testbase.assert_equal(len(received), 1)
    return


def test_record_outcome_idempotent_per_run_identity():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: re-recording the same (run_id, identity) returns
    the existing row without re-emitting.**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=FlakeEventTopics.OUTCOME_RECORDED,
        subscriber=lambda e: received.append(e),
    )
    identity = hash_test_case_identity(raw_identity="case::dup")
    run_id = new_uuid()
    first = record_outcome(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
        run_id=run_id,
        runtime_env_digest="",
        outcome=Outcome.PASS,
        duration_ms=10,
    )
    second = record_outcome(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
        run_id=run_id,
        runtime_env_digest="",
        outcome=Outcome.PASS,
        duration_ms=10,
    )
    testbase.assert_equal(first.outcome_id, second.outcome_id)
    testbase.assert_equal(len(received), 1)
    return


# -------------------------------------
# 6-flake-tracking — classify_for_test_case
# -------------------------------------

def test_classify_returns_insufficient_data_below_min_samples():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: a history below the classifier's min_samples
    returns INSUFFICIENT_DATA with the below-min-samples
    rationale.**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    identity = hash_test_case_identity(raw_identity="case::few")
    _seed_outcomes(
        session=session, identity_sha=identity,
        outcomes=[Outcome.PASS],
    )
    view = classify_for_test_case(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
    )
    testbase.assert_equal(view.classification, FlakeClass.INSUFFICIENT_DATA)
    testbase.assert_equal(view.rationale_tag, "below-min-samples")
    return


def test_classify_returns_stable_for_all_pass_history():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: an all-PASS window classifies as STABLE.**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=FlakeEventTopics.CLASSIFIED,
        subscriber=lambda e: received.append(e),
    )

    identity = hash_test_case_identity(raw_identity="case::stable")
    _seed_outcomes(
        session=session, identity_sha=identity,
        outcomes=[Outcome.PASS] * 10,
    )
    view = classify_for_test_case(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
    )
    testbase.assert_equal(view.classification, FlakeClass.STABLE)
    testbase.assert_equal(view.classifier_name, "window-ratio")
    testbase.assert_equal(len(received), 1)
    return


def test_classify_returns_broken_when_no_recent_pass():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: no PASS in the broken window classifies as BROKEN.**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    identity = hash_test_case_identity(raw_identity="case::broken")
    # 2 historical PASS, then 6 FAIL — recent broken window has no PASS.
    _seed_outcomes(
        session=session, identity_sha=identity,
        outcomes=[Outcome.PASS, Outcome.PASS]
        + [Outcome.FAIL] * 6,
    )
    view = classify_for_test_case(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
    )
    testbase.assert_equal(view.classification, FlakeClass.BROKEN)
    return


def test_classify_returns_flaky_for_alternating_outcomes():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: 2+ PASS↔FAIL transitions classify as FLAKY.**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    identity = hash_test_case_identity(raw_identity="case::flaky")
    _seed_outcomes(
        session=session, identity_sha=identity,
        outcomes=[
            Outcome.PASS, Outcome.FAIL, Outcome.PASS, Outcome.FAIL,
            Outcome.PASS,
        ],
    )
    view = classify_for_test_case(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
    )
    testbase.assert_equal(view.classification, FlakeClass.FLAKY)
    testbase.assert_equal("transitions" in view.rationale_tag, True)
    return


def test_classify_without_registered_classifier_raises():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: classify_for_test_case with no registered
    classifier raises FlakeClassifierNotFoundError.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    _engine, session = build_in_memory_session()
    identity = hash_test_case_identity(raw_identity="case::no-classifier")
    raised = False
    try:
        classify_for_test_case(
            db_session=session,
            project_id=PROJECT_UUID,
            catalog_entry_id=CATALOG_ENTRY_UUID,
            test_case_identity_sha256=identity,
        )
    except FlakeClassifierNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 6-flake-tracking — quarantine
# -------------------------------------

def test_set_quarantine_overrides_classifier_output():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: set_quarantine flips the classification to
    QUARANTINED, emits entity.flake.quarantined, and a
    subsequent classify_for_test_case keeps it QUARANTINED
    (sticky override).**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=FlakeEventTopics.QUARANTINED,
        subscriber=lambda e: received.append(e),
    )

    identity = hash_test_case_identity(raw_identity="case::quarantine")
    _seed_outcomes(
        session=session, identity_sha=identity,
        outcomes=[Outcome.PASS] * 10,
    )
    view = set_quarantine(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
        runtime_env_digest=None,
        actor_id=ACTOR_UUID,
        reason="known-bad",
    )
    testbase.assert_equal(view.classification, FlakeClass.QUARANTINED)
    testbase.assert_equal(len(received), 1)

    # A subsequent classify keeps it QUARANTINED.
    view_after = classify_for_test_case(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
    )
    testbase.assert_equal(view_after.classification, FlakeClass.QUARANTINED)
    return


def test_clear_quarantine_recomputes_classification():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: clear_quarantine emits the cleared topic, drops
    the override, and the returned view reflects the natural
    classifier output.**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    received_cleared: List[EntityEvent] = []
    received_classified: List[EntityEvent] = []
    subscribe(
        topic=FlakeEventTopics.QUARANTINE_CLEARED,
        subscriber=lambda e: received_cleared.append(e),
    )
    subscribe(
        topic=FlakeEventTopics.CLASSIFIED,
        subscriber=lambda e: received_classified.append(e),
    )

    identity = hash_test_case_identity(raw_identity="case::clear")
    _seed_outcomes(
        session=session, identity_sha=identity,
        outcomes=[Outcome.PASS] * 10,
    )
    set_quarantine(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
        runtime_env_digest=None,
        actor_id=ACTOR_UUID,
        reason="oops",
    )
    view = clear_quarantine(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
        runtime_env_digest=None,
        actor_id=ACTOR_UUID,
        reason="resolved",
    )
    testbase.assert_equal(view.classification, FlakeClass.STABLE)
    testbase.assert_equal(len(received_cleared), 1)
    testbase.assert_equal(len(received_classified), 1)
    return


def test_get_classification_unknown_raises():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: get_classification on a never-classified test
    raises FlakeClassificationNotFoundError.**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_classification(
            db_session=session,
            project_id=PROJECT_UUID,
            catalog_entry_id=CATALOG_ENTRY_UUID,
            test_case_identity_sha256="x" * 64,
        )
    except FlakeClassificationNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_history_returns_newest_first():
    """
    **Feature: 6-flake-tracking (M1)**
    **Property: list_history_for_test_case returns samples
    newest-first.**
    """
    _prepare_runtime_with_flake()
    _engine, session = build_in_memory_session()
    identity = hash_test_case_identity(raw_identity="case::history")
    _seed_outcomes(
        session=session, identity_sha=identity,
        outcomes=[Outcome.PASS, Outcome.FAIL, Outcome.PASS],
    )
    window = list_history_for_test_case(
        db_session=session,
        project_id=PROJECT_UUID,
        catalog_entry_id=CATALOG_ENTRY_UUID,
        test_case_identity_sha256=identity,
    )
    testbase.assert_equal(len(window.outcomes), 3)
    timestamps = [s.started_at for s in window.outcomes]
    testbase.assert_equal(timestamps, sorted(timestamps, reverse=True))
    return


# -------------------------------------
# 6-artifact-browser
# -------------------------------------

def test_select_renderer_picks_log_for_log_classifier_tag():
    """
    **Feature: 6-artifact-browser (M1)**
    **Property: an artifact tagged "log" picks the log-stream
    renderer over the plain-text fallback.**
    """
    _prepare_runtime_with_flake()
    artifact = ArtifactRef(
        run_id=new_uuid(),
        path="run/output.log",
        name="output.log",
        content_type="text/plain",
        classifier_tag="log",
    )
    choice = select_renderer(artifact=artifact)
    testbase.assert_equal(choice.component_tag, "px-log-stream")
    testbase.assert_equal(choice.confidence > 100, True)
    testbase.assert_equal(choice.run_id, artifact.run_id)
    return


def test_select_renderer_falls_back_to_plain_text_for_text_files():
    """
    **Feature: 6-artifact-browser (M1)**
    **Property: a text/* artifact with no classifier tag and no
    log-shaped name picks the plain-text renderer.**
    """
    _prepare_runtime_with_flake()
    artifact = ArtifactRef(
        run_id=new_uuid(),
        path="run/notes.txt",
        name="notes.txt",
        content_type="text/plain",
        classifier_tag="",
    )
    choice = select_renderer(artifact=artifact)
    testbase.assert_equal(choice.component_tag, "px-plain-text")
    return


def test_select_renderer_picks_log_renderer_by_suffix():
    """
    **Feature: 6-artifact-browser (M1)**
    **Property: a .log filename without classifier metadata
    still wins for the log-stream renderer.**
    """
    _prepare_runtime_with_flake()
    artifact = ArtifactRef(
        run_id=new_uuid(),
        path="run/dispatcher.log",
        name="dispatcher.log",
        content_type="application/octet-stream",
    )
    choice = select_renderer(artifact=artifact)
    testbase.assert_equal(choice.component_tag, "px-log-stream")
    return


def test_select_renderer_no_match_raises():
    """
    **Feature: 6-artifact-browser (M1)**
    **Property: a non-text, non-log artifact falls through and
    raises NoMatchingRendererError naming the path and content
    type.**
    """
    _prepare_runtime_with_flake()
    artifact = ArtifactRef(
        run_id=new_uuid(),
        path="run/binary.dat",
        name="binary.dat",
        content_type="application/x-binary",
    )
    raised = False
    try:
        select_renderer(artifact=artifact)
    except NoMatchingRendererError as xcpt:
        raised = True
        testbase.assert_equal("binary.dat" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_select_renderer_rejects_path_traversal():
    """
    **Feature: 6-artifact-browser (M1)**
    **Property: an artifact path containing ".." raises
    ArtifactPathInvalidError before any renderer match runs.**
    """
    _prepare_runtime_with_flake()
    artifact = ArtifactRef(
        run_id=new_uuid(),
        path="run/../../etc/passwd",
        name="passwd",
        content_type="text/plain",
    )
    raised = False
    try:
        select_renderer(artifact=artifact)
    except ArtifactPathInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_renderer_records_returns_registered_renderers():
    """
    **Feature: 6-artifact-browser (M1)**
    **Property: list_renderer_records exposes both reference
    renderers in PRECEDENCE order.**
    """
    _prepare_runtime_with_flake()
    records = list_renderer_records()
    testbase.assert_equal(len(records), 2)
    tags = [r.component_tag for r in records]
    testbase.assert_equal("px-log-stream" in tags, True)
    testbase.assert_equal("px-plain-text" in tags, True)
    return
