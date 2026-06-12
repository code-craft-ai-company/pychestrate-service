"""
.. module:: audit.factories.local_db_sink
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Canonical local-database audit sink.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2025, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Tuple

from ccai.pychestrate.webservice.audit.factories.audit_sink import (
    AuditSinkProtocol,
    SinkHealth,
    SinkWriteResult,
)


class LocalDatabaseAuditSink(AuditSinkProtocol):
    """
        Reference canonical sink that persists to the ``audit_records``
        table. All record-writing logic lives in
        :mod:`ccai.pychestrate.webservice.audit.audit_writer`; this
        class exposes only the factory surface so operators can enumerate
        registered sinks through the extension host.
    """

    factory_protocol_name: str = "audit_sink"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def sink_name(cls) -> str:
        rtnval = "local-db"
        return rtnval

    @classmethod
    def is_canonical(cls) -> bool:
        rtnval = True
        return rtnval

    @classmethod
    def write_records(cls, *, records: Tuple) -> SinkWriteResult:
        # The canonical write happens inline in audit_writer.capture_event
        # under the same transaction as the audit record insert. Records
        # reach this method only if a consumer drains the outbox for this
        # sink, which is a no-op for the canonical path.
        written_count = len(records)
        last_sequence = 0
        if written_count > 0:
            last_sequence = int(getattr(records[-1], "sequence_number", 0))
        rtnval = SinkWriteResult(
            written_count=written_count,
            last_sequence_written=last_sequence,
        )
        return rtnval

    @classmethod
    def health_check(cls) -> SinkHealth:
        rtnval = SinkHealth(healthy=True, reason="")
        return rtnval
