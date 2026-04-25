"""
.. module:: orchestration.test.triage.events
    :synopsis: Triage / bug-linking bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class TriageEventTopics:
    """
        Triage / bug-linking bus topics.
    """
    OPENED = "entity.triage.opened"
    RECLASSIFIED = "entity.triage.reclassified"
    TICKET_LINKED = "entity.triage.ticket_linked"
