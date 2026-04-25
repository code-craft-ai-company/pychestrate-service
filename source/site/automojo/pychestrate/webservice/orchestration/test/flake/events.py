"""
.. module:: orchestration.test.flake.events
    :synopsis: Flake-tracking bus topic constants.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


class FlakeEventTopics:
    """
        Flake-tracking bus topics. M1 emits OUTCOME_RECORDED,
        CLASSIFIED, QUARANTINED and QUARANTINE_CLEARED. M2 adds
        BROKEN_ALERTED + SAMPLE_INSUFFICIENT diagnostics.
    """
    OUTCOME_RECORDED = "entity.flake.outcome_recorded"
    CLASSIFIED = "entity.flake.classified"
    QUARANTINED = "entity.flake.quarantined"
    QUARANTINE_CLEARED = "entity.flake.quarantine_cleared"
    BROKEN_ALERTED = "entity.flake.broken_alerted"
