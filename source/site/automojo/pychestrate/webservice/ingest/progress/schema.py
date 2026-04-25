"""
.. module:: ingest.progress.schema
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Caller-facing IO shapes for forwarded progress.

.. moduleauthor:: Automation Mojo LLC

The shapes mirror testbase's ``ForwardingInfo`` /
``ProgressConcentratorServer`` contract so an unmodified testbase
client posts directly without translation.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional


@dataclass(frozen=True)
class ProgressSummary:
    """
        Roll-up the client emits at intervals (and once at the end).

        :param run_id: Run UUID.
        :param client_id: Client UUID that posted the summary.
        :param format_tag: Parser tag that resolves a registered
                           ``progress_parser`` (``"testbase"`` for
                           the in-tree default).
        :param tests_total: Total tests planned, or ``None`` when
                            the test pass has not finished
                            collection.
        :param tests_passed: Count of tests reported PASSED so far.
        :param tests_failed: Count of tests reported FAILED so far.
        :param tests_skipped: Count of SKIPPED tests so far.
        :param tests_errored: Count of ERRORED tests so far.
        :param percent_complete: Optional float in [0.0, 100.0].
        :param notes: Optional free-form note string.
        :param recorded_at: UTC timestamp the client minted the
                            summary.
        :param raw: Untyped dict passthrough so the parser can
                    capture any extras it cares about without
                    schema churn.
    """
    run_id: str
    client_id: str
    format_tag: str
    tests_total: Optional[int]
    tests_passed: int
    tests_failed: int
    tests_skipped: int
    tests_errored: int
    percent_complete: Optional[float]
    notes: Optional[str]
    recorded_at: datetime
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class ProgressRecord:
    """
        One progress record from the testbase
        ``testrun_results_stream.jsos`` shape — represents one test
        scope completion (or preview).

        :param run_id: Run UUID.
        :param client_id: Client UUID.
        :param record_index: Monotonically-increasing index of the
                             record within the run's stream.
        :param test_name: Fully-qualified test name string.
        :param result: Result string (``"PASSED"``, ``"FAILED"``,
                       ``"SKIPPED"``, ``"ERRORED"``, ``"UNSET"``).
        :param started_at: UTC start timestamp from the record.
        :param finished_at: UTC stop timestamp; ``None`` when the
                            record is a preview.
        :param duration_seconds: Optional float duration.
        :param raw: Untyped dict passthrough.
    """
    run_id: str
    client_id: str
    record_index: int
    test_name: str
    result: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_seconds: Optional[float]
    raw: Mapping[str, Any]
