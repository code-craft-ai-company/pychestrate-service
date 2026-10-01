"""
.. module:: test_p32zzzzzzzzz_validate_checks_step_inputs_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Validating a pipeline checks its steps' inputs, not just its graph (ORC-13).

.. moduleauthor:: Code Craft AI LLC

Validate said "valid" for a pipeline whose build step had no image and whose script step had no commands:
only the stage graph was checked, and the inputs were refused later, at run time, in the middle of writing the run. The
inputs now go through each step kind's own validation when the pipeline is validated, one line per problem naming the
step; and a run whose inputs are invalid is refused before anything is written.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus
from ccai.pychestrate.webservice.orchestration.pipelines.definition import (
    PipelineDocumentInvalidError,
    register_builtin_extensions as pipeline_definition_register,
    trigger_run,
)
from ccai.pychestrate.webservice.orchestration.pipelines.definition import service as definition_service
from ccai.pychestrate.webservice.orchestration.pipelines.definition.models import (
    PipelineRun,
    PipelineStageRun,
    PipelineStepRun,
)

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


PROJECT_UUID = "00000000-0000-4000-8000-0000000d0001"

VALID = b"""
schema_version: 1
name: ci
stages:
  - id: build
    steps:
      - id: build-image
        kind: build
        inputs:
          image: registry.example.com/app
          commands:
            - make build
"""

NO_IMAGE_NO_COMMANDS = b"""
schema_version: 1
name: ci
stages:
  - id: build
    steps:
      - id: build-image
        kind: build
        inputs:
          commands:
            - make build
  - id: package
    needs: [build]
    steps:
      - id: pack
        kind: script
        inputs:
          commands: []
"""


def _prepare() -> None:
    reset_registry_for_testing()
    reset_event_bus()
    pipeline_definition_register()
    return


def test_validate_flags_a_build_with_no_image_and_a_script_with_no_commands_by_step():
    """
    **Feature: validate checks inputs (ORC-13)**
    **Property: a pipeline whose build step has no image and whose script step has no commands is not valid;
    the issues name each step and its kind and say what is wrong; the same document with good inputs is valid; the
    stage count and order are still reported.**
    """
    _prepare()
    bad = definition_service.validate_document(document_bytes=NO_IMAGE_NO_COMMANDS, filename="pipeline.yaml")
    good = definition_service.validate_document(document_bytes=VALID, filename="pipeline.yaml")

    testbase.assert_equal(
        (bad.valid, list(bad.issues), bad.stage_count, list(bad.topological_order), good.valid, list(good.issues)),
        (
            False,
            ["Step 'build-image' (build): 'image' is required", "Step 'pack' (script): 'commands' must contain at least one entry"],
            2, ["build", "package"], True, [],
        ),
    )
    return


def test_a_run_with_invalid_inputs_is_refused_and_leaves_nothing_behind():
    """
    **Feature: validate checks inputs (ORC-13)**
    **Property: triggering a run whose step inputs are invalid raises the document error naming the step and
    has written no run, stage or step row (the inputs used to be checked in the middle of writing them, so the
    rows existed, uncommitted, when the refusal came).**
    """
    _prepare()
    _engine, session = build_in_memory_session()
    refused = ""
    try:
        trigger_run(
            db_session=session, project_id=PROJECT_UUID, commit_sha="a" * 40, ref="main", filename="pipeline.yaml",
            document_bytes=NO_IMAGE_NO_COMMANDS,
        )
    except PipelineDocumentInvalidError as xcpt:
        refused = str(xcpt)
    # Counted before any rollback: the rows would be visible here if they had been written and
    # the refusal came afterwards.

    testbase.assert_equal(
        ("Step 'build-image' inputs failed validation" in refused, session.query(PipelineRun).count(), session.query(PipelineStageRun).count(), session.query(PipelineStepRun).count()),
        (True, 0, 0, 0),
    )
    return
