"""
.. module:: security.auth.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 1-authentication.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class AuthEventTopics:
    """
        String constants for every entity topic owned by 1-authentication.
    """

    SESSION_OPENED: str = "entity.session.opened"
    SESSION_CLOSED: str = "entity.session.closed"
    SESSION_REFRESHED: str = "entity.session.refreshed"
    SESSIONS_REVOKED: str = "entity.session.revoked"
    LOGIN_REJECTED: str = "entity.auth.login.rejected"
    MFA_ENROLLMENT_CREATED: str = "entity.mfa.enrollment.created"
    MFA_ENROLLMENT_VERIFIED: str = "entity.mfa.enrollment.verified"
    MFA_ENROLLMENT_REMOVED: str = "entity.mfa.enrollment.removed"
    MFA_CHALLENGE_ISSUED: str = "entity.mfa.challenge.issued"
    MFA_CHALLENGE_VERIFIED: str = "entity.mfa.challenge.verified"
    MFA_CHALLENGE_REJECTED: str = "entity.mfa.challenge.rejected"
