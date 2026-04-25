"""
.. module:: orchestration.infra.runs.factories.terraform_driver
    :synopsis: TerraformInfraDriver — reference Terraform infra driver.

Required inputs:

* ``working_directory`` — non-empty string path on the runner.

Optional inputs:

* ``var_file`` — path to a tfvars file.
* ``backend_config`` — mapping of backend keys → string values.
* ``parallelism`` — non-negative integer.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from automojo.pychestrate.webservice.orchestration.infra.runs.factories.driver_protocol import (
    InfraToolDriverProtocol,
)


TERRAFORM_DRIVER_NAME: str = "terraform"
TERRAFORM_SUPPORTED_ACTIONS: Tuple[str, ...] = ("plan", "apply", "destroy")


class TerraformInfraDriver(InfraToolDriverProtocol):
    """
        Reference Terraform driver.
    """

    factory_protocol_name: str = "infra_tool_driver"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def driver_name(cls) -> str:
        rtnval = TERRAFORM_DRIVER_NAME
        return rtnval

    @classmethod
    def supported_actions(cls) -> Tuple[str, ...]:
        rtnval = TERRAFORM_SUPPORTED_ACTIONS
        return rtnval

    @classmethod
    def validate_inputs(
            cls,
            *,
            action: str,
            inputs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []

        if action not in TERRAFORM_SUPPORTED_ACTIONS:
            issues.append(
                "action '{}' not supported by terraform driver".format(action),
            )

        working_directory = inputs.get("working_directory", None)
        if working_directory is None:
            issues.append("'working_directory' is required")
        elif not isinstance(working_directory, str) or len(working_directory) == 0:
            issues.append("'working_directory' must be a non-empty string")

        var_file = inputs.get("var_file", None)
        if var_file is not None:
            if not isinstance(var_file, str) or len(var_file) == 0:
                issues.append(
                    "'var_file' must be a non-empty string when present",
                )

        backend_config = inputs.get("backend_config", {})
        if not isinstance(backend_config, dict):
            issues.append("'backend_config' must be a mapping when present")
        else:
            for key, value in backend_config.items():
                if not isinstance(key, str) or len(key) == 0:
                    issues.append("'backend_config' keys must be non-empty strings")
                    break
                if not isinstance(value, str):
                    issues.append("'backend_config' values must be strings")
                    break

        parallelism = inputs.get("parallelism", 0)
        if not isinstance(parallelism, int) or parallelism < 0:
            issues.append("'parallelism' must be a non-negative integer")

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval
