"""
.. module:: clients.upgrades
    :synopsis: 3-agent-upgrade-channel — agent rollout orchestrator.

Public surface (M1):

* :class:`AgentRollout`, :class:`AgentRolloutStage`,
  :class:`AgentUpgradeOffer`, :class:`AgentPodPin` —
  persistence rows.
* :class:`RolloutState`, :class:`StageState`,
  :class:`OfferOutcome` — enums.
* :class:`FleetSnapshot`,
  :class:`OfferOutcomeReport`,
  :class:`ArtifactDescriptor` — IO shapes.
* :func:`draft_rollout`, :func:`start_rollout`,
  :func:`record_offer_outcome`,
  :func:`set_pod_pin`, :func:`delete_pod_pin`,
  :func:`get_pin_map`,
  :func:`get_rollout`,
  :func:`list_rollouts`.
* :class:`UpgradeArtifactSourceProtocol` +
  :class:`ObjectStoreArtifactSource` reference.
* :class:`RolloutPolicyProtocol` +
  :class:`FixedSetRolloutPolicy` reference.
* :class:`UpgradeEventTopics`.
* Errors: :class:`UpgradeError`,
  :class:`InvalidRolloutTransitionError`,
  :class:`PinConflictError`,
  :class:`RolloutNotFoundError`.
* :func:`register_builtin_extensions`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai.pychestrate.webservice.clients.upgrades.dtos import (
    ArtifactDescriptor,
    FleetSnapshot,
    OfferOutcomeReport,
)
from ccai.pychestrate.webservice.clients.upgrades.enums import (
    OfferOutcome,
    RolloutState,
    StageState,
)
from ccai.pychestrate.webservice.clients.upgrades.errors import (
    InvalidRolloutTransitionError,
    PinConflictError,
    RolloutNotFoundError,
    UpgradeError,
)
from ccai.pychestrate.webservice.clients.upgrades.events import (
    UpgradeEventTopics,
)
from ccai.pychestrate.webservice.clients.upgrades.factories.fixed_set_policy import (
    FixedSetRolloutPolicy,
)
from ccai.pychestrate.webservice.clients.upgrades.factories.object_store_source import (
    ObjectStoreArtifactSource,
)
from ccai.pychestrate.webservice.clients.upgrades.factories.rollout_policy_protocol import (
    RolloutPolicyProtocol,
)
from ccai.pychestrate.webservice.clients.upgrades.factories.upgrade_artifact_source_protocol import (
    UpgradeArtifactSourceProtocol,
)
from ccai.pychestrate.webservice.clients.upgrades.models import (
    AgentPodPin,
    AgentRollout,
    AgentRolloutStage,
    AgentUpgradeOffer,
)
from ccai.pychestrate.webservice.clients.upgrades.pins import (
    delete_pod_pin,
    get_pin_map,
    set_pod_pin,
)
from ccai.pychestrate.webservice.clients.upgrades.service import (
    OfferRecord,
    RolloutRecord,
    StageRecord,
    draft_rollout,
    get_rollout,
    list_rollouts,
    record_offer_outcome,
    start_rollout,
)
from ccai.pychestrate.webservice.extensions.registry import (
    register_factory_implementation,
)


def register_builtin_extensions() -> None:
    """
        Seed the in-tree :class:`ObjectStoreArtifactSource`
        and :class:`FixedSetRolloutPolicy` references under
        the ``upgrade_artifact_source`` and ``rollout_policy``
        factory protocols.
    """
    register_factory_implementation(implementation=ObjectStoreArtifactSource)
    register_factory_implementation(implementation=FixedSetRolloutPolicy)
    return
