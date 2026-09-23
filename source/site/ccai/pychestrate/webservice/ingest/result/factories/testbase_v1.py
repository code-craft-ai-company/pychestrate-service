"""
.. module:: ingest.result.factories.testbase_v1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Reference parser for the testbase result tree.

.. moduleauthor:: Code Craft AI LLC

Reads:

- ``testrun_summary.json`` — for the run-level roll-up.
- ``testrun_results_stream.jsos`` — for each test scope's
  authoritative result row (the *finished* records, not the
  preview rows).
- Every regular file under the tree — catalogued as an artifact
  with a classification derived from its top-level subdirectory.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import mimetypes
import os

from datetime import datetime, timezone
from typing import Any, List, Mapping, Optional

from ccai.pychestrate.webservice.ingest.result.factories.parser_protocol import (
    ParsedArtifact,
    ParsedResultTree,
    ParsedSummary,
    ParsedTaskResult,
    ResultTreeParserProtocol,
)


TESTBASE_V1_PARSER_TAG: str = "testbase-v1"

JSOS_RECORD_SEPARATOR: int = 0x1E
SUMMARY_FILENAME: str = "testrun_summary.json"
RESULTS_STREAM_FILENAME: str = "testrun_results_stream.jsos"
RESULTS_FINAL_FILENAME: str = "testrun_results.json"

ARTIFACT_CLASSIFICATION_MAP = {
    "artifacts": "artifact",
    "taskings": "tasking",
    "tc-by-products": "tc-by-product",
    "diagnostics": "diagnostic",
}
SUMMARY_CLASSIFICATION = "summary"
PROGRESS_STREAM_CLASSIFICATION = "progress-stream"


class TestBaseResultTreeParser(ResultTreeParserProtocol):
    """
        Default parser. Tolerant of partial trees — a missing
        summary or empty results stream is reflected on the
        :class:`ParsedResultTree` rather than raising.
    """

    factory_protocol_name: str = "result_tree_parser"
    protocol_schema_version: int = 1
    PRECEDENCE: int = 1000

    @classmethod
    def parser_tag(cls) -> str:
        rtnval = TESTBASE_V1_PARSER_TAG
        return rtnval

    @classmethod
    def recognizes_tree(cls, *, tree_path: str) -> bool:
        """
            A testbase tree has its summary or results stream at the root.
        """
        if tree_path is None or len(tree_path) == 0 or os.path.isdir(tree_path) is False:
            return False
        rtnval = False
        for marker in (SUMMARY_FILENAME, RESULTS_STREAM_FILENAME, RESULTS_FINAL_FILENAME):
            if os.path.isfile(os.path.join(tree_path, marker)):
                rtnval = True
        return rtnval

    @classmethod
    def parse_tree(cls, *, tree_path: str) -> ParsedResultTree:
        if tree_path is None or len(tree_path) == 0:
            return ParsedResultTree(summary=None, tasks=[], artifacts=[], files_seen=0)
        if os.path.isdir(tree_path) is False:
            return ParsedResultTree(summary=None, tasks=[], artifacts=[], files_seen=0)

        summary = _parse_summary(tree_path=tree_path)
        tasks = _parse_results_stream(tree_path=tree_path)
        artifacts, files_seen = _walk_artifacts(tree_path=tree_path)

        rtnval = ParsedResultTree(
            summary=summary,
            tasks=tasks,
            artifacts=artifacts,
            files_seen=files_seen,
        )
        return rtnval


def _parse_summary(*, tree_path: str) -> Optional[ParsedSummary]:
    """
        Read ``testrun_summary.json`` if present.
    """
    summary_path = os.path.join(tree_path, SUMMARY_FILENAME)
    if os.path.isfile(summary_path) is False:
        return None
    try:
        with open(summary_path, "rb") as fh:
            raw = json.loads(fh.read().decode("utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(raw, dict) is False:
        return None

    detail = raw.get("detail", {})
    if isinstance(detail, dict) is False:
        detail = {}

    rtnval = ParsedSummary(
        tests_total=_int_or_zero(value=detail.get("total", raw.get("tests_total", 0))),
        tests_passed=_int_or_zero(value=detail.get("passed", raw.get("tests_passed", 0))),
        tests_failed=_int_or_zero(value=detail.get("failed", raw.get("tests_failed", 0))),
        tests_skipped=_int_or_zero(value=detail.get("skipped", raw.get("tests_skipped", 0))),
        tests_errored=_int_or_zero(value=detail.get("errors", raw.get("tests_errored", 0))),
        started_at=_iso_or_none(value=raw.get("start", None)),
        finished_at=_iso_or_none(value=raw.get("stop", None)),
        raw=dict(raw),
    )
    return rtnval


def _parse_results_stream(*, tree_path: str) -> List[ParsedTaskResult]:
    """
        Walk ``testrun_results_stream.jsos`` and return one
        :class:`ParsedTaskResult` per *terminal* record (one whose
        ``result`` is anything other than ``UNSET``).

        The stream contains both preview rows (``UNSET``) and
        authoritative result rows; the parser uses the
        ``instance`` UUID to dedupe — the last terminal row for
        each instance wins.
    """
    stream_path = os.path.join(tree_path, RESULTS_STREAM_FILENAME)
    if os.path.isfile(stream_path) is False:
        return []
    try:
        with open(stream_path, "rb") as fh:
            blob = fh.read()
    except OSError:
        return []
    pieces = blob.split(bytes([JSOS_RECORD_SEPARATOR]))

    by_instance: dict = {}
    for piece in pieces:
        text = piece.strip()
        if len(text) == 0:
            continue
        try:
            obj = json.loads(text)
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(obj, dict) is False:
            continue
        result_str = obj.get("result", "UNSET")
        if isinstance(result_str, str) is False:
            result_str = str(result_str)
        result_str = result_str.upper().strip() or "UNSET"
        if result_str == "UNSET":
            continue
        instance_uuid = obj.get("instance", "") or ""
        if isinstance(instance_uuid, str) is False:
            instance_uuid = str(instance_uuid)
        if len(instance_uuid) == 0:
            continue
        rtype = obj.get("rtype", "TEST")
        if isinstance(rtype, str) is False:
            rtype = "TEST"
        test_name = obj.get("name", "")
        if isinstance(test_name, str) is False:
            test_name = str(test_name)

        by_instance[instance_uuid] = ParsedTaskResult(
            instance_uuid=instance_uuid,
            test_name=test_name,
            rtype=rtype,
            result=result_str,
            started_at=_iso_or_none(value=obj.get("start", None)),
            finished_at=_iso_or_none(value=obj.get("stop", None)),
            raw=dict(obj),
        )

    rtnval = list(by_instance.values())
    return rtnval


def _walk_artifacts(*, tree_path: str):
    """
        Walk every regular file under ``tree_path`` and produce a
        :class:`ParsedArtifact` describing it. Returns a tuple
        ``(artifacts, files_seen)``.
    """
    artifacts: List[ParsedArtifact] = []
    files_seen = 0
    for root, _dirs, files in os.walk(tree_path):
        for fname in files:
            files_seen = files_seen + 1
            full_path = os.path.join(root, fname)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                size = 0
            relative = os.path.relpath(full_path, start=tree_path)
            classification = _classify_relative_path(relative=relative)
            content_type, _ = mimetypes.guess_type(full_path)
            artifacts.append(
                ParsedArtifact(
                    relative_path=relative,
                    classification=classification,
                    size_bytes=int(size),
                    content_type=content_type,
                )
            )
    rtnval = (artifacts, files_seen)
    return rtnval


def _classify_relative_path(*, relative: str) -> str:
    """
        Pick a classification string from a relative path.
        Top-level convention: the first segment names the
        category (``artifacts/`` → ``artifact``,
        ``taskings/`` → ``tasking``, …); known top-level files
        get explicit classifications.
    """
    if relative == SUMMARY_FILENAME or relative == RESULTS_FINAL_FILENAME:
        return SUMMARY_CLASSIFICATION
    if relative == RESULTS_STREAM_FILENAME:
        return PROGRESS_STREAM_CLASSIFICATION

    parts = relative.replace("\\", "/").split("/")
    if len(parts) == 0:
        return "other"
    head = parts[0]
    return ARTIFACT_CLASSIFICATION_MAP.get(head, "other")


def _int_or_zero(*, value: Any) -> int:
    """
        Coerce to int with a safe zero fallback.
    """
    if value is None:
        return 0
    try:
        rtnval = int(value)
    except (TypeError, ValueError):
        return 0
    return rtnval


def _iso_or_none(*, value: Any) -> Optional[datetime]:
    """
        Best-effort ISO-8601 parser.
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
