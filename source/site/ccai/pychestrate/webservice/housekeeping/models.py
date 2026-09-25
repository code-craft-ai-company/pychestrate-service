"""
.. module:: housekeeping.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Lease rows that let one server process at a time run each
               housekeeping task.

.. moduleauthor:: Code Craft AI LLC

Every server process runs the same periodic housekeeping tasks. A task
that changes shared state (activating a reservation, expiring an
allocation, probing a device) must run in one process at a time, so a
run first takes the task's lease row. A lease its holder never released
lapses after its time-to-live, so a process that died mid-run cannot
stop a task for good. The row also records when the task last ran and
what it did.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import Column, DateTime, String

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class HousekeepingLease(PychestratePhase1Base, SerializableModel):
    """
        The lease on one housekeeping task and the outcome of its last run.
    """

    __tablename__ = "housekeeping_lease"

    task_name = Column(String(128), primary_key=True)
    holder_id = Column(String(256), nullable=False)
    expires_at = Column(UtcDateTime(timezone=True), nullable=False)
    last_started_at = Column(UtcDateTime(timezone=True), nullable=True)
    last_finished_at = Column(UtcDateTime(timezone=True), nullable=True)
    last_outcome = Column(String(512), nullable=True)
