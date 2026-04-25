"""
.. module:: resources.inventory.events
    :synopsis: Bus topic constants for resource inventory.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class ResourceEventTopics:
    """
        Inventory bus topics.
    """
    REGISTERED = "entity.resource.registered"
    UPDATED = "entity.resource.updated"
    RETIRED = "entity.resource.retired"
    QUARANTINED = "entity.resource.quarantined"
    UNQUARANTINED = "entity.resource.unquarantined"
    STATE_CHANGED = "entity.resource.state_changed"
