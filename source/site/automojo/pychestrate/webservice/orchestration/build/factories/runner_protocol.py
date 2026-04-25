"""
.. module:: orchestration.build.factories.runner_protocol
    :synopsis: ``build_runner_kind`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class BuildRunnerKindProtocol(FactoryProtocolBase):
    """
        Contract for ``build_runner_kind`` extensions. M1 covers
        Makefile-driven builds; M2 widens to Poetry, Docker, and
        out-of-tree drivers.
    """

    factory_protocol_name: str = "build_runner_kind"
    protocol_schema_version: int = 1

    @classmethod
    def runner_kind(cls) -> str:
        """
            Stable identifier matching ``inputs.runner_kind`` on
            a :class:`BuildRunInputs`.
        """
        raise NotImplementedError("Subclasses must implement runner_kind")

    @classmethod
    def validate_inputs(
            cls,
            *,
            inputs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        """
            Return ``(True, ())`` on success;
            ``(False, ("reason1", ...))`` otherwise.
        """
        raise NotImplementedError("Subclasses must implement validate_inputs")
