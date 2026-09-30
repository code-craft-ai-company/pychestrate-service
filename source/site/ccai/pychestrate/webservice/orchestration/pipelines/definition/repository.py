"""
.. module:: orchestration.pipelines.definition.repository
    :synopsis: CRUD helpers for pipeline-run rows.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.pychestrate.core.defaults import new_uuid

from ccai.pychestrate.webservice.orchestration.pipelines.definition.models import (
    PipelineDocumentCache,
    PipelineRun,
    PipelineRunState,
    PipelineStageRun,
    PipelineStepRun,
    StageState,
    StepState,
    TriggerCause,
)


def insert_pipeline_run(
        *,
        db_session: DbSession,
        project_id: str,
        commit_sha: str,
        ref: str,
        filename: str,
        pipeline_digest_sha256: str,
        trigger_cause: TriggerCause,
        actor_id: Optional[str],
        started_at: Optional[datetime]
    ) -> PipelineRun:
    row = PipelineRun(
        run_id=new_uuid(),
        project_id=project_id,
        commit_sha=commit_sha,
        ref=ref,
        filename=filename,
        pipeline_digest_sha256=pipeline_digest_sha256,
        state=PipelineRunState.PENDING,
        trigger_cause=trigger_cause,
        actor_id=actor_id,
        started_at=started_at,
        finished_at=None,
        final_state_reason="",
    )
    db_session.add(row)
    db_session.flush()
    return row


def insert_stage_run(
        *,
        db_session: DbSession,
        run_id: str,
        stage_id: str,
        stage_index: int,
        when_clause: str,
        needs_csv: str
    ) -> PipelineStageRun:
    row = PipelineStageRun(
        stage_run_id=new_uuid(),
        run_id=run_id,
        stage_id=stage_id,
        stage_index=stage_index,
        state=StageState.PENDING,
        when_clause=when_clause,
        when_clause_resolved="",
        needs_csv=needs_csv,
        started_at=None,
        finished_at=None,
        final_state_reason="",
    )
    db_session.add(row)
    db_session.flush()
    return row


def insert_step_run(
        *,
        db_session: DbSession,
        stage_run_id: str,
        step_id: str,
        step_index: int,
        kind_name: str,
        job_kind: str,
        inputs: Dict[str, Any]
    ) -> PipelineStepRun:
    row = PipelineStepRun(
        step_run_id=new_uuid(),
        stage_run_id=stage_run_id,
        step_id=step_id,
        step_index=step_index,
        kind_name=kind_name,
        job_kind=job_kind,
        layer5_run_id=None,
        state=StepState.PENDING,
        attempt=0,
        inputs=dict(inputs),
        started_at=None,
        finished_at=None,
        final_state_reason="",
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_run_by_id(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[PipelineRun]:
    rtnval = (
        db_session.query(PipelineRun)
        .filter(PipelineRun.run_id == run_id)
        .first()
    )
    return rtnval


def list_runs_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        limit: int
    ) -> List[PipelineRun]:
    """
        List pipeline runs for a project, newest-started first.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.
        :param limit: Maximum number of rows to return.

        :returns: List of :class:`PipelineRun` rows.
    """
    rows = (
        db_session.query(PipelineRun)
        .filter(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.started_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def find_step_run_by_id(
        *,
        db_session: DbSession,
        step_run_id: str
    ) -> Optional[PipelineStepRun]:
    rtnval = (
        db_session.query(PipelineStepRun)
        .filter(PipelineStepRun.step_run_id == step_run_id)
        .first()
    )
    return rtnval


def find_stage_run_by_id(
        *,
        db_session: DbSession,
        stage_run_id: str
    ) -> Optional[PipelineStageRun]:
    rtnval = (
        db_session.query(PipelineStageRun)
        .filter(PipelineStageRun.stage_run_id == stage_run_id)
        .first()
    )
    return rtnval


def list_stages_for_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[PipelineStageRun]:
    rows = (
        db_session.query(PipelineStageRun)
        .filter(PipelineStageRun.run_id == run_id)
        .order_by(PipelineStageRun.stage_index.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_steps_for_stage(
        *,
        db_session: DbSession,
        stage_run_id: str
    ) -> List[PipelineStepRun]:
    rows = (
        db_session.query(PipelineStepRun)
        .filter(PipelineStepRun.stage_run_id == stage_run_id)
        .order_by(PipelineStepRun.step_index.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def upsert_document_cache(
        *,
        db_session: DbSession,
        project_id: str,
        commit_sha: str,
        filename: str,
        pipeline_digest_sha256: str,
        canonical_json: str,
        cached_at: datetime
    ) -> PipelineDocumentCache:
    row = (
        db_session.query(PipelineDocumentCache)
        .filter(PipelineDocumentCache.project_id == project_id)
        .filter(PipelineDocumentCache.commit_sha == commit_sha)
        .filter(PipelineDocumentCache.filename == filename)
        .first()
    )
    if row is None:
        row = PipelineDocumentCache(
            project_id=project_id,
            commit_sha=commit_sha,
            filename=filename,
            pipeline_digest_sha256=pipeline_digest_sha256,
            canonical_json=canonical_json,
            cached_at=cached_at,
        )
        db_session.add(row)
    else:
        row.pipeline_digest_sha256 = pipeline_digest_sha256
        row.canonical_json = canonical_json
        row.cached_at = cached_at
    db_session.flush()
    return row


def find_document_cache(
        *,
        db_session: DbSession,
        project_id: str,
        commit_sha: str,
        filename: str
    ) -> Optional[PipelineDocumentCache]:
    rtnval = (
        db_session.query(PipelineDocumentCache)
        .filter(PipelineDocumentCache.project_id == project_id)
        .filter(PipelineDocumentCache.commit_sha == commit_sha)
        .filter(PipelineDocumentCache.filename == filename)
        .first()
    )
    return rtnval


def list_document_cache_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        limit: int
    ) -> List[PipelineDocumentCache]:
    """
        Return cached pipeline-definition documents for a project,
        newest-cached first, capped at ``limit`` rows.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.
        :param limit: Maximum number of rows to return.

        :returns: List of :class:`PipelineDocumentCache` rows.
    """
    rows = (
        db_session.query(PipelineDocumentCache)
        .filter(PipelineDocumentCache.project_id == project_id)
        .order_by(PipelineDocumentCache.cached_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval


def delete_document_cache(
        *,
        db_session: DbSession,
        project_id: str,
        commit_sha: str,
        filename: str
    ) -> bool:
    """
        Delete a cached pipeline-definition document keyed by
        ``(project_id, commit_sha, filename)``.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.
        :param commit_sha: Commit SHA component of the cache key.
        :param filename: Filename component of the cache key.

        :returns: True when a row was deleted, False on a miss.
    """
    row = (
        db_session.query(PipelineDocumentCache)
        .filter(PipelineDocumentCache.project_id == project_id)
        .filter(PipelineDocumentCache.commit_sha == commit_sha)
        .filter(PipelineDocumentCache.filename == filename)
        .first()
    )
    if row is None:
        rtnval = False
        return rtnval
    db_session.delete(row)
    db_session.flush()
    rtnval = True
    return rtnval


def delete_document_cache_by_digest(
        *,
        db_session: DbSession,
        project_id: str,
        pipeline_digest_sha256: str
    ) -> int:
    """
        Delete every cached copy of a pipeline definition: the same document saved
        from several commits or files is one pipeline (its id is the digest), so
        deleting the pipeline removes them all.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.
        :param pipeline_digest_sha256: Canonical-document SHA-256.

        :returns: How many cache rows were deleted.
    """
    rows = (
        db_session.query(PipelineDocumentCache)
        .filter(PipelineDocumentCache.project_id == project_id)
        .filter(PipelineDocumentCache.pipeline_digest_sha256 == pipeline_digest_sha256)
        .all()
    )
    for row in rows:
        db_session.delete(row)
    db_session.flush()
    rtnval = len(rows)
    return rtnval


def find_document_cache_by_digest(
        *,
        db_session: DbSession,
        project_id: str,
        pipeline_digest_sha256: str
    ) -> Optional[PipelineDocumentCache]:
    """
        Locate a cached pipeline-definition document for a project
        by its canonical-document digest. The digest is the stable
        ``pipeline_id`` exposed over the REST surface.

        :param db_session: Active SQLAlchemy session.
        :param project_id: Owning project UUID.
        :param pipeline_digest_sha256: Canonical-document SHA-256.

        :returns: Matching row or ``None``.
    """
    rtnval = (
        db_session.query(PipelineDocumentCache)
        .filter(PipelineDocumentCache.project_id == project_id)
        .filter(
            PipelineDocumentCache.pipeline_digest_sha256
            == pipeline_digest_sha256
        )
        .order_by(PipelineDocumentCache.cached_at.desc())
        .first()
    )
    return rtnval
