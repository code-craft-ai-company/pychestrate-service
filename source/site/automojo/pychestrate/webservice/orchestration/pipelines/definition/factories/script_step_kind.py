"""
.. module:: orchestration.pipelines.definition.factories.script_step_kind
    :synopsis: ScriptStepKind — ``kind: script`` reference impl.
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


SCRIPT_STEP_KIND_NAME: str = "script"


class ScriptStepKind(PipelineStepKindProtocol):
    """
        Reference script step. M1 expects ``commands`` (list of
        strings) plus optional ``shell`` (string, defaults to
        ``"bash"``).
    """

    factory_protocol_name: str = "pipeline_step_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def kind_name(cls) -> str:
        rtnval = SCRIPT_STEP_KIND_NAME
        return rtnval

    @classmethod
    def validate_inputs(
            cls,
            *,
            inputs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []
        commands = inputs.get("commands", None)
        if commands is None:
            issues.append("'commands' is required")
        elif not isinstance(commands, list):
            issues.append("'commands' must be a list of strings")
        else:
            if len(commands) == 0:
                issues.append("'commands' must contain at least one entry")
            for index, command in enumerate(commands):
                if not isinstance(command, str) or len(command) == 0:
                    issues.append(
                        "'commands[{}]' must be a non-empty string".format(
                            index,
                        )
                    )

        shell = inputs.get("shell", "bash")
        if not isinstance(shell, str) or len(shell) == 0:
            issues.append("'shell' must be a non-empty string when present")

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
            "commands": list(inputs.get("commands", []) or []),
            "shell": inputs.get("shell", "bash"),
        }
        annotations = {
            "stage_id": stage_id,
            "step_id": step_id,
            "kind_name": SCRIPT_STEP_KIND_NAME,
        }
        rtnval = [
            JobProduction(
                job_kind="script",
                envelope_inputs=envelope_inputs,
                annotations=annotations,
            ),
        ]
        return rtnval
