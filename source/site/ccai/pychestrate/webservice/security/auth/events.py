"""
.. module:: security.auth.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 1-authentication.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class AuthEventTopics:
    """
        String constants for every entity topic owned by 1-authentication.
    """

    SESSION_OPENED: str = "entity.session.opened"
    SESSION_CLOSED: str = "entity.session.closed"
    SESSION_REFRESHED: str = "entity.session.refreshed"
    LOGIN_REJECTED: str = "entity.auth.login.rejected"
    MFA_ENROLLMENT_CREATED: str = "entity.mfa.enrollment.created"
    MFA_ENROLLMENT_REMOVED: str = "entity.mfa.enrollment.removed"
