"""
.. module:: ingest.progress.factories.testbase_v1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference progress parser for the testbase format.

.. moduleauthor:: Code Craft AI LLC

Handles the shapes documented in ``AGENTS.md``'s "Evaluating Test
Results" section: a JSOS stream of records with ``name``, ``rtype``,
``result``, ``start``, ``stop``, and a ``detail`` block on completed
results. Summary posts are derived from
``testrun_summary.json`` — total / pass / fail / skip / errored.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from ccai.pychestrate.core.defaults import utc_now

from ccai.pychestrate.webservice.ingest.progress.factories.parser_protocol import (
    ProgressParserProtocol,
)
from ccai.pychestrate.webservice.ingest.progress.schema import (
    ProgressRecord,
    ProgressSummary,
)


TESTBASE_V1_FORMAT_TAG: str = "testbase-v1"


class TestBaseProgressParser(ProgressParserProtocol):
    """
        Default M1 parser. Maps testbase fields directly into the
        canonical schema; unknown fields land in the ``raw``
        passthrough dict.
    """

    factory_protocol_name: str = "progress_parser"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def format_tag(cls) -> str:
        rtnval = TESTBASE_V1_FORMAT_TAG
        return rtnval

    @classmethod
    def parse_summary(
            cls,
            *,
            run_id: str,
            client_id: str,
            payload: Mapping[str, Any]
        ) -> ProgressSummary:
        recorded_at = _parse_iso(value=payload.get("recorded_at", None))
        if recorded_at is None:
            recorded_at = utc_now()

        rtnval = ProgressSummary(
            run_id=run_id,
            client_id=client_id,
            format_tag=TESTBASE_V1_FORMAT_TAG,
            tests_total=_int_or_none(payload.get("tests_total", None)),
            tests_passed=_int_or_zero(payload.get("tests_passed", 0)),
            tests_failed=_int_or_zero(payload.get("tests_failed", 0)),
            tests_skipped=_int_or_zero(payload.get("tests_skipped", 0)),
            tests_errored=_int_or_zero(payload.get("tests_errored", 0)),
            percent_complete=_float_or_none(payload.get("percent_complete", None)),
            notes=_string_or_none(payload.get("notes", None)),
            recorded_at=recorded_at,
            raw=dict(payload),
        )
        return rtnval

    @classmethod
    def parse_record(
            cls,
            *,
            run_id: str,
            client_id: str,
            record_index: int,
            payload: Mapping[str, Any]
        ) -> ProgressRecord:
        result = payload.get("result", "UNSET")
        if isinstance(result, str) is False:
            result = str(result)
        result = result.upper().strip() or "UNSET"

        started = _parse_iso(value=payload.get("start", None))
        finished = _parse_iso(value=payload.get("stop", None))
        duration: Optional[float] = None
        if started is not None and finished is not None:
            duration = (finished - started).total_seconds()

        test_name_raw = payload.get("name", "")
        if isinstance(test_name_raw, str) is False:
            test_name_raw = str(test_name_raw)

        rtnval = ProgressRecord(
            run_id=run_id,
            client_id=client_id,
            record_index=record_index,
            test_name=test_name_raw,
            result=result,
            started_at=started,
            finished_at=finished,
            duration_seconds=duration,
            raw=dict(payload),
        )
        return rtnval


def _parse_iso(*, value: Any) -> Optional[datetime]:
    """
        Best-effort ISO-8601 parser; returns ``None`` for empty
        / unparseable input rather than raising so a malformed
        timestamp on one record does not poison the whole stream.
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


def _int_or_zero(value: Any) -> int:
    """
        Coerce ``value`` to ``int`` or return ``0``.
    """
    if value is None:
        return 0
    try:
        rtnval = int(value)
    except (TypeError, ValueError):
        return 0
    return rtnval


def _int_or_none(value: Any) -> Optional[int]:
    """
        Coerce ``value`` to ``int`` or return ``None``.
    """
    if value is None:
        return None
    try:
        rtnval = int(value)
    except (TypeError, ValueError):
        return None
    return rtnval


def _float_or_none(value: Any) -> Optional[float]:
    """
        Coerce ``value`` to ``float`` or return ``None``.
    """
    if value is None:
        return None
    try:
        rtnval = float(value)
    except (TypeError, ValueError):
        return None
    return rtnval


def _string_or_none(value: Any) -> Optional[str]:
    """
        Pass through strings; return ``None`` otherwise.
    """
    if value is None:
        return None
    if isinstance(value, str) is False:
        return None
    text = value.strip()
    if len(text) == 0:
        return None
    return text
