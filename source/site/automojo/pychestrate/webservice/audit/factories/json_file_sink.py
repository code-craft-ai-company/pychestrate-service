"""
.. module:: audit.factories.json_file_sink
    :synopsis: JsonFileAuditSink — append-only JSONL fan-out sink.

The sink writes one canonical JSON line per record to a
configured file path. M2 ships the sink as a non-canonical
fan-out target; M3 hardening swaps the path config to the
operator-managed audit log directory.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import threading

from typing import Any, Optional, Tuple

from automojo.pychestrate.webservice.audit.factories.audit_sink import (
    AuditSinkProtocol,
    SinkHealth,
    SinkWriteResult,
)


_LOCK = threading.RLock()
_FILE_PATH: Optional[str] = None


def configure(*, file_path: str) -> None:
    """
        Set the active file path the sink writes JSONL records
        to. Operator bootstrap calls this once at startup.
    """
    global _FILE_PATH
    with _LOCK:
        _FILE_PATH = file_path
    return


def get_configured_path() -> Optional[str]:
    """
        Return the currently configured JSONL file path.
    """
    with _LOCK:
        return _FILE_PATH


def reset_for_testing() -> None:
    """
        Drop the active file-path configuration so tests do
        not bleed paths across cases.
    """
    global _FILE_PATH
    with _LOCK:
        _FILE_PATH = None
    return


class JsonFileAuditSink(AuditSinkProtocol):
    """
        Reference fan-out audit sink that writes one JSON
        object per line to a configured file. The sink
        serializes records via the canonical JSON form
        (sorted keys, no whitespace) so an external tail-er
        can decode each line independently.
    """

    factory_protocol_name: str = "audit_sink"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 2000

    @classmethod
    def sink_name(cls) -> str:
        rtnval = "json-file"
        return rtnval

    @classmethod
    def is_canonical(cls) -> bool:
        rtnval = False
        return rtnval

    @classmethod
    def write_records(cls, *, records: Tuple) -> SinkWriteResult:
        """
            Append every record to the configured file path.

            :raises: RuntimeError when no path is configured —
                     callers either configure() before write
                     or accept the runtime error as a wiring
                     bug.
        """
        path = get_configured_path()
        if path is None:
            err_lines = ["JsonFileAuditSink path has not been configured."]
            err_lines.append("CALL: configure(file_path=...) at bootstrap.")
            err_msg = os.linesep.join(err_lines)
            raise RuntimeError(err_msg) from None
        if records is None or len(records) == 0:
            rtnval = SinkWriteResult(
                written_count=0, last_sequence_written=0,
            )
            return rtnval

        last_sequence = 0
        with _LOCK:
            with open(path, "a", encoding="utf-8") as handle:
                for record in records:
                    line = _canonicalize(record=record)
                    handle.write(line)
                    handle.write("\n")
                    sequence = int(getattr(record, "sequence_number", 0))
                    if sequence > last_sequence:
                        last_sequence = sequence
        rtnval = SinkWriteResult(
            written_count=len(records),
            last_sequence_written=last_sequence,
        )
        return rtnval

    @classmethod
    def health_check(cls) -> SinkHealth:
        path = get_configured_path()
        if path is None:
            rtnval = SinkHealth(
                healthy=False,
                reason="path_not_configured",
            )
            return rtnval
        directory = os.path.dirname(path) or "."
        if not os.path.isdir(directory):
            rtnval = SinkHealth(
                healthy=False,
                reason="parent_directory_missing",
            )
            return rtnval
        if not os.access(directory, os.W_OK):
            rtnval = SinkHealth(
                healthy=False,
                reason="parent_directory_not_writable",
            )
            return rtnval
        rtnval = SinkHealth(healthy=True, reason="")
        return rtnval


def _canonicalize(*, record: Any) -> str:
    """
        Render an :class:`AuditRecord` as a one-line canonical
        JSON object. The form mirrors the canonicalization the
        chain hash uses so external archivers can replay the
        chain compute against this file.
    """
    record_hash = bytes(record.record_hash) if record.record_hash is not None else b""
    previous_hash = bytes(record.previous_hash) if record.previous_hash is not None else b""
    payload = record.payload_json if record.payload_json is not None else {}
    rendered = {
        "sequence_number": int(record.sequence_number),
        "record_id": str(record.record_id),
        "kind": record.kind,
        "source_topic": record.source_topic,
        "source_event_id": str(record.source_event_id),
        "actor_user_id": (
            str(record.actor_user_id)
            if record.actor_user_id is not None else None
        ),
        "actor_service_identity": record.actor_service_identity,
        "target_ref": record.target_ref,
        "payload_json": payload,
        "payload_hash_hex": bytes(record.payload_hash).hex(),
        "previous_hash_hex": previous_hash.hex(),
        "record_hash_hex": record_hash.hex(),
        "written_at": record.written_at.isoformat(),
    }
    rtnval = json.dumps(rendered, sort_keys=True, separators=(",", ":"))
    return rtnval
