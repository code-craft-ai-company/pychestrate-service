"""
.. module:: orchestration.infra.environment.factories.kind_protocol
    :synopsis: ``environment_kind`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class EnvironmentKindProtocol(FactoryProtocolBase):
    """
        Contract for ``environment_kind`` extensions. M1 ships
        only :class:`K8sClusterEnvironmentKind`; M2 widens to
        VMware / cloud / on-prem kinds via new factory
        implementations.
    """

    factory_protocol_name: str = "environment_kind"
    protocol_schema_version: int = 1

    @classmethod
    def kind_name(cls) -> str:
        """
            Stable identifier matching ``Environment.kind_name``.
        """
        raise NotImplementedError("Subclasses must implement kind_name")

    @classmethod
    def validate_attrs(
            cls,
            *,
            attrs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        """
            Validate the kind-specific attrs payload. Return
            ``(True, ())`` on success;
            ``(False, ("reason1", ...))`` otherwise.
        """
        raise NotImplementedError("Subclasses must implement validate_attrs")
