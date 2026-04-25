"""
.. module:: ingest.progress.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ProgressIngestService — auth + parse + persist + emit.

.. moduleauthor:: Automation Mojo LLC

The service is the single point that turns inbound JSON bodies
(from the REST receiver in :mod:`.routes`, M2 scope) into
persisted rows + bus events. M1 exposes service-level functions
the REST layer will call once routes land.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime
from typing import Any, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from automojo.pychestrate.webservice.ingest.progress import repositories
from automojo.pychestrate.webservice.ingest.progress.errors import (
    ProgressClientMismatchError,
    ProgressFormatError,
    ProgressUnknownRunError,
)
from automojo.pychestrate.webservice.ingest.progress.events import (
    ProgressEventTopics,
)
from automojo.pychestrate.webservice.ingest.progress.factories.parser_protocol import (
    ProgressParserProtocol,
)
from automojo.pychestrate.webservice.ingest.progress.schema import (
    ProgressRecord,
    ProgressSummary,
)
from automojo.pychestrate.webservice.jobs.dispatch.receipt import (
    lookup_by_run as lookup_receipt_by_run,
)
from automojo.pychestrate.webservice.jobs.run.state import (
    Run,
)
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent
from automojo.pychestrate.webservice.messaging.outbox import enqueue_event


PROGRESS_PARSER_PROTOCOL: str = "progress_parser"


def ingest_summary(
        *,
        db_session: DbSession,
        run_id: str,
        authenticated_client_id: str,
        format_tag: str,
        payload: Mapping[str, Any]
    ) -> ProgressSummary:
    """
        Authenticate, parse, persist, and emit a forwarded
        progress summary.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the URL path.
        :param authenticated_client_id: Client UUID derived from
                                        the transport's
                                        authenticated identity.
        :param format_tag: Inbound payload's ``format_tag`` field
                           — selects the parser.
        :param payload: Decoded JSON dict.

        :returns: The canonical :class:`ProgressSummary` derived
                  from the payload.
        :raises: ProgressUnknownRunError, ProgressClientMismatchError,
                 ProgressFormatError.
    """
    _assert_run_belongs_to_client(
        db_session=db_session,
        run_id=run_id,
        client_id=authenticated_client_id,
    )
    parser = _resolve_parser(format_tag=format_tag)
    summary = parser.parse_summary(
        run_id=run_id,
        client_id=authenticated_client_id,
        payload=payload,
    )

    received_at = utc_now()
    repositories.insert_summary(
        db_session=db_session,
        summary=summary,
        received_at=received_at,
    )

    project_id = _project_id_for_run(db_session=db_session, run_id=run_id)
    repositories.upsert_counters_from_summary(
        db_session=db_session,
        run_id=run_id,
        project_id=project_id,
        summary=summary,
        last_summary_at=received_at,
    )

    event_payload = {
        "run_id": run_id,
        "project_id": project_id,
        "client_id": authenticated_client_id,
        "format_tag": summary.format_tag,
        "tests_total": summary.tests_total,
        "tests_passed": summary.tests_passed,
        "tests_failed": summary.tests_failed,
        "tests_skipped": summary.tests_skipped,
        "tests_errored": summary.tests_errored,
        "percent_complete": summary.percent_complete,
        "received_at": received_at.isoformat(),
    }
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ProgressEventTopics.RECEIVED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ProgressEventTopics.SUMMARY_LANDED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    return summary


def ingest_record(
        *,
        db_session: DbSession,
        run_id: str,
        authenticated_client_id: str,
        record_index: int,
        format_tag: str,
        payload: Mapping[str, Any]
    ) -> ProgressRecord:
    """
        Persist one progress record. Idempotent on
        ``(run_id, record_index)`` — re-posting the same record
        is a no-op.
    """
    _assert_run_belongs_to_client(
        db_session=db_session,
        run_id=run_id,
        client_id=authenticated_client_id,
    )
    parser = _resolve_parser(format_tag=format_tag)
    record = parser.parse_record(
        run_id=run_id,
        client_id=authenticated_client_id,
        record_index=record_index,
        payload=payload,
    )

    existing = repositories.find_record(
        db_session=db_session, run_id=run_id, record_index=record_index,
    )
    if existing is not None:
        rtnval = record
        return rtnval

    received_at = utc_now()
    repositories.insert_record(
        db_session=db_session,
        record=record,
        received_at=received_at,
    )
    project_id = _project_id_for_run(db_session=db_session, run_id=run_id)
    enqueue_event(
        db_session=db_session,
        event=EntityEvent(
            topic=ProgressEventTopics.RECORD_INGESTED,
            payload={
                "run_id": run_id,
                "project_id": project_id,
                "client_id": authenticated_client_id,
                "record_index": record_index,
                "test_name": record.test_name,
                "result": record.result,
            },
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = record
    return rtnval


def get_summary(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[ProgressSummary]:
    """
        Return the latest persisted summary for ``run_id``, or
        ``None`` when none has landed.
    """
    row = repositories.latest_summary(db_session=db_session, run_id=run_id)
    if row is None:
        return None
    rtnval = ProgressSummary(
        run_id=str(row.run_id),
        client_id=str(row.client_id),
        format_tag=row.format_tag,
        tests_total=row.tests_total,
        tests_passed=row.tests_passed,
        tests_failed=row.tests_failed,
        tests_skipped=row.tests_skipped,
        tests_errored=row.tests_errored,
        percent_complete=row.percent_complete,
        notes=row.notes,
        recorded_at=row.recorded_at,
        raw=dict(row.raw_payload or {}),
    )
    return rtnval


def list_records(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[ProgressRecord]:
    """
        Return every persisted record for ``run_id`` ordered by
        index.
    """
    rows = repositories.list_records(db_session=db_session, run_id=run_id)
    rtnval: List[ProgressRecord] = []
    for row in rows:
        rtnval.append(
            ProgressRecord(
                run_id=str(row.run_id),
                client_id=str(row.client_id),
                record_index=row.record_index,
                test_name=row.test_name,
                result=row.result,
                started_at=row.started_at,
                finished_at=row.finished_at,
                duration_seconds=row.duration_seconds,
                raw=dict(row.raw_payload or {}),
            )
        )
    return rtnval


def _assert_run_belongs_to_client(
        *,
        db_session: DbSession,
        run_id: str,
        client_id: str
    ) -> None:
    """
        Verify the run exists AND was dispatched to the
        authenticated client. The check uses the dispatch receipt
        as authoritative — only the client that owns the receipt
        for the run may post progress for it.

        :raises: ProgressUnknownRunError when the run row or its
                 receipt is missing;
                 ProgressClientMismatchError when the receipt's
                 ``client_id`` differs.
    """
    receipt = lookup_receipt_by_run(db_session=db_session, run_id=run_id)
    if receipt is None:
        err_lines = ["Cannot ingest progress — no dispatch receipt recorded for run."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise ProgressUnknownRunError(err_msg) from None
    if receipt.client_id != client_id:
        err_lines = ["Cannot ingest progress — authenticated client does not own the run."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_lines.append("EXPECTED_CLIENT: {}".format(receipt.client_id))
        err_lines.append("AUTHENTICATED_CLIENT: {}".format(client_id))
        err_msg = os.linesep.join(err_lines)
        raise ProgressClientMismatchError(err_msg) from None
    return


def _project_id_for_run(*, db_session: DbSession, run_id: str) -> str:
    """
        Look up the project id from the run row.

        :raises: ProgressUnknownRunError when the run row does not
                 exist.
    """
    row = db_session.query(Run).filter(Run.run_id == run_id).first()
    if row is None:
        err_lines = ["Cannot ingest progress — run row not found."]
        err_lines.append("RUN_ID: {}".format(run_id))
        err_msg = os.linesep.join(err_lines)
        raise ProgressUnknownRunError(err_msg) from None
    rtnval = str(row.project_id)
    return rtnval


def _resolve_parser(*, format_tag: str):
    """
        Find a registered parser whose ``format_tag()`` matches.
        Raises :class:`ProgressFormatError` when no parser
        matches.
    """
    candidates = list_factory_implementations(
        factory_protocol_name=PROGRESS_PARSER_PROTOCOL,
    )
    for impl in candidates:
        try:
            if impl.format_tag() == format_tag:
                return impl
        except NotImplementedError:
            continue
    err_lines = ["No progress_parser registered for the supplied format_tag."]
    err_lines.append("FORMAT_TAG: {}".format(format_tag))
    err_lines.append("REGISTERED: ({})".format(len(candidates)))
    err_msg = os.linesep.join(err_lines)
    raise ProgressFormatError(err_msg) from None
