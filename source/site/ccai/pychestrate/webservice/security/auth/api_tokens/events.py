"""
.. module:: security.auth.api_tokens.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Entity topics published by the API-token feature.

.. moduleauthor:: Code Craft AI LLC

Each topic is captured into the audit store by the matching
:mod:`security.auth.api_tokens.audit_events` pack.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class ApiTokenEventTopics:
    """
        String constants for every entity topic the API-token feature
        publishes.
    """

    TOKEN_CREATED: str = "entity.api_token.created"
    TOKEN_REVOKED: str = "entity.api_token.revoked"
    TOKEN_USED: str = "entity.api_token.used"
