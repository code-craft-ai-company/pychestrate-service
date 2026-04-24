"""
.. module:: agents.factories.artifact_source
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ``upgrade_artifact_source`` factory protocol base.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import ClassVar

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class ArtifactHandle:
    """
        Opaque reference to an artifact blob.

        :param uri: Where the artifact lives.
        :param sha256: Content hash as a lower-case hex digest.
        :param size_bytes: Artifact size.
    """
    uri: str
    sha256: str
    size_bytes: int


class UpgradeArtifactSourceProtocol(FactoryProtocolBase):
    """
        Contract for artifact-source resolvers.
    """

    factory_protocol_name: ClassVar[str] = "upgrade_artifact_source"
    protocol_schema_version: ClassVar[int] = 1
    source_name: ClassVar[str] = ""

    @classmethod
    def resolve(cls, *, artifact_ref: str) -> ArtifactHandle:
        raise NotImplementedError("Subclasses must implement resolve()")
