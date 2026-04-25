"""
.. module:: extensions.sandbox.errors
    :synopsis: Extension-sandbox exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class SandboxError(Exception):
    """
        Base for recoverable sandbox errors.
    """


class UnknownCapabilityError(SandboxError):
    """
        Raised when caller references a capability not in the
        closed vocabulary.
    """


class UnknownExtensionError(SandboxError):
    """
        Raised when caller references an extension not currently
        tracked by the authority.
    """
