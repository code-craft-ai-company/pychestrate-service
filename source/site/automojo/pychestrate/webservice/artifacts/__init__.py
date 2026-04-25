"""
.. module:: artifacts
    :synopsis: 5-artifact-store — content-addressed artifact retention.

Public surface:

* :class:`ArtifactStore` — register / get / list facade.
* :class:`ArtifactBlob`, :class:`RunArtifactReference`,
  :class:`ArtifactTypeMetadata`, :class:`ArtifactRetentionPlan`
  — persistence rows.
* :class:`ArtifactRegistration` — register-call IO shape.
* :func:`hash_blob_stream`, :func:`build_cas_key`.
* :class:`PromotionStrategyProtocol` +
  :class:`DefaultPromotionStrategy`.
* :func:`register_builtin_extensions` — seed the registry.
* Errors: :class:`ArtifactError`,
  :class:`ArtifactBlobNotFoundError`,
  :class:`ArtifactReferenceNotFoundError`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)
from automojo.pychestrate.webservice.artifacts.cas_layout import build_cas_key
from automojo.pychestrate.webservice.artifacts.errors import (
    ArtifactBlobNotFoundError,
    ArtifactError,
    ArtifactReferenceNotFoundError,
)
from automojo.pychestrate.webservice.artifacts.factories.default_promotion import (
    DefaultPromotionStrategy,
)
from automojo.pychestrate.webservice.artifacts.factories.promotion_strategy import (
    PromotionStrategyProtocol,
)
from automojo.pychestrate.webservice.artifacts.hashing import hash_blob_stream
from automojo.pychestrate.webservice.artifacts.models import (
    ArtifactBlob,
    ArtifactRetentionPlan,
    ArtifactTypeMetadata,
    RunArtifactReference,
)
from automojo.pychestrate.webservice.artifacts.store import (
    ArtifactRegistration,
    ArtifactStore,
)


def register_builtin_extensions() -> None:
    """
        Register :class:`DefaultPromotionStrategy` under the
        ``promotion_strategy`` factory protocol.
    """
    register_factory_implementation(implementation=DefaultPromotionStrategy)
    return
