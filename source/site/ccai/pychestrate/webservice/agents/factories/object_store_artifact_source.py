"""
.. module:: agents.factories.object_store_artifact_source
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference ObjectStoreArtifactSource for 3-agent-upgrade-channel M1.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib

from typing import ClassVar

from ccai.pychestrate.webservice.agents.factories.artifact_source import (
    ArtifactHandle,
    UpgradeArtifactSourceProtocol,
)


class ObjectStoreArtifactSource(UpgradeArtifactSourceProtocol):
    """
        Reference implementation: interprets ``artifact_ref`` as an
        ``s3://`` or ``objstore://`` URI and returns a deterministic
        :class:`ArtifactHandle`. Real blob fetch wiring lands once
        ``0-object-store`` is fully landed.
    """

    factory_protocol_name: ClassVar[str] = "upgrade_artifact_source"
    source_name: ClassVar[str] = "object_store"
    PRECEDENCE: ClassVar[int] = 100

    @classmethod
    def resolve(cls, *, artifact_ref: str) -> ArtifactHandle:
        digest = hashlib.sha256((artifact_ref or "").encode("utf-8")).hexdigest()
        rtnval = ArtifactHandle(
            uri=artifact_ref if artifact_ref is not None else "",
            sha256=digest,
            size_bytes=0,
        )
        return rtnval
