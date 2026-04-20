"""
.. module:: audit.factories.audit_sink
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: FactoryProtocolBase for pluggable audit sinks.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Tuple

from automojo.pychestrate.webservice.extensions.factory_protocol import FactoryProtocolBase


@dataclass(frozen=True)
class SinkWriteResult:
    """
        Result of a batch write to an audit sink.

        :param written_count: Number of records persisted.
        :param last_sequence_written: Highest sequence number acknowledged.
    """
    written_count: int
    last_sequence_written: int


@dataclass(frozen=True)
class SinkHealth:
    """
        Health report returned by :meth:`AuditSinkProtocol.health_check`.

        :param healthy: Current health status.
        :param reason: Short reason string when unhealthy.
    """
    healthy: bool
    reason: str


class AuditSinkProtocol(FactoryProtocolBase):
    """
        Contract for any ``audit_sink`` implementation.
    """

    factory_protocol_name: str = "audit_sink"
    protocol_schema_version: int = 1

    @classmethod
    def sink_name(cls) -> str:
        """
            Return the sink's unique name.

            :returns: The sink name string.
        """
        raise NotImplementedError("Subclasses must implement sink_name")

    @classmethod
    def is_canonical(cls) -> bool:
        """
            True only for the single canonical durable sink.

            :returns: Boolean.
        """
        raise NotImplementedError("Subclasses must implement is_canonical")

    @classmethod
    def write_records(cls, *, records: Tuple) -> SinkWriteResult:
        """
            Write one or more :class:`AuditRecord` rows. Must be idempotent
            on ``sequence_number``.

            :param records: Tuple of :class:`AuditRecord` instances.

            :returns: :class:`SinkWriteResult`.
        """
        raise NotImplementedError("Subclasses must implement write_records")

    @classmethod
    def health_check(cls) -> SinkHealth:
        """
            Report current sink health.

            :returns: :class:`SinkHealth`.
        """
        raise NotImplementedError("Subclasses must implement health_check")
