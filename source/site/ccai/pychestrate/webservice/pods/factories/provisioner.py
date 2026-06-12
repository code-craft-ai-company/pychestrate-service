"""
.. module:: pods.factories.provisioner
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``pod_provisioner`` factory protocol base.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Any, ClassVar, Mapping

from ccai.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class ProvisionOutcome:
    """
        Result of a provisioner invocation.

        :param provisioned: True when the target pod backing is ready.
        :param detail: Free-text outcome detail.
    """
    provisioned: bool
    detail: str


class PodProvisionerProtocol(FactoryProtocolBase):
    """
        Contract implemented by dynamic-pod provisioners.
    """

    factory_protocol_name: ClassVar[str] = "pod_provisioner"
    protocol_schema_version: ClassVar[int] = 1
    provisioner_name: ClassVar[str] = ""
    required_capabilities: ClassVar[frozenset] = frozenset()

    @classmethod
    def provision(
            cls,
            *,
            rendered_spec: Mapping[str, Any]
        ) -> ProvisionOutcome:
        """
            Bring a backing for the rendered pod spec online.

            :param rendered_spec: Fully-rendered pod spec.

            :returns: The outcome.
        """
        raise NotImplementedError("Subclasses must implement provision()")
