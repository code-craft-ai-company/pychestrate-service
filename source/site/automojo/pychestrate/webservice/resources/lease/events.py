"""
.. module:: resources.lease.events
    :synopsis: Lease bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class LeaseEventTopics:
    """
        Lease bus topics. M1 emits ATTACHED, RENEWED, EXPIRED and
        RELEASED; M2 adds NEARING_EXPIRY and CAP_REACHED.
    """
    ATTACHED = "entity.lease.attached"
    RENEWED = "entity.lease.renewed"
    EXPIRED = "entity.lease.expired"
    RELEASED = "entity.lease.released"
