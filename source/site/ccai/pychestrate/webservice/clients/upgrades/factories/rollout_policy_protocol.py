"""
.. module:: clients.upgrades.factories.rollout_policy_protocol
    :synopsis: ``rollout_policy`` factory contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Mapping, Tuple

from ccai.pychestrate.webservice.clients.upgrades.dtos import FleetSnapshot
from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)


class RolloutPolicyProtocol(FactoryProtocolBase):
    """
        Contract for ``rollout_policy`` extensions. The policy
        receives a fleet snapshot and stage params and returns
        the ordered tuple of client ids that should receive an
        offer.
    """

    factory_protocol_name: str = "rollout_policy"
    protocol_schema_version: int = 1

    @classmethod
    def policy_name(cls) -> str:
        """
            Stable identifier the rollout row stores so the
            orchestrator can resolve the policy at start time.
        """
        raise NotImplementedError("Subclasses must implement policy_name")

    @classmethod
    def compute_target_set(
            cls,
            *,
            rollout_id: str,
            fleet: FleetSnapshot,
            params: Mapping[str, Any]
        ) -> Tuple[str, ...]:
        """
            Return the deterministic ordered tuple of client
            ids that should receive an offer for this stage.
        """
        raise NotImplementedError(
            "Subclasses must implement compute_target_set",
        )
