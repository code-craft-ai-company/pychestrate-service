"""
.. module:: webhooks_out.errors
    :synopsis: Webhooks-out exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class WebhookOutError(Exception):
    """
        Base for recoverable webhooks-out errors.
    """


class WebhookTargetNotFoundError(WebhookOutError):
    """
        Raised when a target lookup misses.
    """


class WebhookTargetConflictError(WebhookOutError):
    """
        Raised when (project, name) UNIQUE is violated.
    """


class WebhookTargetInvalidError(WebhookOutError):
    """
        Raised when caller-supplied target fields fail
        validation.
    """
