"""
.. module:: clients.upgrades.factories.upgrade_artifact_source_protocol
    :synopsis: ``upgrade_artifact_source`` factory contract.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.clients.upgrades.dtos import (
    ArtifactDescriptor,
)
from automojo.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class UpgradeArtifactSourceProtocol(FactoryProtocolBase):
    """
        Contract for ``upgrade_artifact_source`` extensions.
        M1 ships :class:`ObjectStoreArtifactSource` as the
        in-tree reference. Each implementation declares a
        stable :meth:`source_name` used by callers to bind a
        rollout to a specific source.
    """

    factory_protocol_name: str = "upgrade_artifact_source"
    protocol_schema_version: int = 1

    @classmethod
    def source_name(cls) -> str:
        """
            Stable identifier callers store on the rollout
            row to select this source at offer-emission time.
        """
        raise NotImplementedError("Subclasses must implement source_name")

    @classmethod
    def describe(
            cls,
            *,
            artifact_ref: str
        ) -> ArtifactDescriptor:
        """
            Resolve the artifact reference into a descriptor
            carrying URI / sha256 / byte size / content type.
        """
        raise NotImplementedError("Subclasses must implement describe")
