"""
.. module:: orchestration.rpa.factories.taskplus_execution_mode
    :synopsis: TaskplusExecutionMode — tasker-based jobs.

.. moduleauthor:: Code Craft AI LLC

A tasker-based job runs a ``codecraftai-taskplus`` workflow. The
entrypoint declares either a workflow file inside the resolved
source or a single ``module@Class`` tasking the client wraps in a
one-task workflow::

    {"workflow": "workflows/invoice.yaml"}
    {"tasking": "jobs.invoice@InvoiceImport"}

The client renders the work packet into the workflow's ``parameters``
and the version's environment into its ``environment`` and runs the
``taskplus`` console script as a subprocess; the engine is never
imported into the agent process.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from typing import Any, List, Mapping, Tuple

from ccai.pychestrate.webservice.orchestration.rpa.factories.execution_mode_protocol import (
    RpaExecutionModeProtocol,
)


TASKPLUS_EXECUTION_MODE_NAME: str = "tasker"

#: ``module.path@ClassName`` identity used by taskplus and the tasker
#: protocol for a task type.
TASKING_IDENTITY_PATTERN = re.compile(r"^[A-Za-z_][\w.]*@[A-Za-z_]\w*$")


class TaskplusExecutionMode(RpaExecutionModeProtocol):
    """
        Reference tasker-based driver (taskplus workflows).
    """

    factory_protocol_name: str = "rpa_execution_mode"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1100

    @classmethod
    def execution_mode(cls) -> str:
        rtnval = TASKPLUS_EXECUTION_MODE_NAME
        return rtnval

    @classmethod
    def describe(cls) -> str:
        rtnval = (
            "Tasker-based job: a taskplus workflow (module@Class tasks) runs"
            " with the work packet as its parameters."
        )
        return rtnval

    @classmethod
    def validate_entrypoint(
            cls,
            *,
            entrypoint: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []
        workflow = entrypoint.get("workflow", None)
        tasking = entrypoint.get("tasking", None)

        if workflow is None and tasking is None:
            issues.append(
                "tasker jobs require 'entrypoint.workflow' (a taskplus YAML path)"
                " or 'entrypoint.tasking' (a module@Class identity)"
            )
        if workflow is not None and tasking is not None:
            issues.append("'entrypoint.workflow' and 'entrypoint.tasking' are mutually exclusive")
        if workflow is not None:
            if not isinstance(workflow, str) or len(workflow) == 0:
                issues.append("'entrypoint.workflow' must be a non-empty relative path")
            elif workflow.startswith("/") or ".." in workflow.split("/"):
                issues.append("'entrypoint.workflow' must be a relative path inside the source")
        if tasking is not None:
            if not isinstance(tasking, str) or TASKING_IDENTITY_PATTERN.match(tasking) is None:
                issues.append("'entrypoint.tasking' must look like 'package.module@ClassName'")

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval
