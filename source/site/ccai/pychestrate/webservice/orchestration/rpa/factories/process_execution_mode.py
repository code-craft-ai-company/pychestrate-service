"""
.. module:: orchestration.rpa.factories.process_execution_mode
    :synopsis: ProcessExecutionMode — simple process jobs.

.. moduleauthor:: Code Craft AI LLC

A simple process job receives the work packet and performs the work
in a subprocess the client launches. The entrypoint declares::

    {
      "command": ["python", "-m", "jobs.invoice_import"],
      "packet_delivery": "file" | "stdin" | "env",
      "working_dir": "."          (optional, relative to the source)
    }

The client writes ``work_packet.json`` in the run directory, exports
``PYC_WORK_PACKET`` (path), ``PYC_RUN_ID``, ``PYC_JOB_TYPE``,
``PYC_JOB_VERSION``, ``PYC_RESULTS_DIR``, delivers the packet per
``packet_delivery``, and maps exit code ``0`` to ``succeeded``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from ccai.pychestrate.webservice.orchestration.rpa.factories.execution_mode_protocol import (
    RpaExecutionModeProtocol,
)


PROCESS_EXECUTION_MODE_NAME: str = "process"

PACKET_DELIVERY_FILE: str = "file"
PACKET_DELIVERY_STDIN: str = "stdin"
PACKET_DELIVERY_ENV: str = "env"
SUPPORTED_PACKET_DELIVERIES: Tuple[str, ...] = (
    PACKET_DELIVERY_FILE,
    PACKET_DELIVERY_STDIN,
    PACKET_DELIVERY_ENV,
)


class ProcessExecutionMode(RpaExecutionModeProtocol):
    """
        Reference simple-process driver.
    """

    factory_protocol_name: str = "rpa_execution_mode"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def execution_mode(cls) -> str:
        rtnval = PROCESS_EXECUTION_MODE_NAME
        return rtnval

    @classmethod
    def describe(cls) -> str:
        rtnval = (
            "Simple process job: the work packet is handed to a command;"
            " the exit code and the files it writes are the result."
        )
        return rtnval

    @classmethod
    def validate_entrypoint(
            cls,
            *,
            entrypoint: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []
        command = entrypoint.get("command", None)
        if command is None:
            issues.append("'entrypoint.command' is required for process jobs")
        elif not isinstance(command, list) or len(command) == 0:
            issues.append("'entrypoint.command' must be a non-empty list of strings (argv)")
        else:
            for index, part in enumerate(command):
                if not isinstance(part, str) or len(part) == 0:
                    issues.append(
                        "'entrypoint.command[{}]' must be a non-empty string".format(index)
                    )

        delivery = entrypoint.get("packet_delivery", PACKET_DELIVERY_FILE)
        if delivery not in SUPPORTED_PACKET_DELIVERIES:
            issues.append(
                "'entrypoint.packet_delivery' must be one of {}".format(
                    ", ".join(SUPPORTED_PACKET_DELIVERIES),
                )
            )

        working_dir = entrypoint.get("working_dir", ".")
        if not isinstance(working_dir, str) or len(working_dir) == 0:
            issues.append("'entrypoint.working_dir' must be a non-empty string when present")

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval
