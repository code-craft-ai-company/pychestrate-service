"""
.. module:: orchestration.pipelines.definition.factories.build_step_kind
    :synopsis: BuildStepKind — ``kind: build`` reference impl.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from automojo.pychestrate.webservice.orchestration.pipelines.definition.factories.step_kind_protocol import (
    JobProduction,
    PipelineStepKindProtocol,
)


BUILD_STEP_KIND_NAME: str = "build"


class BuildStepKind(PipelineStepKindProtocol):
    """
        Reference build step. M1 expects an ``image`` (string)
        plus optional ``commands`` (list of strings).
    """

    factory_protocol_name: str = "pipeline_step_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def kind_name(cls) -> str:
        rtnval = BUILD_STEP_KIND_NAME
        return rtnval

    @classmethod
    def validate_inputs(
            cls,
            *,
            inputs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []
        image = inputs.get("image", None)
        if image is None:
            issues.append("'image' is required")
        elif not isinstance(image, str) or len(image) == 0:
            issues.append("'image' must be a non-empty string")

        commands = inputs.get("commands", [])
        if not isinstance(commands, list):
            issues.append("'commands' must be a list of strings when present")
        else:
            for index, command in enumerate(commands):
                if not isinstance(command, str):
                    issues.append(
                        "'commands[{}]' must be a string".format(index),
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
            "image": inputs.get("image", ""),
            "commands": list(inputs.get("commands", []) or []),
        }
        annotations = {
            "stage_id": stage_id,
            "step_id": step_id,
            "kind_name": BUILD_STEP_KIND_NAME,
        }
        rtnval = [
            JobProduction(
                job_kind="build",
                envelope_inputs=envelope_inputs,
                annotations=annotations,
            ),
        ]
        return rtnval
