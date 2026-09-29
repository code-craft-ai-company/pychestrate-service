"""
.. module:: orchestration.infra.runs.factories.driver_protocol
    :synopsis: ``infra_tool_driver`` factory contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class InfraToolDriverProtocol(FactoryProtocolBase):
    """
        Contract for ``infra_tool_driver`` extensions. M1 ships
        the Terraform reference; M2 widens to Pulumi + Ansible
        + custom drivers.
    """

    factory_protocol_name: str = "infra_tool_driver"
    protocol_schema_version: int = 1

    is_published: bool = True
    published_docs_url: str = "/docs/extensions/protocols/infra_tool_driver.html"
    published_reference: str = (
        "ccai.pychestrate.webservice.orchestration.infra.runs.factories.terraform_driver"
        ".TerraformInfraDriver"
    )

    @classmethod
    def driver_name(cls) -> str:
        """
            Stable identifier matching ``InfraRunInputs.driver_name``.
        """
        raise NotImplementedError("Subclasses must implement driver_name")

    @classmethod
    def supported_actions(cls) -> Tuple[str, ...]:
        """
            Tuple of action names (``plan`` / ``apply`` /
            ``destroy``) the driver supports.
        """
        raise NotImplementedError("Subclasses must implement supported_actions")

    @classmethod
    def validate_inputs(
            cls,
            *,
            action: str,
            inputs: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        """
            Validate the driver-specific inputs payload for the
            requested action. Return ``(True, ())`` on success;
            ``(False, ("reason1", ...))`` otherwise.
        """
        raise NotImplementedError("Subclasses must implement validate_inputs")
