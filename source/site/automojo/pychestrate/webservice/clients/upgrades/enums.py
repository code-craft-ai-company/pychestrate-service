"""
.. module:: clients.upgrades.enums
    :synopsis: 3-agent-upgrade-channel enumerations.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum


class RolloutState(str, enum.Enum):
    """
        Top-level rollout state. M1 lands DRAFT + ACTIVE +
        COMPLETED; M2 fills out HALTED + ABANDONED on top of
        the same enum so consumers do not see an enum value
        churn.
    """
    DRAFT = "draft"
    ACTIVE = "active"
    HALTED = "halted"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class StageState(str, enum.Enum):
    """
        Per-stage lifecycle.
    """
    PENDING = "pending"
    ACTIVE = "active"
    HELD = "held"
    COMPLETED = "completed"
    HALTED = "halted"


class OfferOutcome(str, enum.Enum):
    """
        Per-offer terminal outcomes reported by a client.
    """
    OFFERED = "offered"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    DEFERRED = "deferred"
    EXPIRED = "expired"
    SHA256_MISMATCH = "sha256_mismatch"
    FETCH_FAILED = "fetch_failed"


ROLLOUT_STATE_ENUM = "agent_rollout_state"
STAGE_STATE_ENUM = "agent_rollout_stage_state"
OFFER_OUTCOME_ENUM = "agent_upgrade_offer_outcome"
