"""
.. module:: orchestration.infra.drift.events
    :synopsis: Drift-detection bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class DriftEventTopics:
    """
        Drift-detection bus topics.
    """
    SCHEDULE_SET = "entity.drift.schedule_set"
    SCHEDULE_DISABLED = "entity.drift.schedule_disabled"
    RUN_TRIGGERED = "entity.drift.run_triggered"
    REPORT_INGESTED = "entity.drift.report_ingested"
    DRIFT_DETECTED = "entity.drift.detected"
    INGEST_FAILED = "entity.drift.ingest_failed"
