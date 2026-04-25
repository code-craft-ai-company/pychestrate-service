"""
.. module:: extensions.sandbox.events
    :synopsis: Extension-sandbox bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class SandboxEventTopics:
    """
        Extension-sandbox bus topics. M1 emits GRANTED +
        REVOKED + AUTHORITY_RELOADED; M2 wires the
        call-denied + hook-denied diagnostics.
    """
    GRANTED = "extension.capability_granted"
    REVOKED = "extension.capability_revoked"
    AUTHORITY_RELOADED = "extension.capability_authority_reloaded"
    CALL_DENIED = "extension.call_denied"
    HOOK_DENIED = "extension.hook_denied"
