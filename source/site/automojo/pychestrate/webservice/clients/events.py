"""
.. module:: clients.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by the client plane.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ClientEventTopics:
    """
        String constants for every ``entity.client.*`` topic.
    """

    TOKEN_ISSUED: str = "entity.client.token_issued"
    TOKEN_REVOKED: str = "entity.client.token_revoked"
    ENROLLED: str = "entity.client.enrolled"
    ENROLL_REJECTED: str = "entity.client.enroll_rejected"
    REGISTERED: str = "entity.client.registered"
    HEARTBEAT: str = "entity.client.heartbeat"
    LIVENESS_CHANGED: str = "entity.client.liveness_changed"
    ATTRIBUTES_CHANGED: str = "entity.client.attributes_changed"
    REVOKED: str = "entity.client.revoked"
