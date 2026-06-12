"""
.. module:: orchestration.pipelines.definition.factories.test_step_kind
    :synopsis: TestStepKind — ``kind: test`` reference impl.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from ccai.pychestrate.webservice.orchestration.pipelines.definition.factories.step_kind_protocol import (
    JobProduction,
    PipelineStepKindProtocol,
)


TEST_STEP_KIND_NAME: str = "test"


class TestStepKind(PipelineStepKindProtocol):
    """
        Reference test step. M1 expects a ``catalog_entry_id``
        (string) plus optional ``runner`` (string, defaults to
        ``"testbase"``) and optional ``timeout_seconds`` (int).
    """

    factory_protocol_name: str = "pipeline_step_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def kind_name(cls) -> str:
        rtnval = TEST_STEP_KIND_NAME
        return rtnval

    @classmethod
    def validate_inputs(
            cls,
            *,
            inputs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []
        catalog_entry = inputs.get("catalog_entry_id", None)
        if catalog_entry is None:
            issues.append("'catalog_entry_id' is required")
        elif not isinstance(catalog_entry, str) or len(catalog_entry) == 0:
            issues.append("'catalog_entry_id' must be a non-empty string")

        runner = inputs.get("runner", "testbase")
        if not isinstance(runner, str) or len(runner) == 0:
            issues.append("'runner' must be a non-empty string when present")

        timeout = inputs.get("timeout_seconds", 0)
        if not isinstance(timeout, int) or timeout < 0:
            issues.append(
                "'timeout_seconds' must be a non-negative integer",
            )

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval

    @classmethod
    def produce_jobs(
            cls,
            *,
            project_id: str,
            run_id: str,
            stage_id: str,
            step_id: str,
            inputs: Mapping[str, Any]
        ) -> List[JobProduction]:
        envelope_inputs = {
            "catalog_entry_id": inputs.get("catalog_entry_id", ""),
            "runner": inputs.get("runner", "testbase"),
            "timeout_seconds": inputs.get("timeout_seconds", 0),
        }
        annotations = {
            "stage_id": stage_id,
            "step_id": step_id,
            "kind_name": TEST_STEP_KIND_NAME,
        }
        rtnval = [
            JobProduction(
                job_kind="test",
                envelope_inputs=envelope_inputs,
                annotations=annotations,
            ),
        ]
        return rtnval
