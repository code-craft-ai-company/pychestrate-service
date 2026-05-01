"""
.. module:: workers.models
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy ORM models for the worker registry.

.. moduleauthor:: Automation Mojo LLC

A :class:`Worker` row represents anything that can run flow tasks
on behalf of pychestrate:

* ``local-process`` workers run inside the service host (the
  in-process pool that ships with the runtime).
* ``remote-machine`` workers run on a Raspberry Pi / UEFI host /
  VM and connect back via the bearer-token auth path. They are
  linked to a previously-enrolled :class:`Client` row through
  ``client_id``.

Status cycles ``idle → running → idle`` while the worker is alive,
flips to ``draining`` when an admin requests graceful shutdown, and
ends at ``offline`` when ``last_heartbeat_at`` passes the liveness
threshold.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import enum

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy_utils import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


class WorkerKind(str, enum.Enum):
    """
        How the worker is managed.
    """
    LOCAL_PROCESS = "local-process"
    REMOTE_MACHINE = "remote-machine"


class WorkerStatus(str, enum.Enum):
    """
        Lifecycle state of a worker.
    """
    IDLE = "idle"
    RUNNING = "running"
    DRAINING = "draining"
    OFFLINE = "offline"


class Worker(PychestratePhase1Base):
    """
        Worker registry row.

        :ivar worker_id: Server-issued primary key.
        :ivar name: Unique within a project (or globally for
                    project-less local workers).
        :ivar kind: ``local-process`` or ``remote-machine``.
        :ivar project_id: Owning project. ``None`` for service-side
                          local workers.
        :ivar client_id: FK to ``clients.client_id``. Set only when
                         ``kind == REMOTE_MACHINE``.
        :ivar status: Current :class:`WorkerStatus`.
        :ivar registered_at: First-seen timestamp.
        :ivar last_heartbeat_at: Most recent heartbeat.
        :ivar attributes: Free-form JSON for capabilities / labels.
        :ivar lease_holder: When set, the worker is exclusively
                            reserved for this opaque holder
                            (typically a ``flow_id``) until
                            ``lease_expires_at`` or until an
                            explicit release. Other holders
                            cannot claim jobs on this worker
                            even if their selectors match.
        :ivar lease_acquired_at: When the current lease started.
        :ivar lease_expires_at: TTL deadline for the lease. An
                                expired lease is treated as
                                released; the stale-worker
                                sweeper clears the row fields on
                                the next pass.
    """

    __tablename__ = "workers"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "name", name="uq_workers_project_name",
        ),
        Index("ix_workers_status", "status"),
        Index("ix_workers_kind", "kind"),
        Index("ix_workers_lease_holder", "lease_holder"),
    )

    worker_id = Column(UUIDType(binary=False), primary_key=True)
    name = Column(String(255), nullable=False)
    kind = Column(String(32), nullable=False)
    project_id = Column(UUIDType(binary=False), nullable=True)
    client_id = Column(
        UUIDType(binary=False),
        ForeignKey("clients_clients.client_id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(String(32), nullable=False, default=WorkerStatus.IDLE.value)
    registered_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    attributes = Column(JSON, nullable=False, default=dict)
    lease_holder = Column(String(255), nullable=True)
    lease_acquired_at = Column(DateTime(timezone=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
