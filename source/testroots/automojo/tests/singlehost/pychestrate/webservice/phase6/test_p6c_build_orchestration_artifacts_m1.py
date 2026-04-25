"""
.. module:: test_p6c_build_orchestration_artifacts_m1
    :synopsis: Tests for P6c — 6-build-orchestration + 6-build-artifacts M1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.extensions.registry import (
    reset_registry_for_testing,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    reset_for_testing as reset_event_bus,
    subscribe,
)
from automojo.pychestrate.webservice.orchestration.build import (
    BuildEventTopics,
    BuildInputsInvalidError,
    BuildRunInputs,
    BuildRunNotFoundError,
    BuildRunState,
    BuildRunnerKindUnknownError,
    BuildToolchainEntry,
    BuildTriggerAspects,
    ReproSnapshot,
    apply_run_terminal,
    compute_repro_digest,
    get_build_run,
    list_build_runs_for_project,
    register_builtin_extensions as build_register,
    trigger_run,
)
from automojo.pychestrate.webservice.orchestration.build.artifacts import (
    ArtifactEntry,
    ArtifactEntryInvalidError,
    ArtifactTypeUnknownError,
    BuildArtifactEventTopics,
    BuildArtifactManifestNotFoundError,
    get_channel_head,
    get_manifest,
    list_entries,
    promote_to_channel,
    register_builtin_extensions as artifacts_register,
    synthesize_manifest,
)

from automojo.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000030001"
ACTOR_UUID = "00000000-0000-4000-8000-000000030002"
LAYER5_UUID = "00000000-0000-4000-8000-000000030003"


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    build_register()
    artifacts_register()
    return


def _valid_makefile_inputs() -> BuildRunInputs:
    rtnval = BuildRunInputs(
        runner_kind="makefile",
        runner_inputs={
            "targets": ["build"],
            "makefile_path": "Makefile",
            "parallelism": 4,
        },
        input_files={"Makefile": "abc123", "src/main.c": "deadbeef"},
        toolchain=(
            BuildToolchainEntry(
                key="gcc", version="13.2.0",
                fingerprint_sha256="aaaaaaaa",
            ),
        ),
        env={"OS": "linux", "ARCH": "x86_64"},
    )
    return rtnval


# -------------------------------------
# 6-build-orchestration — repro digest
# -------------------------------------

def test_repro_digest_is_stable_across_input_orders():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: compute_repro_digest is identical when input
    files / env / toolchain are passed in different
    iteration orders.**
    """
    _prepare_runtime()
    snap_a = ReproSnapshot(
        input_files={"a.c": "1", "b.c": "2"},
        toolchain=(
            BuildToolchainEntry(key="gcc", version="13.2.0"),
            BuildToolchainEntry(key="make", version="4.4"),
        ),
        env={"OS": "linux", "ARCH": "x86_64"},
    )
    snap_b = ReproSnapshot(
        input_files={"b.c": "2", "a.c": "1"},
        toolchain=(
            BuildToolchainEntry(key="make", version="4.4"),
            BuildToolchainEntry(key="gcc", version="13.2.0"),
        ),
        env={"ARCH": "x86_64", "OS": "linux"},
    )
    testbase.assert_equal(
        compute_repro_digest(snapshot=snap_a),
        compute_repro_digest(snapshot=snap_b),
    )
    return


def test_repro_digest_changes_with_input_changes():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: changing any input file content yields a
    different digest.**
    """
    _prepare_runtime()
    base = ReproSnapshot(
        input_files={"a.c": "1"},
        toolchain=(BuildToolchainEntry(key="gcc", version="13.2.0"),),
    )
    drift = ReproSnapshot(
        input_files={"a.c": "2"},
        toolchain=(BuildToolchainEntry(key="gcc", version="13.2.0"),),
    )
    testbase.assert_equal(
        compute_repro_digest(snapshot=base)
        != compute_repro_digest(snapshot=drift),
        True,
    )
    return


# -------------------------------------
# 6-build-orchestration — trigger_run
# -------------------------------------

def test_trigger_run_persists_and_emits():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: trigger_run persists a BuildRun in PENDING +
    toolchain rows + emits entity.build.run_triggered.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=BuildEventTopics.TRIGGERED,
        subscriber=lambda e: received.append(e),
    )
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_makefile_inputs(),
        aspects=BuildTriggerAspects(actor_id=ACTOR_UUID),
    )
    testbase.assert_equal(view.state, BuildRunState.PENDING)
    testbase.assert_equal(view.runner_kind, "makefile")
    testbase.assert_equal(view.actor_id, ACTOR_UUID)
    testbase.assert_equal(len(view.repro_digest_sha256), 64)
    testbase.assert_equal(len(view.toolchain), 1)
    testbase.assert_equal(view.toolchain[0].toolchain_key, "gcc")
    testbase.assert_equal(len(received), 1)
    return


def test_trigger_run_unknown_runner_raises():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: an unknown runner_kind raises
    BuildRunnerKindUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    bad = BuildRunInputs(
        runner_kind="unknown-kind",
        runner_inputs={"targets": ["build"]},
    )
    raised = False
    try:
        trigger_run(
            db_session=session, project_id=PROJECT_UUID, inputs=bad,
        )
    except BuildRunnerKindUnknownError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_trigger_run_invalid_inputs_raise():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: a runner-kind validate_inputs rejection raises
    BuildInputsInvalidError listing every issue.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    bad = BuildRunInputs(
        runner_kind="makefile",
        runner_inputs={
            "targets": [],
            "makefile_path": "",
            "parallelism": -1,
        },
    )
    raised = False
    try:
        trigger_run(
            db_session=session, project_id=PROJECT_UUID, inputs=bad,
        )
    except BuildInputsInvalidError as xcpt:
        raised = True
        testbase.assert_equal("targets" in str(xcpt), True)
        testbase.assert_equal("parallelism" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_trigger_run_empty_runner_kind_raises():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: an empty runner_kind raises
    BuildInputsInvalidError before factory resolution.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    bad = BuildRunInputs(runner_kind="", runner_inputs={"targets": ["x"]})
    raised = False
    try:
        trigger_run(
            db_session=session, project_id=PROJECT_UUID, inputs=bad,
        )
    except BuildInputsInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 6-build-orchestration — apply_run_terminal
# -------------------------------------

def test_apply_run_terminal_completed_emits_topics():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: completing a build emits STATE_CHANGED +
    COMPLETED; layer5_run_id is recorded.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_state: List[EntityEvent] = []
    received_completed: List[EntityEvent] = []
    subscribe(
        topic=BuildEventTopics.STATE_CHANGED,
        subscriber=lambda e: received_state.append(e),
    )
    subscribe(
        topic=BuildEventTopics.COMPLETED,
        subscriber=lambda e: received_completed.append(e),
    )
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_makefile_inputs(),
    )
    completed = apply_run_terminal(
        db_session=session,
        run_id=view.run_id,
        final_state=BuildRunState.COMPLETED,
        layer5_run_id=LAYER5_UUID,
        reason="ok",
    )
    testbase.assert_equal(completed.state, BuildRunState.COMPLETED)
    testbase.assert_equal(completed.layer5_run_id, LAYER5_UUID)
    testbase.assert_equal(len(received_state), 1)
    testbase.assert_equal(len(received_completed), 1)
    return


def test_apply_run_terminal_failed_emits_failed_topic():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: a FAILED terminal emits the FAILED topic, not
    COMPLETED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_failed: List[EntityEvent] = []
    received_completed: List[EntityEvent] = []
    subscribe(
        topic=BuildEventTopics.FAILED,
        subscriber=lambda e: received_failed.append(e),
    )
    subscribe(
        topic=BuildEventTopics.COMPLETED,
        subscriber=lambda e: received_completed.append(e),
    )
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_makefile_inputs(),
    )
    apply_run_terminal(
        db_session=session,
        run_id=view.run_id,
        final_state=BuildRunState.FAILED,
        reason="exit-code-1",
    )
    testbase.assert_equal(len(received_failed), 1)
    testbase.assert_equal(len(received_completed), 0)
    return


def test_apply_run_terminal_idempotent():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: calling apply_run_terminal a second time on a
    terminal row is a no-op (no new events fire).**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=BuildEventTopics.COMPLETED,
        subscriber=lambda e: received.append(e),
    )
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_makefile_inputs(),
    )
    apply_run_terminal(
        db_session=session,
        run_id=view.run_id,
        final_state=BuildRunState.COMPLETED,
    )
    apply_run_terminal(
        db_session=session,
        run_id=view.run_id,
        final_state=BuildRunState.COMPLETED,
    )
    testbase.assert_equal(len(received), 1)
    return


def test_apply_run_terminal_non_terminal_state_raises():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: passing a non-terminal state raises
    BuildInputsInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        inputs=_valid_makefile_inputs(),
    )
    raised = False
    try:
        apply_run_terminal(
            db_session=session,
            run_id=view.run_id,
            final_state=BuildRunState.RUNNING,
        )
    except BuildInputsInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_get_build_run_unknown_raises():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: get_build_run on an unknown id raises
    BuildRunNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_build_run(db_session=session, run_id=new_uuid())
    except BuildRunNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_list_build_runs_scopes_to_project():
    """
    **Feature: 6-build-orchestration (M1)**
    **Property: list_build_runs_for_project returns only the
    target project's rows.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    other_project = new_uuid()
    trigger_run(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_makefile_inputs(),
    )
    trigger_run(
        db_session=session, project_id=PROJECT_UUID,
        inputs=_valid_makefile_inputs(),
    )
    trigger_run(
        db_session=session, project_id=other_project,
        inputs=_valid_makefile_inputs(),
    )
    rows = list_build_runs_for_project(
        db_session=session, project_id=PROJECT_UUID,
    )
    testbase.assert_equal(len(rows), 2)
    return


# -------------------------------------
# 6-build-artifacts — synthesize_manifest
# -------------------------------------

def test_synthesize_manifest_persists_and_emits():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: synthesize_manifest creates a manifest +
    entries; emits MANIFEST_SYNTHESIZED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=BuildArtifactEventTopics.MANIFEST_SYNTHESIZED,
        subscriber=lambda e: received.append(e),
    )

    build_run_id = new_uuid()
    valid_entries = [
        ArtifactEntry(
            artifact_id="api-image",
            artifact_type="container-image",
            artifact_name="api",
            storage_uri="s3://artifacts/api",
            sha256="a" * 64,
            payload={
                "registry": "registry.example.com",
                "repository": "team/api",
                "digest": "sha256:" + "b" * 64,
                "tag": "v1.0.0",
            },
        ),
        ArtifactEntry(
            artifact_id="worker-image",
            artifact_type="container-image",
            artifact_name="worker",
            storage_uri="s3://artifacts/worker",
            sha256="c" * 64,
            payload={
                "registry": "registry.example.com",
                "repository": "team/worker",
                "digest": "sha256:" + "d" * 64,
            },
        ),
    ]
    view = synthesize_manifest(
        db_session=session,
        project_id=PROJECT_UUID,
        build_run_id=build_run_id,
        entries=valid_entries,
        note="release-build",
    )
    testbase.assert_equal(view.entry_count, 2)
    testbase.assert_equal(len(view.entries), 2)
    testbase.assert_equal(view.entries[0].artifact_id, "api-image")
    testbase.assert_equal(len(received), 1)
    return


def test_synthesize_manifest_idempotent_per_build_run():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: a second synthesize_manifest for the same
    build_run_id returns the existing manifest without
    re-emitting.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=BuildArtifactEventTopics.MANIFEST_SYNTHESIZED,
        subscriber=lambda e: received.append(e),
    )
    build_run_id = new_uuid()
    entry = ArtifactEntry(
        artifact_id="img",
        artifact_type="container-image",
        artifact_name="img",
        storage_uri="s3://artifacts/img",
        sha256="e" * 64,
        payload={
            "registry": "r.example.com",
            "repository": "team/img",
            "digest": "sha256:" + "f" * 64,
        },
    )
    first = synthesize_manifest(
        db_session=session, project_id=PROJECT_UUID,
        build_run_id=build_run_id, entries=[entry],
    )
    second = synthesize_manifest(
        db_session=session, project_id=PROJECT_UUID,
        build_run_id=build_run_id, entries=[entry],
    )
    testbase.assert_equal(first.manifest_id, second.manifest_id)
    testbase.assert_equal(len(received), 1)
    return


def test_synthesize_manifest_unknown_type_raises():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: an unknown artifact_type raises
    ArtifactTypeUnknownError naming the kind.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        synthesize_manifest(
            db_session=session, project_id=PROJECT_UUID,
            build_run_id=new_uuid(),
            entries=[
                ArtifactEntry(
                    artifact_id="x",
                    artifact_type="unknown-type",
                    artifact_name="x",
                    storage_uri="",
                    sha256="0" * 64,
                ),
            ],
        )
    except ArtifactTypeUnknownError as xcpt:
        raised = True
        testbase.assert_equal("unknown-type" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_synthesize_manifest_validates_entry_payload():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: an entry whose payload fails the type's
    validate_payload raises ArtifactEntryInvalidError listing
    every issue.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    bad_entry = ArtifactEntry(
        artifact_id="bad",
        artifact_type="container-image",
        artifact_name="bad",
        storage_uri="",
        sha256="g" * 63,  # wrong length
        payload={
            # missing registry, repository
            "digest": "deadbeef",  # missing sha256: prefix + wrong len
        },
    )
    raised = False
    try:
        synthesize_manifest(
            db_session=session, project_id=PROJECT_UUID,
            build_run_id=new_uuid(),
            entries=[bad_entry],
        )
    except ArtifactEntryInvalidError as xcpt:
        raised = True
        msg = str(xcpt)
        testbase.assert_equal("registry" in msg, True)
        testbase.assert_equal("digest" in msg, True)
        testbase.assert_equal("sha256" in msg, True)
    testbase.assert_equal(raised, True)
    return


def test_synthesize_manifest_rejects_duplicate_artifact_ids():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: two entries sharing the same artifact_id raise
    ArtifactEntryInvalidError naming the duplicate.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()

    def _entry(artifact_id: str) -> ArtifactEntry:
        return ArtifactEntry(
            artifact_id=artifact_id,
            artifact_type="container-image",
            artifact_name=artifact_id,
            storage_uri="s3://x",
            sha256="a" * 64,
            payload={
                "registry": "r.example.com",
                "repository": "team/" + artifact_id,
                "digest": "sha256:" + "b" * 64,
            },
        )

    raised = False
    try:
        synthesize_manifest(
            db_session=session, project_id=PROJECT_UUID,
            build_run_id=new_uuid(),
            entries=[_entry("dup"), _entry("dup")],
        )
    except ArtifactEntryInvalidError as xcpt:
        raised = True
        testbase.assert_equal("dup" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_get_manifest_unknown_raises():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: get_manifest on an unknown id raises
    BuildArtifactManifestNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_manifest(db_session=session, manifest_id=new_uuid())
    except BuildArtifactManifestNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# 6-build-artifacts — promote_to_channel
# -------------------------------------

def test_promote_to_channel_advances_head_and_emits():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: promote_to_channel records a ledger row,
    upserts the channel-head pointer, and emits PROMOTED +
    CHANNEL_HEAD_ADVANCED.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_promoted: List[EntityEvent] = []
    received_advanced: List[EntityEvent] = []
    subscribe(
        topic=BuildArtifactEventTopics.PROMOTED,
        subscriber=lambda e: received_promoted.append(e),
    )
    subscribe(
        topic=BuildArtifactEventTopics.CHANNEL_HEAD_ADVANCED,
        subscriber=lambda e: received_advanced.append(e),
    )
    build_run_id = new_uuid()
    entry = ArtifactEntry(
        artifact_id="api-image",
        artifact_type="container-image",
        artifact_name="api",
        storage_uri="s3://artifacts/api",
        sha256="a" * 64,
        payload={
            "registry": "r.example.com",
            "repository": "team/api",
            "digest": "sha256:" + "b" * 64,
        },
    )
    manifest = synthesize_manifest(
        db_session=session, project_id=PROJECT_UUID,
        build_run_id=build_run_id, entries=[entry],
    )
    head = promote_to_channel(
        db_session=session,
        project_id=PROJECT_UUID,
        manifest_id=manifest.manifest_id,
        artifact_id="api-image",
        channel="staging",
        actor_id=ACTOR_UUID,
        note="ready for staging",
    )
    testbase.assert_equal(head.channel, "staging")
    testbase.assert_equal(head.manifest_id, manifest.manifest_id)
    testbase.assert_equal(len(received_promoted), 1)
    testbase.assert_equal(len(received_advanced), 1)

    # Channel head is readable.
    fetched = get_channel_head(
        db_session=session,
        project_id=PROJECT_UUID,
        channel="staging",
        artifact_id="api-image",
    )
    testbase.assert_equal(fetched is not None, True)
    testbase.assert_equal(fetched.manifest_id, manifest.manifest_id)
    return


def test_promote_unknown_manifest_raises():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: promote_to_channel on an unknown manifest_id
    raises BuildArtifactManifestNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        promote_to_channel(
            db_session=session,
            project_id=PROJECT_UUID,
            manifest_id=new_uuid(),
            artifact_id="x",
            channel="staging",
        )
    except BuildArtifactManifestNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_promote_artifact_not_in_manifest_raises():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: promoting an artifact_id absent from the
    manifest raises ArtifactEntryInvalidError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    build_run_id = new_uuid()
    entry = ArtifactEntry(
        artifact_id="api-image",
        artifact_type="container-image",
        artifact_name="api",
        storage_uri="s3://artifacts/api",
        sha256="a" * 64,
        payload={
            "registry": "r.example.com",
            "repository": "team/api",
            "digest": "sha256:" + "b" * 64,
        },
    )
    manifest = synthesize_manifest(
        db_session=session, project_id=PROJECT_UUID,
        build_run_id=build_run_id, entries=[entry],
    )
    raised = False
    try:
        promote_to_channel(
            db_session=session,
            project_id=PROJECT_UUID,
            manifest_id=manifest.manifest_id,
            artifact_id="missing-artifact",
            channel="staging",
        )
    except ArtifactEntryInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_get_channel_head_unknown_returns_none():
    """
    **Feature: 6-build-artifacts (M1)**
    **Property: get_channel_head on a non-existent (project,
    channel, artifact) triple returns None.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    head = get_channel_head(
        db_session=session, project_id=PROJECT_UUID,
        channel="prod", artifact_id="missing",
    )
    testbase.assert_equal(head is None, True)
    return
