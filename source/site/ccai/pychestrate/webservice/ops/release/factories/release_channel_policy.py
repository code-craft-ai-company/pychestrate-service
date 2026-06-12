"""
.. module:: ops.release.factories.release_channel_policy
    :synopsis: ``release_channel_policy`` factory contract.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Sequence, Tuple

from ccai.pychestrate.webservice.extensions.factory_protocol import (
    FactoryProtocolBase,
)
from ccai.pychestrate.webservice.ops.release.models import ReleaseChannel


@dataclass(frozen=True)
class ConsumerDescriptor:
    """
        Minimal description of a fleet member the policy
        evaluates against. M2 enriches the descriptor with
        labels / region / capability tags.
    """
    consumer_id: str
    region: str = ""
    cohort: str = ""


@dataclass(frozen=True)
class EligibleConsumerSet:
    """
        Output of a policy's
        :meth:`compute_eligible_consumers` call.
    """
    consumer_ids: Tuple[str, ...]
    fraction: float


class ReleaseChannelPolicyProtocol(FactoryProtocolBase):
    """
        Contract for the channel-policy router. The policy
        decides which consumers are eligible for a release at
        a given fraction and supplies the per-channel initial
        rollout fraction.
    """

    factory_protocol_name: str = "release_channel_policy"
    protocol_schema_version: int = 1

    @classmethod
    def channel(cls) -> ReleaseChannel:
        """
            Channel this policy claims. The default
            HashRingChannelPolicy claims every channel via
            ``channel_set``; override here for single-channel
            policies.
        """
        raise NotImplementedError("Subclasses must implement channel")

    @classmethod
    def channel_set(cls) -> Tuple[ReleaseChannel, ...]:
        """
            Set of channels this policy claims. Defaults to
            ``(channel(),)``; override to claim multiple
            channels at once.
        """
        rtnval = (cls.channel(),)
        return rtnval

    @classmethod
    def initial_fraction(cls, *, channel: ReleaseChannel) -> float:
        """
            Initial rollout fraction at publish time on the
            given channel. M1 policy contract returns
            0.05 for canary, 0.25 for beta, 1.00 for stable.
        """
        raise NotImplementedError("Subclasses must implement initial_fraction")

    @classmethod
    def compute_eligible_consumers(
            cls,
            *,
            release_id: str,
            fraction: float,
            universe: Sequence[ConsumerDescriptor]
        ) -> EligibleConsumerSet:
        """
            Compute the eligible consumer subset for a release
            at the given fraction.
        """
        raise NotImplementedError(
            "Subclasses must implement compute_eligible_consumers",
        )
