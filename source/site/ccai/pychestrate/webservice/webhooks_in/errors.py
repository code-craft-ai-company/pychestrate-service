"""
.. module:: webhooks_in.errors
    :synopsis: Webhooks-in exception hierarchy.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class WebhookInError(Exception):
    """
        Base for recoverable inbound-webhook errors.
    """


class WebhookConfigurationNotFoundError(WebhookInError):
    """
        Raised when a configured webhook lookup misses.
    """


class WebhookConfigurationConflictError(WebhookInError):
    """
        Raised when ``(project_id, provider, hook_name)``
        UNIQUE is violated on create.
    """


class WebhookConfigurationInvalidError(WebhookInError):
    """
        Raised when create_webhook receives a malformed
        provider, hook_name, or secret_ref.
    """


class WebhookProviderUnknownError(WebhookInError):
    """
        Raised when a request references a provider with no
        registered :class:`InboundWebhookParserProtocol`
        implementation.
    """


class WebhookSignatureInvalidError(WebhookInError):
    """
        Raised when signature verification fails on a parsed
        request. M1 surfaces this through the dispatcher as a
        :class:`StructuredRejection`.
    """


class WebhookReplayDetectedError(WebhookInError):
    """
        Raised when the replay-cache has already seen the
        ``(provider, hook_name, delivery_id)`` triple.
    """


class WebhookSecretInvalidError(WebhookInError):
    """
        Raised when a create supplies no usable shared secret: none
        at all, both a secret and a ``secret_ref``, or a
        ``secret_ref`` that names no (unexpired) vault secret.
    """


class WebhookSecretAccessDeniedError(WebhookInError):
    """
        Raised when the caller may not store the shared secret in
        the secrets vault, or may not read the vault secret it asked
        to bind.
    """
