"""
.. module:: orchestration.build.repository
    :synopsis: CRUD helpers for build-run rows.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.orchestration.build.models import (
    BuildRun,
    BuildRunState,
    BuildToolchainSnapshot,
)


def insert_build_run(
        *,
        db_session: DbSession,
        project_id: str,
        runner_kind: str,
        repro_digest_sha256: str,
        actor_id: Optional[str],
        pipeline_run_id: Optional[str],
        pipeline_step_run_id: Optional[str],
        inputs: Dict[str, Any],
        annotations: Dict[str, Any],
        started_at: Optional[datetime]
    ) -> BuildRun:
    row = BuildRun(
        run_id=new_uuid(),
        project_id=project_id,
        runner_kind=runner_kind,
        repro_digest_sha256=repro_digest_sha256,
        state=BuildRunState.PENDING,
        layer5_run_id=None,
        pipeline_run_id=pipeline_run_id,
        pipeline_step_run_id=pipeline_step_run_id,
        actor_id=actor_id,
        started_at=started_at,
        finished_at=None,
        final_state_reason="",
        inputs=dict(inputs),
        annotations=dict(annotations),
    )
    db_session.add(row)
    db_session.flush()
    return row


def insert_toolchain_snapshot_row(
        *,
        db_session: DbSession,
        run_id: str,
        toolchain_key: str,
        version: str,
        fingerprint_sha256: str
    ) -> BuildToolchainSnapshot:
    row = BuildToolchainSnapshot(
        run_id=run_id,
        toolchain_key=toolchain_key,
        version=version,
        fingerprint_sha256=fingerprint_sha256,
    )
    db_session.add(row)
    db_session.flush()
    return row


def find_run_by_id(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[BuildRun]:
    rtnval = (
        db_session.query(BuildRun)
        .filter(BuildRun.run_id == run_id)
        .first()
    )
    return rtnval


def list_toolchain_for_run(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[BuildToolchainSnapshot]:
    rows = (
        db_session.query(BuildToolchainSnapshot)
        .filter(BuildToolchainSnapshot.run_id == run_id)
        .order_by(BuildToolchainSnapshot.toolchain_key.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval


def list_runs_for_project(
        *,
        db_session: DbSession,
        project_id: str,
        limit: int
    ) -> List[BuildRun]:
    rows = (
        db_session.query(BuildRun)
        .filter(BuildRun.project_id == project_id)
        .order_by(BuildRun.started_at.desc())
        .limit(limit)
        .all()
    )
    rtnval = list(rows)
    return rtnval
