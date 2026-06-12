"""
.. module:: orchestration.build.artifacts.factories.artifact_type_protocol
    :synopsis: ``build_artifact_type`` factory contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class ArtifactTypeProtocol(FactoryProtocolBase):
    """
        Contract for ``build_artifact_type`` extensions. M1
        ships only :class:`ContainerImageArtifactType`; M2 adds
        SBOM, firmware-image, and python-package types.
    """

    factory_protocol_name: str = "build_artifact_type"
    protocol_schema_version: int = 1

    @classmethod
    def artifact_type_name(cls) -> str:
        """
            Stable identifier matching ``ArtifactEntry.artifact_type``.
        """
        raise NotImplementedError(
            "Subclasses must implement artifact_type_name",
        )

    @classmethod
    def validate_payload(
            cls,
            *,
            payload: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        """
            Validate the artifact-specific payload. Return
            ``(True, ())`` on success;
            ``(False, ("reason1", ...))`` on rejection.
        """
        raise NotImplementedError("Subclasses must implement validate_payload")
