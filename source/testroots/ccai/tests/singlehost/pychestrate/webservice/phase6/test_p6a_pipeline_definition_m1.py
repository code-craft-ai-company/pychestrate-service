"""
.. module:: test_p6a_pipeline_definition_m1
    :synopsis: Tests for P6a — 6-pipeline-definition M1.
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
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    PipelineDagCycleError,
    PipelineDocumentInvalidError,
    PipelineEventTopics,
    PipelineRunNotFoundError,
    PipelineRunState,
    PipelineStepKindUnknownError,
    StageState,
    StepState,
    TriggerAspects,
    TriggerCause,
    apply_step_terminal,
    canonicalize_document,
    compute_pipeline_digest,
    get_pipeline_run,
    load_from_source,
    register_builtin_extensions as pipeline_definition_register,
    trigger_run,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition.parser import (
    parse_document,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition.dag import (
    build_dag,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000010001"
ACTOR_UUID = "00000000-0000-4000-8000-000000010002"
COMMIT_SHA = "abc1234567890def1234567890abc1234567890d"


VALID_YAML_PIPELINE = b"""
schema_version: 1
name: ci-pipeline
stages:
  - id: build
    steps:
      - id: build-image
        kind: build
        inputs:
          image: registry.example.com/app
          commands:
            - make build
  - id: test
    needs: [build]
    steps:
      - id: run-tests
        kind: test
        inputs:
          catalog_entry_id: 00000000-0000-4000-8000-aaaaaaaaaaaa
          runner: testbase
"""


VALID_JSON_PIPELINE = b"""{
  "schema_version": 1,
  "name": "json-pipeline",
  "stages": [
    {
      "id": "lint",
      "steps": [
        {"id": "ruff", "kind": "script", "inputs": {"commands": ["ruff check ."]}}
      ]
    }
  ]
}"""


def _prepare_runtime() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    pipeline_definition_register()
    return


# -------------------------------------
# parser
# -------------------------------------

def test_parse_document_handles_yaml_and_json_round_trip():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: parse_document accepts both YAML and JSON
    bytes; the resulting AST has the expected stages and
    steps.**
    """
    _prepare_runtime()
    yaml_doc = parse_document(
        document_bytes=VALID_YAML_PIPELINE, filename="pipeline.yaml",
    )
    testbase.assert_equal(yaml_doc.name, "ci-pipeline")
    testbase.assert_equal(len(yaml_doc.stages), 2)
    testbase.assert_equal(yaml_doc.stages[0].stage_id, "build")
    testbase.assert_equal(yaml_doc.stages[1].needs, ("build",))

    json_doc = parse_document(
        document_bytes=VALID_JSON_PIPELINE, filename="pipeline.json",
    )
    testbase.assert_equal(json_doc.name, "json-pipeline")
    testbase.assert_equal(json_doc.stages[0].steps[0].kind_name, "script")
    return


def test_parse_document_rejects_empty_bytes():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: empty document bytes raise
    PipelineDocumentInvalidError.**
    """
    _prepare_runtime()
    raised = False
    try:
        parse_document(document_bytes=b"", filename="pipeline.yaml")
    except PipelineDocumentInvalidError as xcpt:
        raised = True
        testbase.assert_equal("empty" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


def test_parse_document_aggregates_multiple_issues():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: parse_document collects every problem before
    raising a single error.**
    """
    _prepare_runtime()
    bad = b"""
schema_version: 1
stages:
  - id: ""
    steps: []
  - id: a
    when: never
    steps:
      - id: ""
        kind: ""
"""
    raised = False
    try:
        parse_document(document_bytes=bad, filename="pipeline.yaml")
    except PipelineDocumentInvalidError as xcpt:
        raised = True
        message = str(xcpt)
        # Expect at least 4 issues surfaced — name missing,
        # stage[0].id empty, stages[0].steps empty, when invalid,
        # step[0].id empty + kind empty.
        testbase.assert_equal(message.count("\n") >= 4, True)
    testbase.assert_equal(raised, True)
    return


def test_parse_document_rejects_yaml_python_tags():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: yaml.safe_load rejects ``!!python/...`` tags so
    document loading is sandbox-safe.**
    """
    _prepare_runtime()
    malicious = b"name: !!python/object/apply:os.system ['echo hi']\nstages: []\n"
    raised = False
    try:
        parse_document(
            document_bytes=malicious, filename="pipeline.yaml",
        )
    except PipelineDocumentInvalidError:
        raised = True
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# dag
# -------------------------------------

def test_build_dag_topological_order_is_stable():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: build_dag returns a topological order honoring
    document index for ties.**
    """
    _prepare_runtime()
    document = parse_document(
        document_bytes=VALID_YAML_PIPELINE, filename="pipeline.yaml",
    )
    dag = build_dag(document=document)
    testbase.assert_equal(dag.topological_order, ("build", "test"))
    return


def test_build_dag_detects_cycle():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: a stage cycle raises PipelineDagCycleError.**
    """
    _prepare_runtime()
    cyclic = b"""
schema_version: 1
name: cyclic
stages:
  - id: a
    needs: [b]
    steps:
      - id: s
        kind: script
        inputs:
          commands: [echo]
  - id: b
    needs: [a]
    steps:
      - id: s
        kind: script
        inputs:
          commands: [echo]
"""
    document = parse_document(
        document_bytes=cyclic, filename="pipeline.yaml",
    )
    raised = False
    try:
        build_dag(document=document)
    except PipelineDagCycleError as xcpt:
        raised = True
        testbase.assert_equal("cycle" in str(xcpt).lower(), True)
    testbase.assert_equal(raised, True)
    return


def test_build_dag_detects_unknown_dependency():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: ``needs:`` referencing an unknown stage raises
    PipelineDocumentInvalidError naming the unknown target.**
    """
    _prepare_runtime()
    bad_needs = b"""
schema_version: 1
name: bad-needs
stages:
  - id: a
    needs: [missing-stage]
    steps:
      - id: s
        kind: script
        inputs:
          commands: [echo]
"""
    document = parse_document(
        document_bytes=bad_needs, filename="pipeline.yaml",
    )
    raised = False
    try:
        build_dag(document=document)
    except PipelineDocumentInvalidError as xcpt:
        raised = True
        testbase.assert_equal("missing-stage" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# canonicalization
# -------------------------------------

def test_canonical_digest_is_stable_across_yaml_and_json():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: a YAML and an equivalent JSON document
    canonicalize to the same digest.**
    """
    _prepare_runtime()
    yaml_doc = parse_document(
        document_bytes=b"""
schema_version: 1
name: same
stages:
  - id: a
    steps:
      - id: s
        kind: script
        inputs:
          commands: [echo]
""",
        filename="pipeline.yaml",
    )
    json_doc = parse_document(
        document_bytes=b"""{
  "schema_version": 1,
  "name": "same",
  "stages": [
    {"id": "a", "steps": [{"id": "s", "kind": "script", "inputs": {"commands": ["echo"]}}]}
  ]
}""",
        filename="pipeline.json",
    )
    testbase.assert_equal(
        compute_pipeline_digest(document=yaml_doc),
        compute_pipeline_digest(document=json_doc),
    )
    canon = canonicalize_document(document=yaml_doc)
    testbase.assert_equal(len(canon) > 0, True)
    return


# -------------------------------------
# load_from_source
# -------------------------------------

def test_load_from_source_persists_cache_and_emits_defined():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: load_from_source caches the canonical document
    and emits entity.pipeline.defined.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received: List[EntityEvent] = []
    subscribe(
        topic=PipelineEventTopics.DEFINED,
        subscriber=lambda e: received.append(e),
    )
    document = load_from_source(
        db_session=session,
        project_id=PROJECT_UUID,
        commit_sha=COMMIT_SHA,
        filename="pipeline.yaml",
        document_bytes=VALID_YAML_PIPELINE,
    )
    testbase.assert_equal(document.name, "ci-pipeline")
    testbase.assert_equal(len(received), 1)
    return


def test_load_from_source_rejects_unknown_step_kind():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: a step referencing a kind with no registered
    factory raises PipelineStepKindUnknownError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    bad_kind = b"""
schema_version: 1
name: bad-kind
stages:
  - id: x
    steps:
      - id: y
        kind: unknown-kind
        inputs: {}
"""
    raised = False
    try:
        load_from_source(
            db_session=session,
            project_id=PROJECT_UUID,
            commit_sha=COMMIT_SHA,
            filename="pipeline.yaml",
            document_bytes=bad_kind,
        )
    except PipelineStepKindUnknownError as xcpt:
        raised = True
        testbase.assert_equal("unknown-kind" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# trigger_run
# -------------------------------------

def test_trigger_run_persists_run_stage_step_tree_and_emits():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: trigger_run persists a PipelineRun, every
    StageRun, and every StepRun in PENDING; emits
    entity.pipeline.run_started.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_started: List[EntityEvent] = []
    subscribe(
        topic=PipelineEventTopics.RUN_STARTED,
        subscriber=lambda e: received_started.append(e),
    )
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        commit_sha=COMMIT_SHA,
        ref="refs/heads/main",
        filename="pipeline.yaml",
        document_bytes=VALID_YAML_PIPELINE,
        aspects=TriggerAspects(
            trigger_cause=TriggerCause.WEBHOOK,
            actor_id=ACTOR_UUID,
        ),
    )
    testbase.assert_equal(view.state, PipelineRunState.RUNNING)
    testbase.assert_equal(view.trigger_cause, TriggerCause.WEBHOOK)
    testbase.assert_equal(len(view.stages), 2)
    testbase.assert_equal(view.stages[0].stage_id, "build")
    testbase.assert_equal(view.stages[1].needs, ("build",))
    testbase.assert_equal(len(view.stages[0].steps), 1)
    testbase.assert_equal(view.stages[0].steps[0].job_kind, "build")
    testbase.assert_equal(view.stages[1].steps[0].job_kind, "test")
    testbase.assert_equal(view.stages[0].steps[0].state, StepState.PENDING)
    testbase.assert_equal(len(received_started), 1)
    return


def test_trigger_run_rejects_invalid_step_inputs():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: a step whose inputs fail kind validation raises
    PipelineDocumentInvalidError naming the step.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    bad_inputs = b"""
schema_version: 1
name: bad-build
stages:
  - id: build
    steps:
      - id: bad-build-step
        kind: build
        inputs: {}
"""
    raised = False
    try:
        trigger_run(
            db_session=session,
            project_id=PROJECT_UUID,
            commit_sha=COMMIT_SHA,
            ref="refs/heads/main",
            filename="pipeline.yaml",
            document_bytes=bad_inputs,
        )
    except PipelineDocumentInvalidError as xcpt:
        raised = True
        testbase.assert_equal("bad-build-step" in str(xcpt), True)
    testbase.assert_equal(raised, True)
    return


# -------------------------------------
# apply_step_terminal cascade
# -------------------------------------

def test_apply_step_terminal_cascade_to_pipeline_completed():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: when every step terminates with COMPLETED, the
    stages and the pipeline transition to COMPLETED in turn.
    Step + stage + run completion topics fire.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    received_step: List[EntityEvent] = []
    received_stage: List[EntityEvent] = []
    received_run: List[EntityEvent] = []
    subscribe(
        topic=PipelineEventTopics.STEP_COMPLETED,
        subscriber=lambda e: received_step.append(e),
    )
    subscribe(
        topic=PipelineEventTopics.STAGE_COMPLETED,
        subscriber=lambda e: received_stage.append(e),
    )
    subscribe(
        topic=PipelineEventTopics.RUN_COMPLETED,
        subscriber=lambda e: received_run.append(e),
    )

    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        commit_sha=COMMIT_SHA,
        ref="refs/heads/main",
        filename="pipeline.yaml",
        document_bytes=VALID_YAML_PIPELINE,
    )
    for stage in view.stages:
        for step in stage.steps:
            apply_step_terminal(
                db_session=session,
                step_run_id=step.step_run_id,
                final_state=StepState.COMPLETED,
                layer5_run_id=new_uuid(),
                reason="ok",
            )

    refreshed = get_pipeline_run(
        db_session=session, run_id=view.run_id,
    )
    testbase.assert_equal(refreshed.state, PipelineRunState.COMPLETED)
    for stage in refreshed.stages:
        testbase.assert_equal(stage.state, StageState.COMPLETED)
        for step in stage.steps:
            testbase.assert_equal(step.state, StepState.COMPLETED)
    testbase.assert_equal(len(received_step), 2)
    testbase.assert_equal(len(received_stage), 2)
    testbase.assert_equal(len(received_run), 1)
    return


def test_apply_step_terminal_cascade_to_pipeline_failed():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: a single FAILED step propagates to its stage
    and to the pipeline run.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    view = trigger_run(
        db_session=session,
        project_id=PROJECT_UUID,
        commit_sha=COMMIT_SHA,
        ref="refs/heads/main",
        filename="pipeline.yaml",
        document_bytes=VALID_YAML_PIPELINE,
    )
    apply_step_terminal(
        db_session=session,
        step_run_id=view.stages[0].steps[0].step_run_id,
        final_state=StepState.FAILED,
        reason="exit-code-1",
    )
    apply_step_terminal(
        db_session=session,
        step_run_id=view.stages[1].steps[0].step_run_id,
        final_state=StepState.COMPLETED,
    )

    refreshed = get_pipeline_run(
        db_session=session, run_id=view.run_id,
    )
    testbase.assert_equal(refreshed.state, PipelineRunState.FAILED)
    testbase.assert_equal(refreshed.stages[0].state, StageState.FAILED)
    testbase.assert_equal(refreshed.stages[1].state, StageState.COMPLETED)
    return


def test_apply_step_terminal_unknown_step_raises():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: apply_step_terminal on an unknown step run id
    raises PipelineStepRunNotFoundError.**
    """
    from ccai.pychestrate.webservice.orchestration.pipelines.definition.errors import (
        PipelineStepRunNotFoundError,
    )

    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        apply_step_terminal(
            db_session=session,
            step_run_id=new_uuid(),
            final_state=StepState.COMPLETED,
        )
    except PipelineStepRunNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_get_pipeline_run_unknown_raises():
    """
    **Feature: 6-pipeline-definition (M1)**
    **Property: get_pipeline_run on an unknown id raises
    PipelineRunNotFoundError.**
    """
    _prepare_runtime()
    _engine, session = build_in_memory_session()
    raised = False
    try:
        get_pipeline_run(db_session=session, run_id=new_uuid())
    except PipelineRunNotFoundError:
        raised = True
    testbase.assert_equal(raised, True)
    return
