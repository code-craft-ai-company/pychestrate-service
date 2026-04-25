"""
.. module:: orchestration.infra.drift.factories.checker_protocol
    :synopsis: ``drift_checker`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class DriftCheckerProtocol(FactoryProtocolBase):
    """
        Contract for ``drift_checker`` extensions. M1 ships
        only the Terraform reference; M2 widens to Pulumi +
        Ansible + custom checkers.
    """

    factory_protocol_name: str = "drift_checker"
    protocol_schema_version: int = 1

    @classmethod
    def checker_name(cls) -> str:
        """
            Stable identifier matching
            ``DriftSchedule.checker_name``.
        """
        raise NotImplementedError("Subclasses must implement checker_name")

    @classmethod
    def supported_environment_kinds(cls) -> Tuple[str, ...]:
        """
            Tuple of environment-kind names this checker can
            inspect. The service uses this to reject schedule
            assignments for incompatible env kinds.
        """
        raise NotImplementedError(
            "Subclasses must implement supported_environment_kinds",
        )
