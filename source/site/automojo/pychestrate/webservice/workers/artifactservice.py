"""
.. module:: workers.artifactservice
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Service-layer operations for worker-job artifacts.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import hashlib
import os

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.workers.artifactmodels import (
    ArtifactStorageKind,
    WorkerJobArtifact,
)
from automojo.pychestrate.webservice.workers.jobmodels import WorkerJob


# 10 MB inline-storage default — operators can raise via
# PYCHESTRATE_ARTIFACT_MAX_INLINE_BYTES once filesystem storage
# arrives in a follow-up slice.
_DEFAULT_MAX_INLINE_BYTES = 10 * 1024 * 1024


class ArtifactTooLargeError(Exception):
    """
        Raised when an upload exceeds the configured inline
        size cap. Operators tune the cap via
        ``PYCHESTRATE_ARTIFACT_MAX_INLINE_BYTES``.
    """


class ArtifactNotFoundError(Exception):
    """
        Raised when an artifact_id has no row.
    """


class ArtifactJobMismatchError(Exception):
    """
        Raised when a request scopes an artifact to a specific
        ``job_id`` but the artifact's row points at a different
        job. Defends against URL-tampering reads.
    """


@dataclass(frozen=True)
class ArtifactView:
    """
        Caller-facing snapshot of a :class:`WorkerJobArtifact`
        row (without the bytes — fetched via a separate
        endpoint).
    """
    artifact_id: str
    job_id: str
    worker_id: Optional[str]
    attempt: int
    name: str
    kind: str
    content_type: str
    size_bytes: int
    content_hash: str
    storage_kind: str
    attributes: Dict[str, Any]
    created_at: str


def _to_view(*, row: WorkerJobArtifact) -> ArtifactView:
    if row.worker_id is not None:
        worker_field: Optional[str] = str(row.worker_id)
    else:
        worker_field = None
    if row.attributes is not None:
        attrs = dict(row.attributes)
    else:
        attrs = {}
    rtnval = ArtifactView(
        artifact_id=str(row.artifact_id),
        job_id=str(row.job_id),
        worker_id=worker_field,
        attempt=int(row.attempt) if row.attempt is not None else 1,
        name=row.name,
        kind=row.kind,
        content_type=row.content_type,
        size_bytes=int(row.size_bytes),
        content_hash=row.content_hash,
        storage_kind=row.storage_kind,
        attributes=attrs,
        created_at=row.created_at.isoformat(),
    )
    return rtnval


def _resolve_max_inline_bytes(
        *,
        environment: Optional[Dict[str, str]] = None,
    ) -> int:
    """
        Read the configured inline-storage size cap. Defaults
        to 10 MiB; ``PYCHESTRATE_ARTIFACT_MAX_INLINE_BYTES``
        overrides.
    """
    if environment is None:
        env = os.environ
    else:
        env = environment
    raw = env.get("PYCHESTRATE_ARTIFACT_MAX_INLINE_BYTES", None)
    if raw is None:
        rtnval = _DEFAULT_MAX_INLINE_BYTES
        return rtnval
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        rtnval = _DEFAULT_MAX_INLINE_BYTES
        return rtnval
    if parsed <= 0:
        rtnval = _DEFAULT_MAX_INLINE_BYTES
        return rtnval
    rtnval = parsed
    return rtnval


def _hash_content(*, content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    rtnval = digest
    return rtnval


def upload_artifact(
        *,
        db_session: DbSession,
        job_id: str,
        worker_id: Optional[str],
        name: str,
        content: bytes,
        kind: str = "binary",
        content_type: str = "application/octet-stream",
        attributes: Optional[Dict[str, Any]] = None,
        max_inline_bytes: Optional[int] = None,
    ) -> ArtifactView:
    """
        Insert an inline-storage artifact for ``job_id``.

        :raises LookupError: When ``job_id`` is unknown.
        :raises ArtifactTooLargeError: When ``content`` exceeds
                                       the configured cap.
    """
    if name is None or len(str(name).strip()) == 0:
        err_lines = [
            "Artifact name is required.",
        ]
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if content is None:
        content_value = b""
    else:
        content_value = bytes(content)
    if max_inline_bytes is None:
        cap = _resolve_max_inline_bytes()
    else:
        cap = int(max_inline_bytes)
    if len(content_value) > cap:
        err_lines = [
            "Artifact content exceeds inline-storage cap.",
            "SIZE_BYTES: {}".format(len(content_value)),
            "CAP_BYTES: {}".format(cap),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ArtifactTooLargeError(err_msg) from None

    job_row = (
        db_session.query(WorkerJob)
        .filter(WorkerJob.job_id == job_id)
        .first()
    )
    if job_row is None:
        err_lines = [
            "Worker job not found.",
            "JOB_ID: {}".format(job_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise LookupError(err_msg) from None

    attempt_value = (
        int(job_row.attempt) if job_row.attempt is not None else 1
    )
    if attributes is None:
        attrs_value: Dict[str, Any] = {}
    else:
        attrs_value = dict(attributes)
    if content_type is None or len(content_type) == 0:
        content_type_value = "application/octet-stream"
    else:
        content_type_value = str(content_type)
    if kind is None or len(kind) == 0:
        kind_value = "binary"
    else:
        kind_value = str(kind)

    row = WorkerJobArtifact(
        artifact_id=new_uuid(),
        job_id=job_id,
        worker_id=worker_id,
        attempt=attempt_value,
        name=str(name).strip(),
        kind=kind_value,
        content_type=content_type_value,
        size_bytes=len(content_value),
        content_hash=_hash_content(content=content_value),
        storage_kind=ArtifactStorageKind.INLINE.value,
        content=content_value,
        filesystem_path=None,
        attributes=attrs_value,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(row)
    db_session.commit()
    rtnval = _to_view(row=row)
    return rtnval


def list_artifacts_for_job(
        *,
        db_session: DbSession,
        job_id: str,
    ) -> List[ArtifactView]:
    """
        List every artifact attached to ``job_id``, oldest first
        so the caller can replay the test's evidence in order.
    """
    rows = (
        db_session.query(WorkerJobArtifact)
        .filter(WorkerJobArtifact.job_id == job_id)
        .order_by(WorkerJobArtifact.created_at.asc())
        .all()
    )
    rtnval = [_to_view(row=r) for r in rows]
    return rtnval


def read_artifact_metadata(
        *,
        db_session: DbSession,
        artifact_id: str,
        scoped_job_id: Optional[str] = None,
    ) -> ArtifactView:
    """
        Read one artifact's metadata.

        :param scoped_job_id: When supplied, the artifact's
                              ``job_id`` must match (defends
                              against URL-tampered reads from a
                              job-scoped REST path).
        :raises ArtifactNotFoundError: When the id has no row.
        :raises ArtifactJobMismatchError: When the scoped check
                                          fails.
    """
    row = (
        db_session.query(WorkerJobArtifact)
        .filter(WorkerJobArtifact.artifact_id == artifact_id)
        .first()
    )
    if row is None:
        err_lines = [
            "Artifact not found.",
            "ARTIFACT_ID: {}".format(artifact_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ArtifactNotFoundError(err_msg) from None
    if scoped_job_id is not None:
        if str(row.job_id) != str(scoped_job_id):
            err_lines = [
                "Artifact does not belong to the scoped job.",
                "ARTIFACT_ID: {}".format(artifact_id),
                "EXPECTED_JOB_ID: {}".format(scoped_job_id),
                "ACTUAL_JOB_ID: {}".format(row.job_id),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ArtifactJobMismatchError(err_msg) from None
    rtnval = _to_view(row=row)
    return rtnval


def read_artifact_content(
        *,
        db_session: DbSession,
        artifact_id: str,
        scoped_job_id: Optional[str] = None,
    ) -> bytes:
    """
        Read the raw bytes of one artifact. Honours the same
        ``scoped_job_id`` defence as the metadata reader.
    """
    row = (
        db_session.query(WorkerJobArtifact)
        .filter(WorkerJobArtifact.artifact_id == artifact_id)
        .first()
    )
    if row is None:
        err_lines = [
            "Artifact not found.",
            "ARTIFACT_ID: {}".format(artifact_id),
        ]
        err_msg = os.linesep.join(err_lines)
        raise ArtifactNotFoundError(err_msg) from None
    if scoped_job_id is not None:
        if str(row.job_id) != str(scoped_job_id):
            err_lines = [
                "Artifact does not belong to the scoped job.",
                "ARTIFACT_ID: {}".format(artifact_id),
                "EXPECTED_JOB_ID: {}".format(scoped_job_id),
                "ACTUAL_JOB_ID: {}".format(row.job_id),
            ]
            err_msg = os.linesep.join(err_lines)
            raise ArtifactJobMismatchError(err_msg) from None
    if row.storage_kind != ArtifactStorageKind.INLINE.value:
        err_lines = [
            "Non-inline storage not yet supported.",
            "STORAGE_KIND: {}".format(row.storage_kind),
        ]
        err_msg = os.linesep.join(err_lines)
        raise NotImplementedError(err_msg) from None
    if row.content is None:
        rtnval = b""
        return rtnval
    rtnval = bytes(row.content)
    return rtnval
