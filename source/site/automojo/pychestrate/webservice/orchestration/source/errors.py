"""
.. module:: orchestration.source.errors
    :synopsis: Source-integrations exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class SourceIntegrationsError(Exception):
    """
        Base for recoverable source-integrations errors.
    """


class ScmConfigNotFoundError(SourceIntegrationsError):
    """
        Raised when a project's SCM config has not been
        registered.
    """


class ScmProviderNotFoundError(SourceIntegrationsError):
    """
        Raised when no registered :class:`ScmProviderProtocol`
        claims the supplied provider name.
    """


class ScmSignatureInvalidError(SourceIntegrationsError):
    """
        Raised when webhook signature verification fails.
    """


class ScmPayloadInvalidError(SourceIntegrationsError):
    """
        Raised when a webhook body is too large, malformed, or
        otherwise rejected by the provider's parser.
    """
