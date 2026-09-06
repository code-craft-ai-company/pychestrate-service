"""
.. module:: orchestration.pipelines.definition.factories.rpa_step_kind
    :synopsis: RpaStepKind — ``kind: rpa`` pipeline step (6-rpa-orchestration).

.. moduleauthor:: Code Craft AI LLC

A pipeline stage can trigger an RPA specification with a work packet::

    - kind: rpa
      inputs:
        spec_id: 3f2a...            # RPA specification UUID
        work_packet: {customer_id: 42}
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


RPA_STEP_KIND_NAME: str = "rpa"


class RpaStepKind(PipelineStepKindProtocol):
    """
        Reference RPA step. Requires ``spec_id`` (string) plus an
        optional ``work_packet`` (object).
    """

    factory_protocol_name: str = "pipeline_step_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1300

    @classmethod
    def kind_name(cls) -> str:
        rtnval = RPA_STEP_KIND_NAME
        return rtnval

    @classmethod
    def validate_inputs(
            cls,
            *,
            inputs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []
        spec_id = inputs.get("spec_id", None)
        if spec_id is None:
            issues.append("'spec_id' is required")
        elif not isinstance(spec_id, str) or len(spec_id) == 0:
            issues.append("'spec_id' must be a non-empty string")
        work_packet = inputs.get("work_packet", {})
        if work_packet is not None and not isinstance(work_packet, dict):
            issues.append("'work_packet' must be an object when present")
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
            "spec_id": str(inputs.get("spec_id", "")),
            "work_packet": dict(inputs.get("work_packet", {}) or {}),
        }
        annotations = {
            "stage_id": stage_id,
            "step_id": step_id,
            "kind_name": RPA_STEP_KIND_NAME,
        }
        rtnval = [
            JobProduction(
                job_kind="rpa",
                envelope_inputs=envelope_inputs,
                annotations=annotations,
            ),
        ]
        return rtnval
