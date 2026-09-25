"""
.. module:: jobs.dispatch.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy model for the dispatch-attempt archive.

.. moduleauthor:: Code Craft AI LLC

``dispatch_attempt`` carries one row per attempted dispatch. A run
can accumulate multiple rows if the dispatcher re-transmits after
an ack timeout (M2 path). The status column captures the lifecycle
of the attempt at the transport layer, distinct from the run's own
state machine.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Index,
    String,
    Text,
)
from sqlalchemy_utils.types.uuid import UUIDType

from ccai.pychestrate.core.utc_datetime import UtcDateTime
from ccai.pychestrate.core.defaults import utc_now
from ccai.pychestrate.core.orm import SerializableModel

from ccai.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class DispatchAttemptStatus(str, enum.Enum):
    """
        Lifecycle of a single dispatch attempt at the transport
        layer. Independent of the run's state machine — an attempt
        can succeed at the transport layer and still produce a run
        that later fails.
    """
    PENDING = "pending"
    TRANSMITTED = "transmitted"
    ACKED = "acked"
    TRANSPORT_FAILED = "transport_failed"
    ACK_TIMEOUT = "ack_timeout"
    ABORTED = "aborted"


DISPATCH_ATTEMPT_STATUS_ENUM = "dispatch_attempt_status"


class DispatchAttempt(PychestratePhase1Base, SerializableModel):
    """
        One row per dispatch transmission attempt. Written inside
        :meth:`JobDispatcher.dispatch`'s transaction alongside the
        envelope archive row so queries that need the full attempt
        history for a run find every attempt in order.
    """

    __tablename__ = "jobs_dispatch_attempt"

    attempt_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    client_id = Column(UUIDType(binary=False), nullable=False)
    pod_id = Column(UUIDType(binary=False), nullable=False)
    envelope_id = Column(UUIDType(binary=False), nullable=False)
    strategy_name = Column(String(64), nullable=False, default="")
    transport_name = Column(String(64), nullable=False, default="")
    status = Column(
        Enum(DispatchAttemptStatus, name=DISPATCH_ATTEMPT_STATUS_ENUM),
        nullable=False,
        default=DispatchAttemptStatus.PENDING,
    )
    created_at = Column(UtcDateTime(timezone=True), nullable=False, default=utc_now)
    transmitted_at = Column(UtcDateTime(timezone=True), nullable=True)
    acked_at = Column(UtcDateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_jobs_dispatch_attempt_run_id", "run_id"),
        Index("ix_jobs_dispatch_attempt_client_id", "client_id"),
        Index("ix_jobs_dispatch_attempt_status", "status"),
        Index("ix_jobs_dispatch_attempt_envelope_id", "envelope_id"),
    )
