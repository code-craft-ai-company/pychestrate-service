"""
.. module:: ops.release.factories.hash_ring_policy
    :synopsis: HashRingChannelPolicy reference at PRECEDENCE=1000.

The policy claims every channel and selects the lowest-ranked
``fraction * 10000`` consumers under
``HMAC-SHA-256(consumer_id, release_id) mod 10000``. The
deterministic ranking lets a consumer's "is eligible" answer
remain stable across promotions on the same release — once
selected, the consumer keeps the offer as the fraction
expands.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import hmac

from typing import Sequence, Tuple

from automojo.pychestrate.webservice.ops.release.factories.release_channel_policy import (
    ConsumerDescriptor,
    EligibleConsumerSet,
    ReleaseChannelPolicyProtocol,
)
from automojo.pychestrate.webservice.ops.release.models import ReleaseChannel


HASH_RING_PRECEDENCE: int = 1000
RING_BUCKET_COUNT: int = 10000

CANARY_INITIAL_FRACTION: float = 0.05
BETA_INITIAL_FRACTION: float = 0.25
STABLE_INITIAL_FRACTION: float = 1.0


class HashRingChannelPolicy(ReleaseChannelPolicyProtocol):
    """
        Default channel policy. Claims every channel; ranks
        consumers via HMAC-SHA-256 over
        ``consumer_id : release_id`` modulo
        :data:`RING_BUCKET_COUNT`.
    """

    factory_protocol_name: str = "release_channel_policy"
    protocol_schema_version: int = 1
    PRECEDENCE: int = HASH_RING_PRECEDENCE

    @classmethod
    def channel(cls) -> ReleaseChannel:
        rtnval = ReleaseChannel.CANARY
        return rtnval

    @classmethod
    def channel_set(cls) -> Tuple[ReleaseChannel, ...]:
        rtnval: Tuple[ReleaseChannel, ...] = (
            ReleaseChannel.CANARY,
            ReleaseChannel.BETA,
            ReleaseChannel.STABLE,
        )
        return rtnval

    @classmethod
    def initial_fraction(cls, *, channel: ReleaseChannel) -> float:
        if channel == ReleaseChannel.CANARY:
            rtnval = CANARY_INITIAL_FRACTION
            return rtnval
        if channel == ReleaseChannel.BETA:
            rtnval = BETA_INITIAL_FRACTION
            return rtnval
        if channel == ReleaseChannel.STABLE:
            rtnval = STABLE_INITIAL_FRACTION
            return rtnval
        rtnval = STABLE_INITIAL_FRACTION
        return rtnval

    @classmethod
    def compute_eligible_consumers(
            cls,
            *,
            release_id: str,
            fraction: float,
            universe: Sequence[ConsumerDescriptor]
        ) -> EligibleConsumerSet:
        """
            Return the eligible subset for ``fraction`` of the
            ``universe``. Determinism: the same release_id +
            universe + fraction always produces the same
            ordered subset.
        """
        if fraction <= 0.0:
            rtnval = EligibleConsumerSet(
                consumer_ids=tuple(), fraction=0.0,
            )
            return rtnval
        if fraction >= 1.0:
            rtnval = EligibleConsumerSet(
                consumer_ids=tuple(c.consumer_id for c in universe),
                fraction=1.0,
            )
            return rtnval

        ranked = []
        secret = release_id.encode("utf-8")
        for descriptor in universe:
            digest = hmac.new(
                key=secret,
                msg=descriptor.consumer_id.encode("utf-8"),
                digestmod=hashlib.sha256,
            ).digest()
            bucket = int.from_bytes(digest[:4], byteorder="big") % RING_BUCKET_COUNT
            ranked.append((bucket, descriptor.consumer_id))
        ranked.sort(key=lambda pair: (pair[0], pair[1]))

        cutoff = int(round(fraction * len(ranked)))
        if cutoff <= 0 and len(ranked) > 0:
            cutoff = 1
        chosen = tuple(consumer_id for (_bucket, consumer_id) in ranked[:cutoff])
        rtnval = EligibleConsumerSet(
            consumer_ids=chosen, fraction=fraction,
        )
        return rtnval
