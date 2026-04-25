"""
.. module:: orchestration.build.factories.makefile_runner_kind
    :synopsis: MakefileRunnerKind — reference Makefile-driven build runner.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from automojo.pychestrate.webservice.orchestration.build.factories.runner_protocol import (
    BuildRunnerKindProtocol,
)


MAKEFILE_RUNNER_KIND_NAME: str = "makefile"


class MakefileRunnerKind(BuildRunnerKindProtocol):
    """
        Reference Makefile runner.

        Required input:

        * ``targets`` — non-empty list of make-target strings.

        Optional input:

        * ``makefile_path`` — defaults to ``"Makefile"``.
        * ``parallelism`` — non-negative int (0 ⇒ default).
    """

    factory_protocol_name: str = "build_runner_kind"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def runner_kind(cls) -> str:
        rtnval = MAKEFILE_RUNNER_KIND_NAME
        return rtnval

    @classmethod
    def validate_inputs(
            cls,
            *,
            inputs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []
        targets = inputs.get("targets", None)
        if targets is None:
            issues.append("'targets' is required")
        elif not isinstance(targets, list):
            issues.append("'targets' must be a list of strings")
        else:
            if len(targets) == 0:
                issues.append("'targets' must contain at least one entry")
            for index, target in enumerate(targets):
                if not isinstance(target, str) or len(target) == 0:
                    issues.append(
                        "'targets[{}]' must be a non-empty string".format(
                            index,
                        )
                    )

        makefile_path = inputs.get("makefile_path", "Makefile")
        if not isinstance(makefile_path, str) or len(makefile_path) == 0:
            issues.append(
                "'makefile_path' must be a non-empty string when present",
            )

        parallelism = inputs.get("parallelism", 0)
        if not isinstance(parallelism, int) or parallelism < 0:
            issues.append("'parallelism' must be a non-negative integer")

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval
