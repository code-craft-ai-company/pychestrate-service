"""
.. module:: orchestration.rpa.events
    :synopsis: RPA-orchestration bus topic constants.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


class RpaEventTopics:
    """
        RPA-orchestration bus topics.
    """
    JOB_TYPE_REGISTERED = "entity.rpa.job_type_registered"
    JOB_TYPE_VERSION_PUBLISHED = "entity.rpa.job_type_published"
    JOB_TYPE_RETIRED = "entity.rpa.job_type_retired"
    JOB_TYPE_UPDATED = "entity.rpa.job_type_updated"
    SPEC_CREATED = "entity.rpa.spec_created"
    SPEC_UPDATED = "entity.rpa.spec_updated"
    SPEC_DELETED = "entity.rpa.spec_deleted"
    JOB_STARTED = "entity.rpa.job_started"
    JOB_DISPATCHED = "entity.rpa.job_dispatched"
    JOB_STATE_CHANGED = "entity.rpa.job_state_changed"
    JOB_COMPLETED = "entity.rpa.job_completed"
    JOB_FAILED = "entity.rpa.job_failed"
    JOB_CANCELLED = "entity.rpa.job_cancelled"
