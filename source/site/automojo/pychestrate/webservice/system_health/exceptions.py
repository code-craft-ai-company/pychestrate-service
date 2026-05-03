"""
.. module:: system_health.exceptions
    :synopsis: System-health exception hierarchy.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo.errors.exceptions import SemanticError


class HealthRegistryError(Exception):
    """
        Base for recoverable health-registry errors.
    """


class DuplicateProbeError(SemanticError):
    """
        Raised when a probe with the same name is registered
        twice. Inherits :class:`SemanticError` so it bubbles
        per AGENTS.md.
    """


class ProbeNotFoundError(HealthRegistryError):
    """
        Raised when a probe lookup misses.
    """
