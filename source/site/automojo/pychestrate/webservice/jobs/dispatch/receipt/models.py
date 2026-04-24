"""
.. module:: jobs.dispatch.receipt.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy model for dispatch-receipt rows.

.. moduleauthor:: Automation Mojo LLC

``dispatch_receipt`` rows correlate the service-side
``dispatch_attempt`` + envelope tuple with the client-side
``(client_id, client_local_run_id)`` tuple so subsequent progress
/ result traffic can be routed back to the right run. A client
that retries a receipt post under the same
``(client_id, client_local_run_id)`` pair hits the UNIQUE
constraint and ``record()`` treats the repeat as idempotent
instead of creating a second row.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy_utils.types.uuid import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.core.orm import SerializableModel

from automojo.pychestrate.webservice.persistence.schema import PychestratePhase1Base


class DispatchReceipt(PychestratePhase1Base, SerializableModel):
    """
        One row per dispatch acknowledgment the client reported.
    """

    __tablename__ = "jobs_dispatch_receipt"

    receipt_id = Column(UUIDType(binary=False), primary_key=True)
    run_id = Column(UUIDType(binary=False), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=False)
    client_id = Column(UUIDType(binary=False), nullable=False)
    attempt_id = Column(UUIDType(binary=False), nullable=False)
    envelope_id = Column(UUIDType(binary=False), nullable=False)
    client_local_run_id = Column(String(128), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    deadline_at = Column(DateTime(timezone=True), nullable=True)
    late_arrival = Column(Boolean, nullable=False, default=False)
    launch_pid = Column(Integer, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "client_id", "client_local_run_id",
            name="uq_jobs_dispatch_receipt_client_local_run",
        ),
        Index("ix_jobs_dispatch_receipt_run_id", "run_id"),
        Index("ix_jobs_dispatch_receipt_attempt_id", "attempt_id"),
        Index("ix_jobs_dispatch_receipt_envelope_id", "envelope_id"),
    )
