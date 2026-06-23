"""
.. module:: clients.enums
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Shared enumerations for the client plane.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum


class ClientStatus(enum.Enum):
    """
        Lifecycle status of an enrolled client. The enrollment service owns
        transitions from ACTIVE to SUSPENDED / REVOKED.
    """
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"


class LivenessState(enum.Enum):
    """
        Runtime liveness state driven by heartbeat cadence. ``ALIVE`` is the
        default after enrollment; ``DEGRADED`` indicates missed heartbeats;
        ``LOST`` indicates the agent has been unreachable beyond a
        configured threshold.
    """
    ALIVE = "ALIVE"
    DEGRADED = "DEGRADED"
    LOST = "LOST"


class TokenStatus(enum.Enum):
    """
        Lifecycle status of an enrollment token.
    """
    PENDING = "PENDING"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class RevocationReason(enum.Enum):
    """
        Why a client was revoked. The registry persists the last reason
        on the revocation row for audit context.
    """
    ROTATED = "ROTATED"
    DECOMMISSIONED = "DECOMMISSIONED"
    COMPROMISED = "COMPROMISED"
    ADMIN_REQUEST = "ADMIN_REQUEST"
