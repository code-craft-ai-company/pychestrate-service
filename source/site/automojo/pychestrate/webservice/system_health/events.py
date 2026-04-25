"""
.. module:: system_health.events
    :synopsis: System-health event topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class SystemHealthEventTopics:
    """
        Stable event-bus topics for system-health transitions.
        ``probe.failed`` / ``probe.recovered`` fire on per-probe
        ok→fail / fail→ok transitions; ``overall.changed``
        fires when the aggregate verdict (ok / degraded /
        failing) flips.
    """
    OVERALL_CHANGED: str = "system_health.overall.changed"
    PROBE_FAILED: str = "system_health.probe.failed"
    PROBE_RECOVERED: str = "system_health.probe.recovered"
