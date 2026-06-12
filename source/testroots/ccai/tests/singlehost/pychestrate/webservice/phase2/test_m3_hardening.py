"""
.. module:: test_m3_hardening
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Cross-cutting tests for the shared Layer-2 M3 infrastructure.

.. moduleauthor:: Code Craft AI LLC
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from ccai import testbase

from ccai.errors.exceptions import ConfigurationError

from ccai.pychestrate.webservice.hardening import metrics as hardening_metrics
from ccai.pychestrate.webservice.hardening import rate_limit as hardening_rate_limit
from ccai.pychestrate.webservice.hardening.collisions import check_unique_identifiers
from ccai.pychestrate.webservice.hardening.rate_limit import RateLimitExceeded


class _A:
    field_name = "a"


class _B:
    field_name = "b"


class _DupeA:
    field_name = "a"


def test_collisions_helper_rejects_duplicates():
    """
    **Feature: shared M3**
    **Property: check_unique_identifiers raises ConfigurationError on a
    duplicate identifier.**
    """
    raised = False
    try:
        check_unique_identifiers(
            packs=[_A, _B, _DupeA],
            identifier_attribute="field_name",
            category_label="TestPack",
        )
    except ConfigurationError:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_collisions_helper_accepts_unique():
    """
    **Feature: shared M3**
    **Property: check_unique_identifiers returns a mapping when every
    identifier is unique.**
    """
    mapping = check_unique_identifiers(
        packs=[_A, _B],
        identifier_attribute="field_name",
        category_label="TestPack",
    )
    testbase.assert_equal(sorted(mapping.keys()), ["a", "b"])
    return


def test_rate_limiter_blocks_after_capacity():
    """
    **Feature: shared M3**
    **Property: rate_limit.acquire raises RateLimitExceeded once the
    bucket is empty.**
    """
    hardening_rate_limit.reset_for_testing()
    for _ in range(3):
        hardening_rate_limit.acquire(
            scope_name="test", scope_key="k", capacity=3, refill_per_second=0.0001,
        )

    raised = False
    try:
        hardening_rate_limit.acquire(
            scope_name="test", scope_key="k", capacity=3, refill_per_second=0.0001,
        )
    except RateLimitExceeded:
        raised = True
    testbase.assert_equal(raised, True)
    return


def test_metrics_counter_and_samples():
    """
    **Feature: shared M3**
    **Property: increment_counter and record_latency accumulate state.**
    """
    hardening_metrics.reset_for_testing()
    hardening_metrics.increment_counter(name="test.ok", labels={}, by=2)
    hardening_metrics.increment_counter(name="test.ok", labels={})
    hardening_metrics.record_latency(name="test.latency", latency_ms=12.5)

    testbase.assert_equal(hardening_metrics.counter_value(name="test.ok", labels={}), 3)
    testbase.assert_equal(hardening_metrics.sample_count(name="test.latency"), 1)
    return
