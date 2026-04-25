"""
.. module:: ingest.result.scanner
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: scan_once — single-pass result-tree ingest.

.. moduleauthor:: Automation Mojo LLC

The scanner is the M1 entry point that ties the
:class:`SharedResultsBackend`, the registered
:class:`ResultTreeParserProtocol`, the persistence layer, and the
in-process bus together.

Callers (M1 tests, M2 polling daemon) invoke :func:`scan_once`
with a ``run_id`` and a ``tree_path``. The scanner records a
:class:`ResultScanAttempt` row, parses the tree, persists summary
/ tasks / artifacts (idempotent against the unique keys), emits
``entity.result_tree.landed`` once + one
``entity.task_result.ingested`` per task + one
``entity.artifact.ingested`` per artifact, and returns a
:class:`ScanOutcome` with the observed counts.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.ingest.result import repositories
from automojo.pychestrate.webservice.ingest.result.errors import (
    ResultIngestError,
    ResultTreeNotFoundError,
)
from automojo.pychestrate.webservice.ingest.result.events import (
    ResultEventTopics,
)
from automojo.pychestrate.webservice.ingest.result.factories.parser_protocol import (
    ResultTreeParserProtocol,
)
from automojo.pychestrate.webservice.ingest.result.models import (
    ScanOutcomeStatus,
)
from automojo.pychestrate.webservice.jobs.run.state import Run
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


RESULT_TREE_PARSER_PROTOCOL: str = "result_tree_parser"


@dataclass(frozen=True)
class ScanOutcome:
    """
        Observed counters from one :func:`scan_once` call.

        :param run_id: Run UUID.
        :param status: ``"scanned"`` / ``"not_found"`` / ``"failed"``.
        :param parser_tag: Identifier of the parser that ran.
        :param files_seen: Total regular files walked.
        :param tasks_persisted: Number of task rows upserted.
        :param artifacts_persisted: Number of artifact rows upserted.
        :param had_summary: Whether a summary row was upserted.
    """
    run_id: str
    status: str
    parser_tag: str
    files_seen: int
    tasks_persisted: int
    artifacts_persisted: int
    had_summary: bool


def scan_once(
        *,
        db_session: DbSession,
        run_id: str,
        tree_path: str
    ) -> ScanOutcome:
    """
        Parse + persist + emit for one result tree.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID.
        :param tree_path: Filesystem path on the shared results
                          backend that contains the run's result
                          tree.

        :returns: :class:`ScanOutcome`.
        :raises: ResultIngestError on parser / persistence failure;
                 ResultTreeNotFoundError when ``tree_path`` does
                 not exist on disk.
    """
    started_at = utc_now()
    attempt = repositories.insert_scan_attempt(
        db_session=db_session,
        run_id=run_id,
        started_at=started_at,
    )

    if tree_path is None or len(tree_path) == 0 or os.path.isdir(tree_path) is False:
        repositories.finalize_scan_attempt(
            db_session=db_session,
            attempt=attempt,
            finished_at=utc_now(),
            status=ScanOutcomeStatus.NOT_FOUND,
            files_seen=0,
            artifacts_persisted=0,
            tasks_persisted=0,
            failure_reason="tree_path missing or not a directory",
        )
        db_session.commit()
        err_lines = ["Result tree not found on disk."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("PATH: {}".format(tree_path))
        err_msg = os.linesep.join(err_lines)
        raise ResultTreeNotFoundError(err_msg) from None

    parser = _resolve_parser()
    project_id = _project_id_for_run(db_session=db_session, run_id=run_id)

    try:
        parsed = parser.parse_tree(tree_path=tree_path)
    except Exception as xcpt:
        repositories.finalize_scan_attempt(
            db_session=db_session,
            attempt=attempt,
            finished_at=utc_now(),
            status=ScanOutcomeStatus.FAILED,
            files_seen=0,
            artifacts_persisted=0,
            tasks_persisted=0,
            failure_reason="parser raised: {}".format(str(xcpt)),
        )
        db_session.commit()
        err_lines = ["Result-tree parser raised."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("PARSER: {}".format(parser.parser_tag()))
        err_lines.append("REASON: {}".format(str(xcpt)))
        err_msg = os.linesep.join(err_lines)
        raise ResultIngestError(err_msg) from xcpt

    ingested_at = utc_now()
    had_summary = False
    if parsed.summary is not None:
        repositories.upsert_summary(
            db_session=db_session,
            run_id=run_id,
            project_id=project_id,
            parser_tag=parser.parser_tag(),
            summary=parsed.summary,
            ingested_at=ingested_at,
        )
        had_summary = True

    tasks_persisted = 0
    for task in parsed.tasks:
        repositories.upsert_task_result(
            db_session=db_session,
            run_id=run_id,
            project_id=project_id,
            task=task,
            ingested_at=ingested_at,
        )
        tasks_persisted = tasks_persisted + 1
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ResultEventTopics.TASK_RESULT_INGESTED,
                payload={
                    "run_id": run_id,
                    "project_id": project_id,
                    "instance_uuid": task.instance_uuid,
                    "test_name": task.test_name,
                    "result": task.result,
                },
                source_event_id=new_uuid(),
            ),
        )

    artifacts_persisted = 0
    for artifact in parsed.artifacts:
        repositories.upsert_artifact(
            db_session=db_session,
            run_id=run_id,
            project_id=project_id,
            artifact=artifact,
            ingested_at=ingested_at,
        )
        artifacts_persisted = artifacts_persisted + 1
        enqueue_event(
            db_session=db_session,
            event=EntityEvent(
                topic=ResultEventTopics.ARTIFACT_INGESTED,
                payload={
                    "run_id": run_id,
                    "project_id": project_id,
                    "relative_path": artifact.relative_path,
                    "classification": artifact.classification,
                    "size_bytes": artifact.size_bytes,
                    "content_type": artifact.content_type,
                },
                source_event_id=new_uuid(),
            ),
        )

    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ResultEventTopics.TREE_LANDED,
            payload={
                "run_id": run_id,
                "project_id": project_id,
                "tree_path": tree_path,
                "parser_tag": parser.parser_tag(),
                "files_seen": parsed.files_seen,
                "tasks_persisted": tasks_persisted,
                "artifacts_persisted": artifacts_persisted,
                "had_summary": had_summary,
                "ingested_at": ingested_at.isoformat(),
            },
            source_event_id=new_uuid(),
        ),
    )

    repositories.finalize_scan_attempt(
        db_session=db_session,
        attempt=attempt,
        finished_at=utc_now(),
        status=ScanOutcomeStatus.SCANNED,
        files_seen=parsed.files_seen,
        artifacts_persisted=artifacts_persisted,
        tasks_persisted=tasks_persisted,
        failure_reason=None,
    )
    db_session.commit()

    rtnval = ScanOutcome(
        run_id=run_id,
        status=ScanOutcomeStatus.SCANNED.value,
        parser_tag=parser.parser_tag(),
        files_seen=parsed.files_seen,
        tasks_persisted=tasks_persisted,
        artifacts_persisted=artifacts_persisted,
        had_summary=had_summary,
    )
    return rtnval


def _resolve_parser():
    """
        Return the highest-precedence registered parser or raise
        :class:`ResultIngestError`.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=RESULT_TREE_PARSER_PROTOCOL,
    )
    if len(candidates) == 0:
        err_lines = ["No result_tree_parser implementation registered."]
        err_lines.append("HINT: call ingest.result.register_builtin_extensions().")
        err_msg = os.linesep.join(err_lines)
        raise ResultIngestError(err_msg) from None
    rtnval = candidates[0]
    return rtnval


def _project_id_for_run(*, db_session: DbSession, run_id: str) -> str:
    """
        Look up the project id from the run row. The result
        watcher cannot proceed without a registered run.
    """
    row = db_session.query(Run).filter(Run.run_id == run_id).first()
    if row is None:
        err_lines = ["Cannot scan result tree — run row not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise ResultIngestError(err_msg) from None
    rtnval = str(row.project_id)
    return rtnval
