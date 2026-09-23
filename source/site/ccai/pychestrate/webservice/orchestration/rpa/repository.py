"""
.. module:: orchestration.rpa.repository
    :synopsis: CRUD helpers for the RPA-orchestration rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.orchestration.rpa.models import (
    RpaJob,
    RpaJobStatus,
    RpaJobType,
    RpaJobTypeState,
    RpaJobTypeVersion,
    RpaSpec,
    RpaSpecRevision,
    RpaVersionState,
)


# ---------------------------------------------------------------------------
# Job types
# ---------------------------------------------------------------------------


def find_job_type(*, db_session: DbSession, type_id: str) -> Optional[RpaJobType]:
    rtnval = (
        db_session.query(RpaJobType)
        .filter(RpaJobType.type_id == type_id)
        .first()
    )
    return rtnval


def list_job_types(
        *,
        db_session: DbSession,
        state: Optional[RpaJobTypeState] = None
    ) -> List[RpaJobType]:
    query = db_session.query(RpaJobType)
    if state is not None:
        query = query.filter(RpaJobType.state == state)
    rows = query.order_by(RpaJobType.type_id.asc()).all()
    rtnval = list(rows)
    return rtnval


def insert_job_type(
        *,
        db_session: DbSession,
        type_id: str,
        display_name: str,
        description: str,
        execution_mode: Any,
        capability_requirements: List[str],
        packet_schema: Optional[Dict[str, Any]],
        secret_fields: List[str],
        created_by_id: Optional[str]
    ) -> RpaJobType:
    now = utc_now()
    row = RpaJobType(
        type_id=type_id,
        display_name=display_name,
        description=description,
        execution_mode=execution_mode,
        capability_requirements=list(capability_requirements),
        packet_schema=packet_schema,
        secret_fields=list(secret_fields),
        state=RpaJobTypeState.ACTIVE,
        created_by_id=created_by_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.flush()
    return row


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


def list_versions(
        *,
        db_session: DbSession,
        type_id: str,
        state: Optional[RpaVersionState] = None
    ) -> List[RpaJobTypeVersion]:
    query = db_session.query(RpaJobTypeVersion).filter(
        RpaJobTypeVersion.type_id == type_id,
    )
    if state is not None:
        query = query.filter(RpaJobTypeVersion.state == state)
    rows = query.order_by(RpaJobTypeVersion.published_at.desc()).all()
    rtnval = list(rows)
    return rtnval


def find_version(
        *,
        db_session: DbSession,
        type_id: str,
        version: str
    ) -> Optional[RpaJobTypeVersion]:
    rtnval = (
        db_session.query(RpaJobTypeVersion)
        .filter(RpaJobTypeVersion.type_id == type_id)
        .filter(RpaJobTypeVersion.version == version)
        .first()
    )
    return rtnval


def insert_version(
        *,
        db_session: DbSession,
        type_id: str,
        version: str,
        source_kind: Any,
        source_ref: str,
        entrypoint: Dict[str, Any],
        environment: Dict[str, str],
        timeout_minutes: int,
        published_by_id: Optional[str]
    ) -> RpaJobTypeVersion:
    row = RpaJobTypeVersion(
        version_id=new_uuid(),
        type_id=type_id,
        version=version,
        source_kind=source_kind,
        source_ref=source_ref,
        entrypoint=dict(entrypoint),
        environment=dict(environment),
        timeout_minutes=timeout_minutes,
        state=RpaVersionState.ACTIVE,
        published_by_id=published_by_id,
        published_at=utc_now(),
    )
    db_session.add(row)
    db_session.flush()
    return row


# ---------------------------------------------------------------------------
# Specifications
# ---------------------------------------------------------------------------


def find_spec(*, db_session: DbSession, spec_id: str) -> Optional[RpaSpec]:
    rtnval = (
        db_session.query(RpaSpec)
        .filter(RpaSpec.spec_id == spec_id)
        .first()
    )
    return rtnval


def find_spec_by_name(
        *,
        db_session: DbSession,
        project_id: str,
        name: str
    ) -> Optional[RpaSpec]:
    rtnval = (
        db_session.query(RpaSpec)
        .filter(RpaSpec.project_id == project_id)
        .filter(RpaSpec.name == name)
        .first()
    )
    return rtnval


def list_specs(
        *,
        db_session: DbSession,
        project_id: str,
        offset: int = 0,
        limit: int = 100
    ) -> List[RpaSpec]:
    rows = (
        db_session.query(RpaSpec)
        .filter(RpaSpec.project_id == project_id)
        .order_by(RpaSpec.name.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def count_specs(*, db_session: DbSession, project_id: str) -> int:
    rtnval = (
        db_session.query(RpaSpec)
        .filter(RpaSpec.project_id == project_id)
        .count()
    )
    return rtnval


def list_specs_for_type(*, db_session: DbSession, type_id: str) -> List[RpaSpec]:
    rows = (
        db_session.query(RpaSpec)
        .filter(RpaSpec.type_id == type_id)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def insert_spec(
        *,
        db_session: DbSession,
        project_id: str,
        name: str,
        type_id: str,
        version_selector: str,
        default_packet: Dict[str, Any],
        target_pod_id: Optional[str],
        required_capabilities: List[str],
        timeout_minutes: Optional[int],
        description: str,
        created_by_id: Optional[str]
    ) -> RpaSpec:
    now = utc_now()
    row = RpaSpec(
        spec_id=new_uuid(),
        project_id=project_id,
        name=name,
        type_id=type_id,
        version_selector=version_selector,
        default_packet=dict(default_packet),
        target_pod_id=target_pod_id,
        required_capabilities=list(required_capabilities),
        timeout_minutes=timeout_minutes,
        description=description,
        revision=1,
        created_by_id=created_by_id,
        created_at=now,
        updated_at=now,
    )
    db_session.add(row)
    db_session.flush()
    return row


def insert_spec_revision(
        *,
        db_session: DbSession,
        spec_id: str,
        revision: int,
        snapshot: Dict[str, Any]
    ) -> RpaSpecRevision:
    row = RpaSpecRevision(
        revision_id=new_uuid(),
        spec_id=spec_id,
        revision=revision,
        snapshot=dict(snapshot),
        created_at=utc_now(),
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_spec_revision(
        *,
        db_session: DbSession,
        spec_id: str,
        revision: int
    ) -> Optional[RpaSpecRevision]:
    rtnval = (
        db_session.query(RpaSpecRevision)
        .filter(RpaSpecRevision.spec_id == spec_id)
        .filter(RpaSpecRevision.revision == revision)
        .first()
    )
    return rtnval


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------


def find_job(*, db_session: DbSession, job_id: str) -> Optional[RpaJob]:
    rtnval = (
        db_session.query(RpaJob)
        .filter(RpaJob.job_id == job_id)
        .first()
    )
    return rtnval


def find_recent_job_by_idempotency_key(
        *,
        db_session: DbSession,
        idempotency_key: str,
        not_before: datetime
    ) -> Optional[RpaJob]:
    rtnval = (
        db_session.query(RpaJob)
        .filter(RpaJob.idempotency_key == idempotency_key)
        .filter(RpaJob.created_at >= not_before)
        .order_by(RpaJob.created_at.desc())
        .first()
    )
    return rtnval


def insert_job(
        *,
        db_session: DbSession,
        job_id: str,
        project_id: str,
        spec_id: Optional[str],
        spec_name: str,
        spec_revision: int,
        type_id: str,
        resolved_version: str,
        execution_mode: Any,
        work_packet: Dict[str, Any],
        packet_digest: str,
        triggered_by_id: Optional[str],
        trigger_cause: Dict[str, Any],
        idempotency_key: str
    ) -> RpaJob:
    row = RpaJob(
        job_id=job_id,
        project_id=project_id,
        spec_id=spec_id,
        spec_name=spec_name,
        spec_revision=spec_revision,
        type_id=type_id,
        resolved_version=resolved_version,
        execution_mode=execution_mode,
        work_packet=dict(work_packet),
        packet_digest=packet_digest,
        status=RpaJobStatus.PENDING,
        exit_code=None,
        triggered_by_id=triggered_by_id,
        trigger_cause=dict(trigger_cause),
        idempotency_key=idempotency_key,
        final_state_reason="",
        created_at=utc_now(),
    )
    db_session.add(row)
    db_session.flush()
    return row


def query_jobs(
        *,
        db_session: DbSession,
        project_id: Optional[str],
        spec_id: Optional[str] = None,
        status: Optional[RpaJobStatus] = None
    ):
    query = db_session.query(RpaJob)
    if project_id is not None:
        query = query.filter(RpaJob.project_id == project_id)
    if spec_id is not None:
        query = query.filter(RpaJob.spec_id == spec_id)
    if status is not None:
        query = query.filter(RpaJob.status == status)
    return query


def list_jobs(
        *,
        db_session: DbSession,
        project_id: Optional[str],
        spec_id: Optional[str] = None,
        status: Optional[RpaJobStatus] = None,
        offset: int = 0,
        limit: int = 50
    ) -> List[RpaJob]:
    query = query_jobs(
        db_session=db_session, project_id=project_id, spec_id=spec_id, status=status,
    )
    rows = query.order_by(RpaJob.created_at.desc()).offset(offset).limit(limit).all()
    rtnval = list(rows)
    return rtnval


def count_jobs(
        *,
        db_session: DbSession,
        project_id: Optional[str],
        spec_id: Optional[str] = None,
        status: Optional[RpaJobStatus] = None
    ) -> int:
    query = query_jobs(
        db_session=db_session, project_id=project_id, spec_id=spec_id, status=status,
    )
    rtnval = query.count()
    return rtnval


def count_active_jobs_for_spec(*, db_session: DbSession, spec_id: str) -> int:
    rtnval = (
        db_session.query(RpaJob)
        .filter(RpaJob.spec_id == spec_id)
        .filter(RpaJob.status.in_([
            RpaJobStatus.PENDING, RpaJobStatus.DISPATCHING, RpaJobStatus.RUNNING,
        ]))
        .count()
    )
    return rtnval


# ---------------------------------------------------------------------------
# Project deletion (PRJ-19)
# ---------------------------------------------------------------------------


def count_active_jobs_for_project(*, db_session: DbSession, project_id: str) -> int:
    """
        Count the project's RPA jobs that are still pending, dispatching
        or running.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Project reference as stored on the rows.

        :returns: Number of active jobs.
    """
    rtnval = (
        db_session.query(RpaJob)
        .filter(RpaJob.project_id == str(project_id))
        .filter(RpaJob.status.in_([
            RpaJobStatus.PENDING, RpaJobStatus.DISPATCHING, RpaJobStatus.RUNNING,
        ]))
        .count()
    )
    return rtnval


def delete_project_rows(*, db_session: DbSession, project_id: str) -> Dict[str, int]:
    """
        Delete every RPA job, specification and specification revision
        that belongs to a project, so a deleted project leaves nothing
        behind for a later project to inherit. Rows are removed child
        first and explicitly (revisions do not rely on the database's
        ``ON DELETE CASCADE``, which SQLite does not enforce by default).
        Does not commit: the caller deletes the project in the same
        transaction.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Project reference as stored on the rows.

        :returns: Counts of deleted ``jobs``, ``revisions`` and ``specs``.
    """
    project_ref = str(project_id)
    spec_ids = [
        row[0]
        for row in db_session.query(RpaSpec.spec_id).filter(RpaSpec.project_id == project_ref).all()
    ]

    jobs_deleted = (
        db_session.query(RpaJob)
        .filter(RpaJob.project_id == project_ref)
        .delete(synchronize_session=False)
    )
    revisions_deleted = 0
    if len(spec_ids) > 0:
        revisions_deleted = (
            db_session.query(RpaSpecRevision)
            .filter(RpaSpecRevision.spec_id.in_(spec_ids))
            .delete(synchronize_session=False)
        )
    specs_deleted = (
        db_session.query(RpaSpec)
        .filter(RpaSpec.project_id == project_ref)
        .delete(synchronize_session=False)
    )
    rtnval = {
        "jobs": int(jobs_deleted),
        "revisions": int(revisions_deleted),
        "specs": int(specs_deleted),
    }
    return rtnval
