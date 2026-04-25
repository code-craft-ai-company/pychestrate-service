"""
.. module:: orchestration.build.artifacts.factories.container_image_artifact_type
    :synopsis: ContainerImageArtifactType — reference container-image artifact.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, List, Mapping, Tuple

from automojo.pychestrate.webservice.orchestration.build.artifacts.factories.artifact_type_protocol import (
    ArtifactTypeProtocol,
)


CONTAINER_IMAGE_ARTIFACT_TYPE_NAME: str = "container-image"


class ContainerImageArtifactType(ArtifactTypeProtocol):
    """
        Reference container-image type.

        Required payload fields:

        * ``registry`` — non-empty string.
        * ``repository`` — non-empty string.
        * ``digest`` — sha256 hex with the ``sha256:`` prefix.

        Optional:

        * ``tag`` — string.
    """

    factory_protocol_name: str = "build_artifact_type"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def artifact_type_name(cls) -> str:
        rtnval = CONTAINER_IMAGE_ARTIFACT_TYPE_NAME
        return rtnval

    @classmethod
    def validate_payload(
            cls,
            *,
            payload: Mapping[str, Any]
        ) -> Tuple[bool, Tuple[str, ...]]:
        issues: List[str] = []

        for field_name in ("registry", "repository", "digest"):
            value = payload.get(field_name, None)
            if value is None:
                issues.append("'{}' is required".format(field_name))
                continue
            if not isinstance(value, str) or len(value) == 0:
                issues.append(
                    "'{}' must be a non-empty string".format(field_name),
                )

        digest = payload.get("digest", "")
        if isinstance(digest, str) and len(digest) > 0:
            if not digest.startswith("sha256:"):
                issues.append("'digest' must start with 'sha256:'")
            else:
                hex_part = digest[len("sha256:"):]
                if len(hex_part) != 64:
                    issues.append(
                        "'digest' sha256 must be 64 hex chars (got {})".format(
                            len(hex_part),
                        )
                    )

        tag = payload.get("tag", None)
        if tag is not None and not isinstance(tag, str):
            issues.append("'tag' must be a string when present")

        if len(issues) > 0:
            rtnval: Tuple[bool, Tuple[str, ...]] = (False, tuple(issues))
            return rtnval
        rtnval = (True, ())
        return rtnval
