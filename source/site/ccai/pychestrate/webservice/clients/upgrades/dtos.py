"""
.. module:: clients.upgrades.dtos
    :synopsis: 3-agent-upgrade-channel data-transfer objects.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, Mapping, Tuple


@dataclass(frozen=True)
class FleetMember:
    """
        Single fleet member used by the policy to compute the
        offer set.
    """
    client_id: str
    region: str = ""
    cohort: str = ""


@dataclass(frozen=True)
class FleetSnapshot:
    """
        Snapshot of the registered client population at the
        time the offer set is computed.
    """
    members: Tuple[FleetMember, ...]


@dataclass(frozen=True)
class OfferOutcomeReport:
    """
        Caller-supplied outcome report. The transport-side
        ``UpgradeOutcomeFrame`` is decoded into this shape
        before being persisted.
    """
    offer_id: str
    outcome: str
    detail: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactDescriptor:
    """
        Per-artifact metadata returned by an artifact source.
    """
    artifact_ref: str
    artifact_uri: str
    artifact_sha256: str
    byte_size: int = 0
    content_type: str = ""
