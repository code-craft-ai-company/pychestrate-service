"""
.. module:: audit.sink_dispatcher
    :synopsis: Per-sink outbox dispatcher.

The dispatcher pulls PENDING rows out of the
``audit_sink_outbox`` table for one sink, calls the sink's
:meth:`AuditSinkProtocol.write_records`, and flips the row to
COMPLETED on success or FAILED on a wire error. Records are
delivered in ``sequence_number`` order so a non-canonical
sink mirrors the canonical chain shape.

The canonical sink is *not* re-fanned out through this path —
``capture_event`` already wrote the canonical row inline, so
the dispatcher skips ``is_canonical=True`` sinks during
:func:`enqueue_record_for_fanout`.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Tuple, Type

from sqlalchemy.orm import Session as DbSession

from automojo.pychestrate.core.defaults import new_uuid, utc_now

from automojo.pychestrate.webservice.audit.factories.audit_sink import (
    AuditSinkProtocol,
)
from automojo.pychestrate.webservice.audit.models import (
    AuditRecord,
    AuditSinkOutbox,
    AuditSinkOutboxStatus,
)
from automojo.pychestrate.webservice.extensions.registry import (
    list_factory_implementations,
)


@dataclass(frozen=True)
class DrainReport:
    """
        Per-call dispatcher summary.

        :param sink_name: Sink the drain ran against.
        :param processed: Number of outbox rows attempted.
        :param succeeded: Number of rows transitioned to
                          COMPLETED.
        :param failed: Number of rows transitioned to FAILED.
        :param last_sequence_written: Highest sequence the sink
                                      reported back.
    """
    sink_name: str
    processed: int
    succeeded: int
    failed: int
    last_sequence_written: int


def enqueue_record_for_fanout(
        *,
        db_session: DbSession,
        record: AuditRecord
    ) -> int:
    """
        Insert one PENDING row in ``audit_sink_outbox`` for
        every registered non-canonical sink. Called by the
        capture path right after the canonical row lands.

        :returns: Number of fan-out rows inserted.
    """
    sinks = _list_fanout_sinks()
    if sinks is None or len(sinks) == 0:
        return 0
    now = utc_now()
    inserted = 0
    for sink_cls in sinks:
        outbox = AuditSinkOutbox(
            outbox_id=new_uuid(),
            sink_name=sink_cls.sink_name(),
            sequence_number=int(record.sequence_number),
            status=AuditSinkOutboxStatus.PENDING,
            enqueued_at=now,
            next_attempt_at=None,
            retry_count=0,
        )
        db_session.add(outbox)
        inserted = inserted + 1
    db_session.flush()
    return inserted


def drain_sink_outbox(
        *,
        db_session: DbSession,
        sink_name: str,
        batch_size: int = 100
    ) -> DrainReport:
    """
        Drain up to ``batch_size`` PENDING rows for ``sink_name``,
        pull the matching :class:`AuditRecord` rows in sequence
        order, deliver them through the sink's
        :meth:`AuditSinkProtocol.write_records`, and flip the
        outbox rows to COMPLETED or FAILED.

        :raises: ValueError when ``sink_name`` has no
                 registered implementation.
    """
    sink_cls = _resolve_sink(sink_name=sink_name)
    if sink_cls is None:
        err_lines = ["No registered audit_sink for the supplied name."]
        err_lines.append("SINK_NAME: {!r}".format(sink_name))
        err_msg = os.linesep.join(err_lines)
        raise ValueError(err_msg) from None
    if sink_cls.is_canonical() is True:
        # The canonical sink is never drained from the outbox —
        # the capture path wrote it inline.
        rtnval = DrainReport(
            sink_name=sink_name,
            processed=0,
            succeeded=0,
            failed=0,
            last_sequence_written=0,
        )
        return rtnval

    pending_rows = (
        db_session.query(AuditSinkOutbox)
        .filter(AuditSinkOutbox.sink_name == sink_name)
        .filter(AuditSinkOutbox.status == AuditSinkOutboxStatus.PENDING)
        .order_by(AuditSinkOutbox.sequence_number.asc())
        .limit(batch_size)
        .all()
    )
    if pending_rows is None or len(pending_rows) == 0:
        rtnval = DrainReport(
            sink_name=sink_name,
            processed=0,
            succeeded=0,
            failed=0,
            last_sequence_written=0,
        )
        return rtnval

    sequence_numbers = [int(row.sequence_number) for row in pending_rows]
    records = _fetch_records(
        db_session=db_session, sequence_numbers=sequence_numbers,
    )
    record_by_sequence = {
        int(record.sequence_number): record for record in records
    }

    deliverable: List[AuditRecord] = []
    deliverable_outbox: List[AuditSinkOutbox] = []
    for outbox_row in pending_rows:
        outbox_row.status = AuditSinkOutboxStatus.IN_FLIGHT
        record = record_by_sequence.get(int(outbox_row.sequence_number))
        if record is None:
            outbox_row.status = AuditSinkOutboxStatus.FAILED
            outbox_row.retry_count = outbox_row.retry_count + 1
            continue
        deliverable.append(record)
        deliverable_outbox.append(outbox_row)
    db_session.flush()

    succeeded = 0
    failed = 0
    last_sequence = 0
    if len(deliverable) > 0:
        try:
            result = sink_cls.write_records(
                records=tuple(deliverable),
            )
        except Exception as write_err:
            for outbox_row in deliverable_outbox:
                outbox_row.status = AuditSinkOutboxStatus.FAILED
                outbox_row.retry_count = outbox_row.retry_count + 1
            db_session.flush()
            db_session.commit()
            err_lines = ["Audit sink write_records raised."]
            err_lines.append("SINK_NAME: {}".format(sink_name))
            err_lines.append("DETAIL: {}".format(write_err))
            err_msg = os.linesep.join(err_lines)
            raise RuntimeError(err_msg) from None
        last_sequence = int(getattr(result, "last_sequence_written", 0))
        for outbox_row in deliverable_outbox:
            if int(outbox_row.sequence_number) <= last_sequence:
                outbox_row.status = AuditSinkOutboxStatus.COMPLETED
                succeeded = succeeded + 1
            else:
                outbox_row.status = AuditSinkOutboxStatus.FAILED
                outbox_row.retry_count = outbox_row.retry_count + 1
                failed = failed + 1
    db_session.flush()
    db_session.commit()

    failed = failed + sum(
        1 for outbox_row in pending_rows
        if outbox_row.status == AuditSinkOutboxStatus.FAILED
        and outbox_row not in deliverable_outbox
    )
    rtnval = DrainReport(
        sink_name=sink_name,
        processed=len(pending_rows),
        succeeded=succeeded,
        failed=failed,
        last_sequence_written=last_sequence,
    )
    return rtnval


def _list_fanout_sinks() -> List[Type[AuditSinkProtocol]]:
    candidates = list_factory_implementations(
        factory_protocol_name=AuditSinkProtocol.factory_protocol_name,
    )
    rtnval: List[Type[AuditSinkProtocol]] = []
    for impl in candidates:
        try:
            if impl.is_canonical() is True:
                continue
        except NotImplementedError:
            continue
        rtnval.append(impl)
    return rtnval


def _resolve_sink(*, sink_name: str):
    candidates = list_factory_implementations(
        factory_protocol_name=AuditSinkProtocol.factory_protocol_name,
    )
    for impl in candidates:
        try:
            if impl.sink_name() == sink_name:
                return impl
        except NotImplementedError:
            continue
    return None


def _fetch_records(
        *,
        db_session: DbSession,
        sequence_numbers: Iterable[int]
    ) -> List[AuditRecord]:
    seq_list = list(sequence_numbers)
    if len(seq_list) == 0:
        return []
    rows = (
        db_session.query(AuditRecord)
        .filter(AuditRecord.sequence_number.in_(seq_list))
        .order_by(AuditRecord.sequence_number.asc())
        .all()
    )
    rtnval = list(rows)
    return rtnval
