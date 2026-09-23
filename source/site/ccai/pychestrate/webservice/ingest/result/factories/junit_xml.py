"""
.. module:: ingest.result.factories.junit_xml
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Result-tree parser for JUnit / xUnit XML reports.

.. moduleauthor:: Code Craft AI LLC

Most test frameworks can write JUnit-style XML: pytest
(``--junitxml``), Maven Surefire and Gradle, GoogleTest
(``--gtest_output=xml``), go-junit-report, jest-junit, NUnit and xUnit.net
converters, and more. This parser reads every such report in a result
tree, so a team does not need testbase to bring its results to
Pychestrate.

A report is any ``*.xml`` file whose root element is ``<testsuites>`` or
``<testsuite>``. Each ``<testcase>`` becomes one task result:

* ``<error>`` -- ``ERRORED``;
* ``<failure>``, or Surefire ``<rerunFailure>`` (every rerun failed) --
  ``FAILED``;
* ``<skipped>``, or GoogleTest's ``status="notrun"`` /
  ``result="skipped"`` -- ``SKIPPED``;
* otherwise -- ``PASSED``; a test with only Surefire ``<flakyFailure>``
  entries passed on a rerun and is marked flaky on its row.

The failure message, type and (truncated) text are kept on the row so a
failure can be diagnosed without opening the report. Task ids are
derived from the report path and the test's position, so scanning the
same tree again updates the same rows. Every file in the tree is also
catalogued as an artifact.

Reports that declare a DOCTYPE are refused (JUnit reports never need
one, and refusing them rules out entity-expansion attacks), and very
large reports are skipped rather than loaded into memory.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import mimetypes
import os
import uuid

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree

from ccai.pychestrate.webservice.ingest.result.factories.parser_protocol import (
    ParsedArtifact,
    ParsedResultTree,
    ParsedSummary,
    ParsedTaskResult,
    ResultTreeParserProtocol,
)


JUNIT_XML_PARSER_TAG: str = "junit-xml"

REPORT_CLASSIFICATION: str = "summary"
ARTIFACT_CLASSIFICATION: str = "artifact"

# Reports larger than this are catalogued but not parsed.
MAX_REPORT_BYTES: int = 64 * 1024 * 1024
# How many ``*.xml`` files are sniffed when deciding whether a tree holds
# JUnit reports.
MAX_FILES_SNIFFED: int = 500
# How much of a file is read when sniffing its root element.
SNIFF_BYTES: int = 4096
# Longest failure text / captured output kept on a task row.
MAX_TEXT_CHARS: int = 8192
# ``TaskResult.test_name`` column width.
MAX_TEST_NAME_CHARS: int = 512

RESULT_PASSED: str = "PASSED"
RESULT_FAILED: str = "FAILED"
RESULT_ERRORED: str = "ERRORED"
RESULT_SKIPPED: str = "SKIPPED"

# Files a testbase tree always has at its root; a tree with any of them is
# testbase's to parse.
TESTBASE_MARKERS: Tuple[str, ...] = (
    "testrun_summary.json",
    "testrun_results_stream.jsos",
    "testrun_results.json",
)

_TASK_ID_NAMESPACE = uuid.UUID("8f0c7c2e-4b54-4f4e-9b36-6a4d1b1e5a20")


class JUnitReportRefusedError(ValueError):
    """
        A report the parser will not read (it declares a DOCTYPE).
    """


class JUnitXmlResultTreeParser(ResultTreeParserProtocol):
    """
        Parser for result trees holding JUnit / xUnit XML reports.
    """

    factory_protocol_name: str = "result_tree_parser"
    protocol_schema_version: int = 1
    # After testbase (1000): testbase stays the fallback for trees that
    # neither parser recognizes.
    PRECEDENCE: int = 2000

    @classmethod
    def parser_tag(cls) -> str:
        rtnval = JUNIT_XML_PARSER_TAG
        return rtnval

    @classmethod
    def recognizes_tree(cls, *, tree_path: str) -> bool:
        """
            A tree is a JUnit tree when it has at least one JUnit report
            and none of testbase's root files.
        """
        if tree_path is None or os.path.isdir(tree_path) is False:
            return False
        for marker in TESTBASE_MARKERS:
            if os.path.isfile(os.path.join(tree_path, marker)):
                return False
        rtnval = len(_find_reports(tree_path=tree_path, stop_after_first=True)) > 0
        return rtnval

    @classmethod
    def parse_tree(cls, *, tree_path: str) -> ParsedResultTree:
        if tree_path is None or len(tree_path) == 0 or os.path.isdir(tree_path) is False:
            return ParsedResultTree(summary=None, tasks=[], artifacts=[], files_seen=0)

        reports = _find_reports(tree_path=tree_path, stop_after_first=False)
        tasks: List[ParsedTaskResult] = []
        suite_starts: List[datetime] = []
        total_seconds = 0.0
        parsed_reports: List[str] = []
        refused_reports: List[Dict[str, str]] = []
        for relative in reports:
            try:
                report_tasks, starts, seconds = _parse_report(
                    full_path=os.path.join(tree_path, relative), relative=relative,
                )
            except (JUnitReportRefusedError, ElementTree.ParseError, OSError) as xcpt:
                refused_reports.append({"report": relative, "reason": str(xcpt)})
                continue
            tasks.extend(report_tasks)
            suite_starts.extend(starts)
            total_seconds += seconds
            parsed_reports.append(relative)

        summary: Optional[ParsedSummary] = None
        if len(parsed_reports) > 0:
            summary = _summarize(
                tasks=tasks, suite_starts=suite_starts, total_seconds=total_seconds,
                parsed_reports=parsed_reports, refused_reports=refused_reports,
            )
        artifacts, files_seen = _catalogue(tree_path=tree_path, reports=set(reports))
        rtnval = ParsedResultTree(summary=summary, tasks=tasks, artifacts=artifacts, files_seen=files_seen)
        return rtnval


# ---------------------------------------------------------------------------
# Finding reports
# ---------------------------------------------------------------------------


def _sniff_is_report(*, full_path: str) -> bool:
    """
        Whether the file's root element is ``<testsuites>`` or
        ``<testsuite>``, judged from its first few kilobytes.
    """
    try:
        with open(full_path, "rb") as fh:
            head = fh.read(SNIFF_BYTES)
    except OSError:
        return False
    text = head.decode("utf-8", errors="replace")
    index = 0
    while True:
        start = text.find("<", index)
        if start < 0 or start + 1 >= len(text):
            return False
        if text.startswith("<!--", start):
            end = text.find("-->", start + 4)
            if end < 0:
                return False
            index = end + 3
            continue
        following = text[start + 1]
        if following in ("?", "!"):
            # XML declaration or DOCTYPE: skip past it.
            end = text.find(">", start)
            if end < 0:
                return False
            index = end + 1
            continue
        name_end = start + 1
        while name_end < len(text) and (text[name_end].isalnum() or text[name_end] in "_-:."):
            name_end += 1
        tag = text[start + 1:name_end].split(":")[-1]
        rtnval = tag in ("testsuites", "testsuite")
        return rtnval


def _find_reports(*, tree_path: str, stop_after_first: bool) -> List[str]:
    """
        Relative paths of the JUnit reports in the tree, sorted.
    """
    found: List[str] = []
    sniffed = 0
    for root, dirs, files in os.walk(tree_path):
        dirs.sort()
        for fname in sorted(files):
            if fname.lower().endswith(".xml") is False:
                continue
            if sniffed >= MAX_FILES_SNIFFED:
                break
            sniffed += 1
            full_path = os.path.join(root, fname)
            if _sniff_is_report(full_path=full_path):
                found.append(os.path.relpath(full_path, start=tree_path))
                if stop_after_first is True:
                    return found
    rtnval = sorted(found)
    return rtnval


# ---------------------------------------------------------------------------
# Parsing one report
# ---------------------------------------------------------------------------


def _local(tag: Any) -> str:
    """
        An element's tag without any namespace.
    """
    text = str(tag)
    if "}" in text:
        text = text.split("}", 1)[1]
    rtnval = text
    return rtnval


def _seconds(value: Any) -> float:
    try:
        rtnval = float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        rtnval = 0.0
    if rtnval < 0:
        rtnval = 0.0
    return rtnval


def _timestamp(value: Any) -> Optional[datetime]:
    """
        A suite ``timestamp`` attribute as an aware datetime (naive
        values are UTC), or ``None``.
    """
    if value is None:
        return None
    text = str(value).strip()
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


def _clip(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    stripped = text.strip()
    if len(stripped) == 0:
        return None
    if len(stripped) > MAX_TEXT_CHARS:
        stripped = stripped[:MAX_TEXT_CHARS] + "\n... (truncated)"
    rtnval = stripped
    return rtnval


def _outcome(testcase: Any) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
        The testcase's result and, when it did not pass, the detail that
        explains it.
    """
    children = {}
    for child in list(testcase):
        children.setdefault(_local(child.tag), child)

    for tag, result in (("error", RESULT_ERRORED), ("failure", RESULT_FAILED)):
        element = children.get(tag, None)
        if element is not None:
            detail = {
                "kind": tag,
                "type": element.get("type"),
                "message": element.get("message"),
                "text": _clip(element.text),
            }
            return result, detail

    skipped = children.get("skipped", None)
    status = str(testcase.get("status", "") or "").lower()
    result_attr = str(testcase.get("result", "") or "").lower()
    if skipped is not None or status in ("notrun", "skipped", "disabled") or result_attr in ("skipped", "suppressed"):
        detail = None
        if skipped is not None:
            detail = {"kind": "skipped", "message": skipped.get("message"), "text": _clip(skipped.text)}
        return RESULT_SKIPPED, detail

    # Surefire records reruns: <rerunFailure>/<rerunError> without a final
    # <failure> still means every run failed, while <flakyFailure> /
    # <flakyError> alone means the test passed on a rerun.
    reruns = children.get("rerunFailure", None)
    if reruns is None:
        reruns = children.get("rerunError", None)
    if reruns is not None:
        detail = {
            "kind": _local(reruns.tag),
            "type": reruns.get("type"),
            "message": reruns.get("message"),
            "text": _clip(reruns.text),
        }
        return RESULT_FAILED, detail

    flaky = [child for child in list(testcase) if _local(child.tag) in ("flakyFailure", "flakyError")]
    if len(flaky) > 0:
        detail = {
            "kind": "flaky",
            "type": flaky[0].get("type"),
            "message": flaky[0].get("message"),
            "failed_attempts": len(flaky),
        }
        return RESULT_PASSED, detail

    return RESULT_PASSED, None


def _iter_suites(element: Any, *, path: Tuple[str, ...]) -> List[Tuple[Any, Tuple[str, ...]]]:
    """
        Every ``<testsuite>`` under ``element`` (including nested suites)
        with the chain of suite names leading to it.
    """
    found: List[Tuple[Any, Tuple[str, ...]]] = []
    for child in list(element):
        if _local(child.tag) == "testsuite":
            name = str(child.get("name", "") or "")
            chain = path + ((name,) if len(name) > 0 else tuple())
            found.append((child, chain))
            found.extend(_iter_suites(child, path=chain))
    return found


def _parse_report(*, full_path: str, relative: str) -> Tuple[List[ParsedTaskResult], List[datetime], float]:
    """
        Parse one report into task results, its suites' start times and
        the total test time it records.
    """
    if os.path.getsize(full_path) > MAX_REPORT_BYTES:
        raise JUnitReportRefusedError(
            "report is larger than {} MB".format(MAX_REPORT_BYTES // (1024 * 1024))
        )
    with open(full_path, "rb") as fh:
        blob = fh.read()
    if b"<!DOCTYPE" in blob or b"<!ENTITY" in blob:
        raise JUnitReportRefusedError("report declares a DOCTYPE or entities")
    root = ElementTree.fromstring(blob)

    suites: List[Tuple[Any, Tuple[str, ...]]] = []
    if _local(root.tag) == "testsuite":
        name = str(root.get("name", "") or "")
        chain = (name,) if len(name) > 0 else tuple()
        suites.append((root, chain))
        suites.extend(_iter_suites(root, path=chain))
    else:
        suites.extend(_iter_suites(root, path=tuple()))

    tasks: List[ParsedTaskResult] = []
    starts: List[datetime] = []
    total_seconds = 0.0
    position = 0
    for suite, chain in suites:
        suite_start = _timestamp(suite.get("timestamp"))
        if suite_start is not None:
            starts.append(suite_start)
        offset = 0.0
        for testcase in list(suite):
            if _local(testcase.tag) != "testcase":
                continue
            position += 1
            name = str(testcase.get("name", "") or "")
            classname = str(testcase.get("classname", "") or "")
            test_name = "{}.{}".format(classname, name) if len(classname) > 0 else name
            if len(test_name) == 0:
                test_name = "{} #{}".format(".".join(chain) or relative, position)
            seconds = _seconds(testcase.get("time"))
            total_seconds += seconds
            result, detail = _outcome(testcase)

            started_at: Optional[datetime] = None
            finished_at: Optional[datetime] = None
            if suite_start is not None:
                started_at = suite_start + timedelta(seconds=offset)
                finished_at = started_at + timedelta(seconds=seconds)
            offset += seconds

            raw: Dict[str, Any] = {
                "format": JUNIT_XML_PARSER_TAG,
                "report": relative,
                "suite": ".".join(chain),
                "classname": classname,
                "name": name,
                "time": seconds,
            }
            for attribute in ("file", "line"):
                if testcase.get(attribute) is not None:
                    raw[attribute] = testcase.get(attribute)
            if detail is not None:
                raw["detail"] = detail
            for stream_tag, key in (("system-out", "stdout"), ("system-err", "stderr")):
                stream = testcase.find(stream_tag)
                if stream is not None and _clip(stream.text) is not None:
                    raw[key] = _clip(stream.text)

            task_id = uuid.uuid5(_TASK_ID_NAMESPACE, "{}\x1f{}\x1f{}".format(relative, position, test_name))
            tasks.append(ParsedTaskResult(
                instance_uuid=str(task_id),
                test_name=test_name[:MAX_TEST_NAME_CHARS],
                rtype="TEST",
                result=result,
                started_at=started_at,
                finished_at=finished_at,
                raw=raw,
            ))
    rtnval = (tasks, starts, total_seconds)
    return rtnval


# ---------------------------------------------------------------------------
# Summary and artifacts
# ---------------------------------------------------------------------------


def _summarize(
        *,
        tasks: List[ParsedTaskResult],
        suite_starts: List[datetime],
        total_seconds: float,
        parsed_reports: List[str],
        refused_reports: List[Dict[str, str]]
    ) -> ParsedSummary:
    """
        Roll the task results up. Counts come from the test cases, not
        the reports' own (often stale or absent) count attributes.
    """
    counts = {RESULT_PASSED: 0, RESULT_FAILED: 0, RESULT_SKIPPED: 0, RESULT_ERRORED: 0}
    for task in tasks:
        counts[task.result] = counts.get(task.result, 0) + 1
    started_at = min(suite_starts) if len(suite_starts) > 0 else None
    finished_at = None
    if started_at is not None:
        latest_finish = [task.finished_at for task in tasks if task.finished_at is not None]
        finished_at = max(latest_finish) if len(latest_finish) > 0 else started_at + timedelta(seconds=total_seconds)
    raw: Dict[str, Any] = {
        "format": JUNIT_XML_PARSER_TAG,
        "reports": parsed_reports,
        "test_seconds": round(total_seconds, 3),
        "detail": {
            "total": len(tasks),
            "passed": counts[RESULT_PASSED],
            "failed": counts[RESULT_FAILED],
            "skipped": counts[RESULT_SKIPPED],
            "errors": counts[RESULT_ERRORED],
        },
    }
    if len(refused_reports) > 0:
        raw["refused_reports"] = refused_reports
    rtnval = ParsedSummary(
        tests_total=len(tasks),
        tests_passed=counts[RESULT_PASSED],
        tests_failed=counts[RESULT_FAILED],
        tests_skipped=counts[RESULT_SKIPPED],
        tests_errored=counts[RESULT_ERRORED],
        started_at=started_at,
        finished_at=finished_at,
        raw=raw,
    )
    return rtnval


def _catalogue(*, tree_path: str, reports: set) -> Tuple[List[ParsedArtifact], int]:
    """
        Every regular file in the tree as an artifact; the JUnit reports
        themselves are classified as the run's summary.
    """
    artifacts: List[ParsedArtifact] = []
    files_seen = 0
    for root, _dirs, files in os.walk(tree_path):
        for fname in files:
            files_seen += 1
            full_path = os.path.join(root, fname)
            try:
                size = os.path.getsize(full_path)
            except OSError:
                size = 0
            relative = os.path.relpath(full_path, start=tree_path)
            content_type, _ = mimetypes.guess_type(full_path)
            artifacts.append(ParsedArtifact(
                relative_path=relative,
                classification=REPORT_CLASSIFICATION if relative in reports else ARTIFACT_CLASSIFICATION,
                size_bytes=int(size),
                content_type=content_type,
            ))
    rtnval = (artifacts, files_seen)
    return rtnval
