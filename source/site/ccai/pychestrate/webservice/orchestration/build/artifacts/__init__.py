"""
.. module:: orchestration.build.artifacts
    :synopsis: 6-build-artifacts — manifest synthesis + (M2) promotion ledger.

Public surface:

* :class:`BuildArtifactManifest`,
  :class:`BuildArtifactEntryIndex`,
  :class:`BuildArtifactPromotionLedger`,
  :class:`ChannelHead`, :class:`PromotionAction` —
  persistence rows + enum.
* :class:`ArtifactEntry`, :class:`ManifestView`,
  :class:`ChannelHeadView` — IO shapes.
* :func:`synthesize_manifest`, :func:`get_manifest`,
  :func:`list_entries`, :func:`promote_to_channel`,
  :func:`get_channel_head`.
* :class:`ArtifactTypeProtocol` factory contract +
  reference :class:`ContainerImageArtifactType`.
* :class:`BuildArtifactEventTopics`.
* Errors: :class:`BuildArtifactsError`,
  :class:`BuildArtifactManifestNotFoundError`,
  :class:`ArtifactTypeUnknownError`,
  :class:`ArtifactEntryInvalidError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.errors import (
    ArtifactEntryInvalidError,
    ArtifactTypeUnknownError,
    BuildArtifactManifestNotFoundError,
    BuildArtifactsError,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.events import (
    BuildArtifactEventTopics,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.factories.artifact_type_protocol import (
    ArtifactTypeProtocol,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.factories.container_image_artifact_type import (
    ContainerImageArtifactType,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.models import (
    BuildArtifactEntryIndex,
    BuildArtifactManifest,
    BuildArtifactPromotionLedger,
    ChannelHead,
    PromotionAction,
)
from ccai.pychestrate.webservice.orchestration.build.artifacts.service import (
    ArtifactEntry,
    ChannelHeadView,
    ManifestView,
    get_channel_head,
    get_manifest,
    list_entries,
    promote_to_channel,
    synthesize_manifest,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`ContainerImageArtifactType`
        reference.
    """
    register_factory_implementation(implementation=ContainerImageArtifactType)
    return
