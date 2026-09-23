"""
.. module:: test_p40i_junit_result_ingest_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for ingesting JUnit / xUnit XML result trees.

.. moduleauthor:: Code Craft AI LLC

Audit finding ORG-F12: result ingestion understood only testbase trees,
so teams using pytest, Surefire, GoogleTest, Go or Jest could not bring
their results. A JUnit XML parser now sits next to testbase-v1, and the
scanner picks whichever parser recognizes the tree.

**Feature: result ingest (ORG-F12 JUnit/xUnit)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import os
import shutil
import tempfile

from typing import Dict, List, Tuple

from ccai import testbase

from ccai.pychestrate.core.defaults import new_uuid
from ccai.pychestrate.webservice.extensions.registry import reset_registry_for_testing
from ccai.pychestrate.webservice.ingest.result import (
    register_builtin_extensions as result_register,
    scan_once,
)
from ccai.pychestrate.webservice.ingest.result import scanner
from ccai.pychestrate.webservice.ingest.result.factories.junit_xml import (
    JUNIT_XML_PARSER_TAG,
    JUnitXmlResultTreeParser,
)
from ccai.pychestrate.webservice.ingest.result.factories.testbase_v1 import (
    TESTBASE_V1_PARSER_TAG,
)
from ccai.pychestrate.webservice.ingest.result.models import (
    RunArtifact,
    RunResultSummary,
    TaskResult,
)
from ccai.pychestrate.webservice.jobs.run.state import create_run as create_run_state
from ccai.pychestrate.webservice.messaging.event_bus import reset_for_testing as reset_event_bus

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    session_for,
)


PROJECT_UUID = "00000000-0000-4000-8000-000000000420"

PYTEST_REPORT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites name="pytest tests">
  <testsuite name="pytest" errors="1" failures="1" skipped="1" tests="99" time="1.75"
             timestamp="2026-09-22T10:00:00.000000+00:00" hostname="ci-7">
    <testcase classname="tests.test_cart" name="test_add_item" time="0.25" file="tests/test_cart.py" line="10"/>
    <testcase classname="tests.test_cart" name="test_total" time="0.50">
      <failure message="assert 41 == 42" type="AssertionError">tests/test_cart.py:20: assert 41 == 42</failure>
      <system-out>computing total</system-out>
    </testcase>
    <testcase classname="tests.test_cart" name="test_checkout" time="1.00">
      <error message="fixture 'db' not found" type="pytest.fixture">E fixture 'db' not found</error>
    </testcase>
    <testcase classname="tests.test_cart" name="test_refund" time="0">
      <skipped type="pytest.skip" message="refunds disabled">tests/test_cart.py:40: refunds disabled</skipped>
    </testcase>
  </testsuite>
</testsuites>
"""

GTEST_REPORT = """<?xml version="1.0" encoding="UTF-8"?>
<!-- written by GoogleTest -->
<testsuites tests="2" failures="0" disabled="1" errors="0" time="0.01" timestamp="2026-09-22T10:05:00" name="AllTests">
  <testsuite name="MathTest" tests="2" failures="0" disabled="1" errors="0" time="0.01" timestamp="2026-09-22T10:05:00">
    <testcase name="Adds" status="run" result="completed" time="0.01" classname="MathTest"/>
    <testcase name="DISABLED_Divides" status="notrun" result="suppressed" time="0" classname="MathTest"/>
  </testsuite>
</testsuites>
"""

SUREFIRE_REPORT = """<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.acme.OrderTest" tests="2" failures="1" errors="0" skipped="0" time="3.0">
  <testcase name="shipsOnTime" classname="com.acme.OrderTest" time="1.0">
    <flakyFailure message="timeout" type="java.util.concurrent.TimeoutException">stack</flakyFailure>
  </testcase>
  <testcase name="billsTwice" classname="com.acme.OrderTest" time="2.0">
    <rerunFailure message="charged 2x" type="java.lang.AssertionError">stack</rerunFailure>
  </testcase>
</testsuite>
"""

NESTED_REPORT = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="outer">
    <testsuite name="inner">
      <testcase name="deep" classname="pkg.Deep" time="0.1"/>
    </testsuite>
  </testsuite>
</testsuites>
"""

DOCTYPE_REPORT = """<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol">]>
<testsuites><testsuite name="evil"><testcase name="t" classname="c">&lol;</testcase></testsuite></testsuites>
"""


def _tree(files: Dict[str, str]) -> str:
    root = tempfile.mkdtemp(prefix="p40i-junit-")
    for relative, content in files.items():
        full_path = os.path.join(root, relative)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return root


def _parse(files: Dict[str, str]) -> Tuple[object, str]:
    root = _tree(files)
    try:
        parsed = JUnitXmlResultTreeParser.parse_tree(tree_path=root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    rtnval = (parsed, root)
    return rtnval


def _results(files: Dict[str, str]) -> Dict[str, str]:
    parsed, _ = _parse(files)
    rtnval = {task.test_name: task.result for task in parsed.tasks}
    return rtnval


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_each_pytest_testcase_becomes_a_row_with_its_outcome():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: a pytest --junitxml report yields one row per testcase:
    passed, failed (<failure>), errored (<error>) and skipped (<skipped>).**
    """
    testbase.assert_equal(
        _results({"reports/junit.xml": PYTEST_REPORT}),
        {
            "tests.test_cart.test_add_item": "PASSED",
            "tests.test_cart.test_total": "FAILED",
            "tests.test_cart.test_checkout": "ERRORED",
            "tests.test_cart.test_refund": "SKIPPED",
        },
    )
    return


def test_a_failure_keeps_its_message_type_text_and_output():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: a failed test's row carries the failure message, type and
    text and the captured output, so it can be diagnosed from the row.**
    """
    parsed, _ = _parse({"junit.xml": PYTEST_REPORT})
    failed = [task for task in parsed.tasks if task.result == "FAILED"][0]
    testbase.assert_equal(
        (failed.raw["detail"]["message"], failed.raw["detail"]["type"], failed.raw["detail"]["text"],
         failed.raw["stdout"]),
        ("assert 41 == 42", "AssertionError", "tests/test_cart.py:20: assert 41 == 42", "computing total"),
    )
    return


def test_summary_counts_come_from_the_testcases_not_the_attributes():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: the run summary counts the testcases actually present
    (the report's tests="99" attribute is ignored) and starts at the
    suite timestamp.**
    """
    parsed, _ = _parse({"junit.xml": PYTEST_REPORT})
    summary = parsed.summary
    testbase.assert_equal(
        (summary.tests_total, summary.tests_passed, summary.tests_failed, summary.tests_errored,
         summary.tests_skipped, summary.started_at.isoformat()),
        (4, 1, 1, 1, 1, "2026-09-22T10:00:00+00:00"),
    )
    return


def test_a_googletest_disabled_test_is_skipped():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: GoogleTest's status="notrun" marks a test skipped, while a
    run test with no failure passed.**
    """
    testbase.assert_equal(
        _results({"gtest.xml": GTEST_REPORT}),
        {"MathTest.Adds": "PASSED", "MathTest.DISABLED_Divides": "SKIPPED"},
    )
    return


def test_surefire_flaky_tests_pass_and_rerun_failures_fail():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: a Surefire test with only flakyFailure entries passed on a
    rerun (and is marked flaky); one with rerunFailure entries failed.**
    """
    parsed, _ = _parse({"TEST-com.acme.OrderTest.xml": SUREFIRE_REPORT})
    by_name = {task.test_name: task for task in parsed.tasks}
    flaky = by_name["com.acme.OrderTest.shipsOnTime"]
    testbase.assert_equal(
        (flaky.result, flaky.raw["detail"]["kind"], by_name["com.acme.OrderTest.billsTwice"].result),
        ("PASSED", "flaky", "FAILED"),
    )
    return


def test_nested_suites_are_walked():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: testcases inside nested testsuites are found, with the
    suite chain recorded.**
    """
    parsed, _ = _parse({"nested.xml": NESTED_REPORT})
    testbase.assert_equal(
        [(task.test_name, task.raw["suite"]) for task in parsed.tasks], [("pkg.Deep.deep", "outer.inner")],
    )
    return


def test_a_report_declaring_a_doctype_is_refused():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: a report with a DOCTYPE (entity declarations) is not
    parsed; the summary records it as refused next to the good reports.**
    """
    parsed, _ = _parse({"a-good.xml": NESTED_REPORT, "b-evil.xml": DOCTYPE_REPORT})
    testbase.assert_equal(
        ([task.test_name for task in parsed.tasks],
         [entry["report"] for entry in parsed.summary.raw["refused_reports"]]),
        (["pkg.Deep.deep"], ["b-evil.xml"]),
    )
    return


def test_task_ids_are_stable_across_scans():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: parsing the same tree twice yields the same task ids, so
    a rescan updates rows instead of duplicating them.**
    """
    first, _ = _parse({"junit.xml": PYTEST_REPORT})
    second, _ = _parse({"junit.xml": PYTEST_REPORT})
    testbase.assert_equal(
        [task.instance_uuid for task in first.tasks], [task.instance_uuid for task in second.tasks],
    )
    return


# ---------------------------------------------------------------------------
# Choosing a parser
# ---------------------------------------------------------------------------


def test_the_scanner_picks_the_parser_that_recognizes_the_tree():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: with both parsers registered, a tree of JUnit reports is
    parsed as JUnit, a testbase tree as testbase, and a tree of neither
    falls back to testbase.**
    """
    reset_registry_for_testing()
    result_register()
    trees = {
        "junit": _tree({"out/junit.xml": PYTEST_REPORT}),
        "testbase": _tree({"testrun_summary.json": json.dumps({"detail": {"total": 0}}),
                           "out/junit.xml": PYTEST_REPORT}),
        "neither": _tree({"logs/build.log": "ok"}),
    }
    try:
        chosen = {name: scanner._resolve_parser(tree_path=root).parser_tag() for name, root in trees.items()}
    finally:
        for root in trees.values():
            shutil.rmtree(root, ignore_errors=True)
    testbase.assert_equal(
        chosen,
        {"junit": JUNIT_XML_PARSER_TAG, "testbase": TESTBASE_V1_PARSER_TAG, "neither": TESTBASE_V1_PARSER_TAG},
    )
    return


def test_scanning_a_junit_tree_stores_the_summary_tests_and_reports():
    """
    **Feature: result ingest (ORG-F12 JUnit/xUnit)**
    **Property: scan_once on a JUnit tree persists the run summary, one
    task row per testcase and the report as a summary artifact.**
    """
    reset_registry_for_testing()
    reset_event_bus()
    result_register()
    engine, session = build_in_memory_session()
    run_id = new_uuid()
    create_run_state(db_session=session, run_id=run_id, project_id=PROJECT_UUID, job_type="pytest")
    root = _tree({"reports/junit.xml": PYTEST_REPORT, "logs/pytest.log": "4 tests"})
    try:
        outcome = scan_once(db_session=session, run_id=run_id, tree_path=root)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    fresh = session_for(engine=engine)
    summary = fresh.query(RunResultSummary).filter(RunResultSummary.run_id == run_id).one()
    results: List[str] = sorted(row.result for row in fresh.query(TaskResult).filter(TaskResult.run_id == run_id))
    artifacts = {
        row.relative_path: row.classification
        for row in fresh.query(RunArtifact).filter(RunArtifact.run_id == run_id)
    }
    testbase.assert_equal(
        (outcome.parser_tag, summary.tests_total, summary.tests_failed, results, artifacts),
        (JUNIT_XML_PARSER_TAG, 4, 1, ["ERRORED", "FAILED", "PASSED", "SKIPPED"],
         {os.path.join("reports", "junit.xml"): "summary", os.path.join("logs", "pytest.log"): "artifact"}),
    )
    return
