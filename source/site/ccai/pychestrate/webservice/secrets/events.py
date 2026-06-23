"""
.. module:: secrets.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 1-secrets-vault.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class SecretEventTopics:
    """
        String constants for every entity topic owned by 1-secrets-vault.
    """

    SECRET_CREATED: str = "entity.secret.created"
    SECRET_ROTATED: str = "entity.secret.rotated"
    SECRET_EXPIRED: str = "entity.secret.expired"
    SECRET_FORCE_EXPIRED: str = "entity.secret.force_expired"
    SECRET_ACCESSED: str = "entity.secret.accessed"
    SECRET_ACCESS_DENIED: str = "entity.secret.access_denied"
    SECRET_ACL_CHANGED: str = "entity.secret.acl.changed"
