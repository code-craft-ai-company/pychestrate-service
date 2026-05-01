"""
.. module:: workers.artifactmodels
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SQLAlchemy ORM model for worker-job artifacts.

.. moduleauthor:: Automation Mojo LLC

A :class:`WorkerJobArtifact` row is a file produced by a worker
during the execution of a :class:`WorkerJob` — typically a test
log, screenshot, packet capture, or captured serial-console
output. ``stdout`` / ``stderr`` are first-class on the job row
itself; this table is for the *other* output that a CI / test
forensic workflow needs.

Storage today is inline (the bytes live in the DB row's
``content`` column). Larger blobs will move to filesystem /
object storage in a follow-up slice; the ``storage_kind``
discriminator is in the schema now so that migration is
additive.
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
    Integer,
    JSON,
    LargeBinary,
    String,
)
from sqlalchemy_utils import UUIDType

from automojo.pychestrate.core.defaults import utc_now
from automojo.pychestrate.webservice.persistence.schema import (
    PychestratePhase1Base,
)


class ArtifactStorageKind(str, enum.Enum):
    """
        Where the artifact bytes live.

        * ``INLINE`` — stored in the DB row's ``content`` column.
          Cheap for small files; the only kind shipped today.
        * ``FILESYSTEM`` — stored on disk; ``filesystem_path``
          carries the absolute path. Reserved for a follow-up.
    """
    INLINE = "inline"
    FILESYSTEM = "filesystem"


class WorkerJobArtifact(PychestratePhase1Base):
    """
        Worker-job artifact row.

        :ivar artifact_id: Server-issued primary key.
        :ivar job_id: FK to ``worker_jobs.job_id``.
        :ivar worker_id: FK to ``workers.worker_id`` for the
                         worker that produced the artifact.
                         Nullable so the row survives a worker
                         deregistration.
        :ivar attempt: Which attempt of the job produced this
                       artifact, 1-indexed. Lets retried jobs
                       keep evidence from prior attempts
                       distinguishable.
        :ivar name: Operator-meaningful file name
                    (e.g. ``screenshot.png``).
        :ivar kind: Discriminator string. Conventional values:
                    ``log``, ``screenshot``, ``pcap``,
                    ``serial-console``, ``binary``.
        :ivar content_type: MIME type for download.
        :ivar size_bytes: Size of the content payload.
        :ivar content_hash: SHA-256 hex of the content.
        :ivar storage_kind: ``inline`` (today) or ``filesystem``.
        :ivar content: Inline bytes when
                       ``storage_kind == "inline"``.
        :ivar filesystem_path: Path on disk when
                               ``storage_kind == "filesystem"``.
        :ivar attributes: Free-form JSON metadata
                          (e.g. ``{compressed: true}``).
        :ivar created_at: When the artifact was uploaded.
    """

    __tablename__ = "worker_job_artifacts"
    __table_args__ = (
        Index("ix_worker_job_artifacts_job_id", "job_id"),
        Index("ix_worker_job_artifacts_kind", "kind"),
    )

    artifact_id = Column(UUIDType(binary=False), primary_key=True)
    job_id = Column(
        UUIDType(binary=False),
        ForeignKey("worker_jobs.job_id", ondelete="CASCADE"),
        nullable=False,
    )
    worker_id = Column(
        UUIDType(binary=False),
        ForeignKey("workers.worker_id", ondelete="SET NULL"),
        nullable=True,
    )
    attempt = Column(Integer, nullable=False, default=1)
    name = Column(String(255), nullable=False)
    kind = Column(String(64), nullable=False, default="binary")
    content_type = Column(
        String(128), nullable=False, default="application/octet-stream",
    )
    size_bytes = Column(Integer, nullable=False, default=0)
    content_hash = Column(String(128), nullable=False, default="")
    storage_kind = Column(
        String(32), nullable=False,
        default=ArtifactStorageKind.INLINE.value,
    )
    content = Column(LargeBinary, nullable=True)
    filesystem_path = Column(String(1024), nullable=True)
    attributes = Column(JSON, nullable=False, default=dict)
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=utc_now,
    )
