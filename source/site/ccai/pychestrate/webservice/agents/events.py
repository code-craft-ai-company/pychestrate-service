"""
.. module:: agents.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Bus topics published by Layer-3 agent features.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class ClientAgentProtocolEventTopics:
    """
        Topics owned by 3-client-agent-protocol.
    """
    SESSION_OPENED: str = "entity.client.session_opened"
    SESSION_CLOSED: str = "entity.client.session_closed"
    CLIENT_ENROLLED_OVER_PROTOCOL: str = "entity.client.enrolled"
    HEARTBEAT: str = "entity.client.heartbeat"
    FRAME_REJECTED: str = "entity.client.frame_rejected"


class CapabilityEventTopics:
    """
        Topics owned by 3-client-capability-advertisement.
    """
    CAPABILITIES_APPLIED: str = "entity.client.capabilities_applied"
    CAPABILITY_REJECTED: str = "entity.client.capability_rejected"


class AgentUpgradeEventTopics:
    """
        Topics owned by 3-agent-upgrade-channel.
    """
    ROLLOUT_DRAFTED: str = "entity.rollout.drafted"
    ROLLOUT_STARTED: str = "entity.rollout.started"
    ROLLOUT_STAGE_STARTED: str = "entity.rollout.stage_started"
    ROLLOUT_STAGE_COMPLETED: str = "entity.rollout.stage_completed"
    UPGRADE_OFFERED: str = "entity.upgrade.offered"
    UPGRADE_SUCCEEDED: str = "entity.upgrade.succeeded"
    UPGRADE_FAILED: str = "entity.upgrade.failed"
