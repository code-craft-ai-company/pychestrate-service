"""
.. module:: ingest.progress.service
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: ProgressIngestService — auth + parse + persist + emit.

.. moduleauthor:: Code Craft AI LLC

The service is the single point that turns inbound JSON bodies
(from the REST receiver in :mod:`.routes`, M2 scope) into
persisted rows + bus events. M1 exposes service-level functions
the REST layer will call once routes land.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from datetime import datetime, timezone
from typing import Any, List, Mapping, Optional

from sqlalchemy.orm import Session as DbSession

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.core.defaults import new_uuid, utc_now

from ccai.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)
from ccai.pychestrate.webservice.ingest.progress import repositories
from ccai.pychestrate.webservice.ingest.progress.errors import (
    ProgressClientMismatchError,
    ProgressFormatError,
    ProgressUnknownRunError,
)
from ccai.pychestrate.webservice.ingest.progress.events import (
    ProgressEventTopics,
)
from ccai.pychestrate.webservice.ingest.progress.factories.parser_protocol import (
    ProgressParserProtocol,
)
from ccai.pychestrate.webservice.ingest.progress.schema import (
    SUPPORTED_FRAME_KINDS,
    FRAME_KIND_TEST,
    ProgressFrameEnvelope,
    ProgressRecord,
    ProgressSummary,
)
from ccai.pychestrate.webservice.jobs.dispatch.receipt import (
    lookup_by_run as lookup_receipt_by_run,
)
from ccai.pychestrate.webservice.jobs.run.state import (
    Run,
)
from ccai.pychestrate.webservice.messaging.event_bus import EntityEvent
from ccai.pychestrate.webservice.messaging.outbox import enqueue_event


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


def ingest_frame(
        *,
        db_session: DbSession,
        run_id: str,
        authenticated_client_id: str,
        frame_kind: str,
        frame_index: int,
        payload: Mapping[str, Any]
    ) -> ProgressFrameEnvelope:
    """
        Authenticate, parse, persist, and emit one generalized
        ``build`` / ``provision`` progress frame.

        Build and provision runs are not test-shaped — they have
        no per-test pass/fail tally — so they do not flow through
        the testbase parser. The frame is structurally parsed
        directly here: phase / status / percent_complete are
        lifted from the payload and the whole payload is kept as a
        verbatim ``raw_payload`` passthrough. Idempotent on
        ``(run_id, frame_kind, frame_index)`` — re-posting the
        same frame is a no-op.

        :param db_session: Active SQLAlchemy session.
        :param run_id: Run UUID from the URL path.
        :param authenticated_client_id: Client UUID derived from
                                        the transport's
                                        authenticated identity.
        :param frame_kind: ``"build"`` or ``"provision"``.
        :param frame_index: Monotonically-increasing frame index
                            inside the run's stream.
        :param payload: Decoded JSON dict for the frame.

        :returns: The canonical :class:`ProgressFrameEnvelope`.
        :raises: ProgressUnknownRunError, ProgressClientMismatchError,
                 ProgressFormatError.
    """
    if frame_kind not in SUPPORTED_FRAME_KINDS or frame_kind == FRAME_KIND_TEST:
        err_lines = ["Cannot ingest progress frame — unsupported frame_kind."]
        err_lines.append("FRAME_KIND: {}".format(frame_kind))
        err_lines.append("SUPPORTED: build, provision")
        err_msg = os.linesep.join(err_lines)
        raise ProgressFormatError(err_msg) from None

    _assert_run_belongs_to_client(
        db_session=db_session,
        run_id=run_id,
        client_id=authenticated_client_id,
    )

    frame = _parse_frame(
        run_id=run_id,
        client_id=authenticated_client_id,
        frame_kind=frame_kind,
        frame_index=frame_index,
        payload=payload,
    )

    existing = repositories.find_frame(
        db_session=db_session,
        run_id=run_id,
        frame_kind=frame_kind,
        frame_index=frame_index,
    )
    if existing is not None:
        rtnval = frame
        return rtnval

    received_at = utc_now()
    repositories.insert_frame(
        db_session=db_session,
        frame=frame,
        received_at=received_at,
    )

    project_id = _project_id_for_run(db_session=db_session, run_id=run_id)
    event_payload = {
        "run_id": run_id,
        "project_id": project_id,
        "client_id": authenticated_client_id,
        "frame_kind": frame.frame_kind,
        "frame_index": frame.frame_index,
        "phase": frame.phase,
        "status": frame.status,
        "percent_complete": frame.percent_complete,
        "notes": frame.notes,
        "recorded_at": frame.recorded_at.isoformat(),
        "received_at": received_at.isoformat(),
        "payload": dict(frame.payload),
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
            topic=ProgressEventTopics.FRAME_LANDED,
            payload=event_payload,
            source_event_id=new_uuid(),
        ),
    )
    db_session.commit()
    rtnval = frame
    return rtnval


def get_latest_frame(
        *,
        db_session: DbSession,
        run_id: str
    ) -> Optional[ProgressFrameEnvelope]:
    """
        Return the most recently received generalized
        build / provision progress frame for ``run_id``, or
        ``None`` when none has landed.
    """
    row = repositories.latest_frame(db_session=db_session, run_id=run_id)
    if row is None:
        return None
    rtnval = _frame_row_to_envelope(row=row)
    return rtnval


def list_frames(
        *,
        db_session: DbSession,
        run_id: str
    ) -> List[ProgressFrameEnvelope]:
    """
        Return every persisted generalized progress frame for
        ``run_id`` ordered by receive time.
    """
    rows = repositories.list_frames(db_session=db_session, run_id=run_id)
    rtnval: List[ProgressFrameEnvelope] = []
    for row in rows:
        rtnval.append(_frame_row_to_envelope(row=row))
    return rtnval


def _frame_row_to_envelope(*, row: Any) -> ProgressFrameEnvelope:
    """
        Map a ``RunProgressFrame`` ORM row to a canonical
        :class:`ProgressFrameEnvelope`.
    """
    rtnval = ProgressFrameEnvelope(
        run_id=str(row.run_id),
        client_id=str(row.client_id),
        frame_kind=row.frame_kind,
        frame_index=row.frame_index,
        phase=row.phase,
        status=row.status,
        percent_complete=row.percent_complete,
        notes=row.notes,
        recorded_at=row.recorded_at,
        payload=dict(row.raw_payload or {}),
    )
    return rtnval


def _parse_frame(
        *,
        run_id: str,
        client_id: str,
        frame_kind: str,
        frame_index: int,
        payload: Mapping[str, Any]
    ) -> ProgressFrameEnvelope:
    """
        Structurally parse a ``build`` / ``provision`` progress
        frame payload into a :class:`ProgressFrameEnvelope`.

        :raises: ProgressFormatError when a structural field has
                 an unusable type.
    """
    phase = _string_or_none(value=payload.get("phase", None))
    status = _string_or_none(value=payload.get("status", None))
    notes = _string_or_none(value=payload.get("notes", None))

    percent_raw = payload.get("percent_complete", None)
    percent_complete: Optional[float] = None
    if percent_raw is not None:
        try:
            percent_complete = float(percent_raw)
        except (TypeError, ValueError):
            err_lines = ["Cannot ingest progress frame — 'percent_complete' not a number."]
            err_lines.append("RUN_ID: {}".format(run_id))
            err_lines.append("VALUE: {}".format(percent_raw))
            err_msg = os.linesep.join(err_lines)
            raise ProgressFormatError(err_msg) from None

    recorded_at = _parse_iso(value=payload.get("recorded_at", None))
    if recorded_at is None:
        recorded_at = utc_now()

    rtnval = ProgressFrameEnvelope(
        run_id=run_id,
        client_id=client_id,
        frame_kind=frame_kind,
        frame_index=frame_index,
        phase=phase,
        status=status,
        percent_complete=percent_complete,
        notes=notes,
        recorded_at=recorded_at,
        payload=dict(payload),
    )
    return rtnval


def _string_or_none(*, value: Any) -> Optional[str]:
    """
        Pass through non-empty strings; return ``None`` otherwise.
    """
    if value is None:
        return None
    if isinstance(value, str) is False:
        return None
    text = value.strip()
    if len(text) == 0:
        return None
    return text


def _parse_iso(*, value: Any) -> Optional[datetime]:
    """
        Best-effort ISO-8601 parser; returns ``None`` for empty /
        unparseable input rather than raising.
    """
    if value is None:
        return None
    if isinstance(value, str) is False:
        return None
    text = value.strip()
    if len(text) == 0:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        rtnval = datetime.fromisoformat(text)
    except ValueError:
        return None
    if rtnval.tzinfo is None:
        rtnval = rtnval.replace(tzinfo=timezone.utc)
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
