"""
.. module:: orchestration.rpa.factories.execution_mode_protocol
    :synopsis: ``rpa_execution_mode`` factory contract.

.. moduleauthor:: Code Craft AI LLC

An execution mode is *how* a job type runs on the pod client. The
driver validates the entrypoint an administrator publishes with a
version and describes the client-side contract (which keys the
envelope payload's ``entrypoint`` carries). The two in-tree drivers
are :class:`ProcessExecutionMode` (simple process jobs) and
:class:`TaskplusExecutionMode` (tasker-based jobs).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Mapping, Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


RPA_EXECUTION_MODE_PROTOCOL: str = "rpa_execution_mode"


class RpaExecutionModeProtocol(FactoryProtocolBase):
    """
        Contract for ``rpa_execution_mode`` extensions.
    """
    factory_protocol_name: str = RPA_EXECUTION_MODE_PROTOCOL
    protocol_schema_version: int = 1
    is_published: bool = True
    published_docs_url: str = "/docs/extensions/protocols/rpa_execution_mode.html"
    published_reference: str = (
        "ccai.pychestrate.webservice.orchestration.rpa.factories.process_execution_mode"
        ".ProcessExecutionMode"
    )

    @classmethod
    def execution_mode(cls) -> str:
        """
            Stable identifier matching ``RpaJobType.execution_mode``.
        """
        raise NotImplementedError("Subclasses must implement execution_mode")

    @classmethod
    def validate_entrypoint(
            cls,
            *,
            entrypoint: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        """
            Validate the entrypoint published with a version.

            :returns: ``(True, ())`` on success;
                      ``(False, ("reason1", ...))`` otherwise.
        """
        raise NotImplementedError("Subclasses must implement validate_entrypoint")

    @classmethod
    def describe(cls) -> str:
        """
            One-line human description shown in the UI.
        """
        raise NotImplementedError("Subclasses must implement describe")
