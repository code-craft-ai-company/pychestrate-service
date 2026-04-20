"""
.. module:: audit.events
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Event topic names published by 1-audit-log.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class AuditEventTopics:
    """
        String constants for every entity topic owned by 1-audit-log.
    """

    AUDIT_EMITTED: str = "entity.audit.emitted"
    AUDIT_SINK_UNHEALTHY: str = "entity.audit.sink.unhealthy"
    AUDIT_SINK_HEALTHY: str = "entity.audit.sink.healthy"
    AUDIT_CHAIN_BROKEN: str = "entity.audit.chain.broken"
    AUDIT_CATALOG_RELOADED: str = "entity.audit.catalog.reloaded"
