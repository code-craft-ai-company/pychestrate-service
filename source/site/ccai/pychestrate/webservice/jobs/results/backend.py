"""
.. module:: jobs.results.backend
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: SharedResultsBackend — allocate + resolve facade.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.jobs.results import repository
from ccai.pychestrate.webservice.jobs.results.errors import (
    AllocationNotFoundError,
)
from ccai.pychestrate.webservice.jobs.results.path_builder import (
    build_canonical_prefix,
)
from ccai.pychestrate.webservice.jobs.results.presign import (
    ArtifactUploadTarget,
    DEFAULT_PRESIGN_TTL_SECONDS,
    mint_local_upload_targets,
)


@dataclass(frozen=True)
class AllocatedResultPath:
    """
        Read-model returned to callers. Stable across releases so
        downstream features bind to this shape rather than the ORM
        row.

        :param run_id: Run UUID.
        :param project_id: Owning project UUID.
        :param backend_driver: Object-store driver name.
        :param backend_key_prefix: Canonical prefix.
        :param allocated_at: Allocation timestamp.
    """
    run_id: str
    project_id: str
    backend_driver: str
    backend_key_prefix: str
    allocated_at: datetime


class SharedResultsBackend:
    """
        Per-run path allocator backed by ``jobs_shared_results_allocation``.
        ``allocate`` is idempotent on ``run_id`` so re-dispatch does
        not fork the path.
    """

    def __init__(self, *, backend_driver: str) -> None:
        """
            :param backend_driver: Driver name persisted on every
                                   allocation row. Resolves through
                                   the ``object_store_driver``
                                   factory at the storage layer.
        """
        self._backend_driver: str = backend_driver
        return

    def backend_driver(self) -> str:
        """
            Return the configured driver name.

            :returns: Driver string.
        """
        rtnval = self._backend_driver
        return rtnval

    def allocate(
            self,
            *,
            db_session: DbSession,
            run_id: str,
            project_id: str,
            project_slug: str,
            job_type: str,
            now: Optional[datetime] = None
        ) -> AllocatedResultPath:
        """
            Return the per-run allocated prefix, inserting a fresh
            row when none exists.

            :param db_session: Active SQLAlchemy session.
            :param run_id: Run UUID.
            :param project_id: Owning project UUID.
            :param project_slug: Project slug (sanitized into the
                                 path).
            :param job_type: Job-type string (sanitized into the
                             path).
            :param now: Optional override for the allocation
                        timestamp.

            :returns: :class:`AllocatedResultPath`.
        """
        existing = repository.find_by_run(
            db_session=db_session, run_id=run_id,
        )
        if existing is not None:
            rtnval = _to_record(row=existing)
            return rtnval

        allocated_at = now
        if allocated_at is None:
            allocated_at = utc_now()
        prefix = build_canonical_prefix(
            project_slug=project_slug,
            job_type=job_type,
            run_id=run_id,
            when=allocated_at,
        )
        row = repository.insert_allocation(
            db_session=db_session,
            run_id=run_id,
            project_id=project_id,
            backend_driver=self._backend_driver,
            backend_key_prefix=prefix,
            allocated_at=allocated_at,
        )
        db_session.commit()
        rtnval = _to_record(row=row)
        return rtnval

    def resolve(
            self,
            *,
            db_session: DbSession,
            run_id: str
        ) -> AllocatedResultPath:
        """
            Look up an existing allocation. Used by the result
            watcher to find the prefix to poll.

            :param db_session: Active SQLAlchemy session.
            :param run_id: Run UUID.

            :returns: :class:`AllocatedResultPath`.
            :raises: AllocationNotFoundError when no row exists.
        """
        existing = repository.find_by_run(
            db_session=db_session, run_id=run_id,
        )
        if existing is None:
            err_lines = ["Shared-results allocation not found."]
            err_lines.append("RUN_ID: {}".format(run_id))
            err_msg = os.linesep.join(err_lines)
            raise AllocationNotFoundError(err_msg) from None
        rtnval = _to_record(row=existing)
        return rtnval

    def presign_put(
            self,
            *,
            run_id: str,
            version_prefix: str,
            relative_paths: List[str],
            signing_secret: bytes,
            now: Optional[datetime] = None,
            ttl_seconds: int = DEFAULT_PRESIGN_TTL_SECONDS
        ) -> List[ArtifactUploadTarget]:
        """
            Mint one short-lived presigned PUT target per relative
            artifact path, each scoped to the run.

            The dev / alpha deploy has no S3-compatible object
            store -- the result tree is a local filesystem subtree
            the result-ingest scanner reads verbatim. This method
            therefore delegates to the local-filesystem presign
            fallback: each minted URL points back at the service's
            own ``_local-upload`` endpoint and carries an
            HMAC-signed query string so object-store credentials
            never reach the client. When an operator later wires a
            real object store this seam dispatches to the driver's
            native presign instead; the HTTP surface does not
            change.

            The caller is responsible for verifying run ownership
            and accepting state *before* calling this method --
            ``presign_put`` only mints URLs.

            :param run_id: Run UUID.
            :param version_prefix: Versioned API prefix
                                   (``/api/v1``).
            :param relative_paths: Canonicalized relative artifact
                                   paths (see
                                   :func:`presign.validate_artifact_path_batch`).
            :param signing_secret: Server-held HMAC signing secret.
            :param now: Optional override for the current UTC time.
            :param ttl_seconds: Lifetime of the minted URLs.

            :returns: List of :class:`ArtifactUploadTarget`.
        """
        minted_now = now
        if minted_now is None:
            minted_now = utc_now()
        targets = mint_local_upload_targets(
            secret=signing_secret,
            run_id=run_id,
            version_prefix=version_prefix,
            relative_paths=relative_paths,
            now=minted_now,
            ttl_seconds=ttl_seconds,
        )
        rtnval = targets
        return rtnval


def _to_record(*, row) -> AllocatedResultPath:
    """
        Convert an ORM row to the read model.

        :param row: ``SharedResultsAllocation``.

        :returns: :class:`AllocatedResultPath`.
    """
    rtnval = AllocatedResultPath(
        run_id=str(row.run_id),
        project_id=str(row.project_id),
        backend_driver=row.backend_driver,
        backend_key_prefix=row.backend_key_prefix,
        allocated_at=row.allocated_at,
    )
    return rtnval
