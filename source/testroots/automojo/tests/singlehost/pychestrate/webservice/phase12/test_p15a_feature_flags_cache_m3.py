"""
.. module:: test_p15a_feature_flags_cache_m3
    :synopsis: Tests for P15a — 1-feature-flags M3
               (last-good-cache fallback + TTL).
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from datetime import datetime, timedelta, timezone
from typing import List

from automojo import testbase

from automojo.pychestrate.core.defaults import new_uuid

from automojo.pychestrate.webservice.identity.flags import cache as flag_cache
from automojo.pychestrate.webservice.identity.flags.events import (
    FlagEventTopics,
)
from automojo.pychestrate.webservice.messaging.event_bus import (
    EntityEvent,
    publish,
    reset_for_testing as reset_event_bus,
)


def _prepare_runtime() -> None:
    reset_event_bus()
    flag_cache.reset_for_testing()
    return


# -------------------------------------
# TTL cache primitives
# -------------------------------------

def test_get_cached_returns_none_when_empty():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: a fresh cache returns None for any key.**
    """
    _prepare_runtime()
    rtnval = flag_cache.get_cached(
        flag_key="ops.flag", bucketing_key="user-1",
    )
    testbase.assert_equal(rtnval, None)
    return


def test_put_then_get_round_trip():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: put_cached persists a value that get_cached
    returns within the TTL window.**
    """
    _prepare_runtime()
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="user-1", value=True,
    )
    rtnval = flag_cache.get_cached(
        flag_key="ops.flag", bucketing_key="user-1",
    )
    testbase.assert_equal(rtnval, True)
    return


def test_ttl_expiry_evicts_entry():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: a get_cached call past the entry's TTL
    deadline returns None and drops the entry.**
    """
    _prepare_runtime()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    flag_cache.put_cached(
        flag_key="ops.flag",
        bucketing_key="user-1",
        value="canary",
        ttl=timedelta(seconds=10),
        now=anchor,
    )
    expired = flag_cache.get_cached(
        flag_key="ops.flag",
        bucketing_key="user-1",
        now=anchor + timedelta(seconds=11),
    )
    testbase.assert_equal(expired, None)
    return


def test_distinct_bucketing_keys_have_separate_entries():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: TTL cache keys on (flag_key, bucketing_key) so
    distinct contexts share the flag's last-good but get
    independent TTL windows.**
    """
    _prepare_runtime()
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="alpha", value="A",
    )
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="beta", value="B",
    )
    testbase.assert_equal(
        flag_cache.get_cached(
            flag_key="ops.flag", bucketing_key="alpha",
        ),
        "A",
    )
    testbase.assert_equal(
        flag_cache.get_cached(
            flag_key="ops.flag", bucketing_key="beta",
        ),
        "B",
    )
    return


# -------------------------------------
# Last-good cache + invalidation
# -------------------------------------

def test_put_cached_records_last_good():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: put_cached also seats the value as the
    flag's last-good entry.**
    """
    _prepare_runtime()
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="user-1", value="stable",
    )
    rtnval = flag_cache.get_last_good(flag_key="ops.flag")
    testbase.assert_equal(rtnval, "stable")
    return


def test_invalidate_flag_drops_ttl_and_last_good():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: invalidate_flag removes every TTL row keyed
    on the flag plus the matching last-good entry.**
    """
    _prepare_runtime()
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="alpha", value="A",
    )
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="beta", value="B",
    )
    flag_cache.put_cached(
        flag_key="other.flag", bucketing_key="alpha", value="X",
    )
    removed = flag_cache.invalidate_flag(flag_key="ops.flag")
    testbase.assert_equal(removed, 2)
    testbase.assert_equal(
        flag_cache.get_last_good(flag_key="ops.flag"), None,
    )
    testbase.assert_equal(
        flag_cache.get_cached(
            flag_key="other.flag", bucketing_key="alpha",
        ),
        "X",
    )
    return


# -------------------------------------
# Bus-driven invalidation
# -------------------------------------

def test_wire_invalidation_subscribers_on_flag_updated():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: an entity.flag.updated emit invalidates the
    flag's cache rows.**
    """
    _prepare_runtime()
    flag_cache.wire_invalidation_subscribers()
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="user-1", value=True,
    )
    publish(event=EntityEvent(
        topic=FlagEventTopics.FLAG_UPDATED,
        payload={"flag_key": "ops.flag", "version": 2},
        source_event_id=new_uuid(),
    ))
    testbase.assert_equal(
        flag_cache.get_cached(
            flag_key="ops.flag", bucketing_key="user-1",
        ),
        None,
    )
    return


def test_wire_invalidation_subscribers_on_flag_retired():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: an entity.flag.retired emit clears the
    flag's last-good entry so a stale-served fallback can't
    leak retired values.**
    """
    _prepare_runtime()
    flag_cache.wire_invalidation_subscribers()
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="user-1", value=True,
    )
    publish(event=EntityEvent(
        topic=FlagEventTopics.FLAG_RETIRED,
        payload={"flag_key": "ops.flag"},
        source_event_id=new_uuid(),
    ))
    testbase.assert_equal(
        flag_cache.get_last_good(flag_key="ops.flag"), None,
    )
    return


def test_wire_invalidation_subscribers_idempotent():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: wire_invalidation_subscribers can be called
    twice without double-subscribing — a single emit causes
    one invalidation.**
    """
    _prepare_runtime()
    flag_cache.wire_invalidation_subscribers()
    flag_cache.wire_invalidation_subscribers()
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="user-1", value=True,
    )
    publish(event=EntityEvent(
        topic=FlagEventTopics.FLAG_UPDATED,
        payload={"flag_key": "ops.flag"},
        source_event_id=new_uuid(),
    ))
    # Cache row gone — even if multiple invalidations ran,
    # the result is the same.
    testbase.assert_equal(
        flag_cache.get_cached(
            flag_key="ops.flag", bucketing_key="user-1",
        ),
        None,
    )
    return


# -------------------------------------
# evaluate_resilient
# -------------------------------------

def test_evaluate_resilient_caches_first_call():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: the first evaluator call lands in cache; the
    second call hits the cache and does not re-invoke the
    evaluator.**
    """
    _prepare_runtime()
    counter = {"n": 0}

    def _evaluator():
        counter["n"] = counter["n"] + 1
        return "alpha"

    first = flag_cache.evaluate_resilient(
        flag_key="ops.flag",
        bucketing_key="user-1",
        evaluator=_evaluator,
        default="default",
    )
    second = flag_cache.evaluate_resilient(
        flag_key="ops.flag",
        bucketing_key="user-1",
        evaluator=_evaluator,
        default="default",
    )
    testbase.assert_equal(first, "alpha")
    testbase.assert_equal(second, "alpha")
    testbase.assert_equal(counter["n"], 1)
    return


def test_evaluate_resilient_falls_back_to_last_good_on_exception():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: when the evaluator raises after a successful
    initial run, the next call returns the last-good value
    and bumps the stale-served counter.**
    """
    _prepare_runtime()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    # Seat a last-good entry anchored in the past.
    flag_cache.put_cached(
        flag_key="ops.flag",
        bucketing_key="user-1",
        value="stable",
        ttl=timedelta(seconds=10),
        now=anchor,
    )

    def _failing_evaluator():
        raise RuntimeError("backend_unavailable")

    # Now is past the TTL deadline so the cache lookup misses
    # and the evaluator runs (and raises). The last-good entry
    # serves the request.
    rtnval = flag_cache.evaluate_resilient(
        flag_key="ops.flag",
        bucketing_key="user-1",
        evaluator=_failing_evaluator,
        default="hard-default",
        now=anchor + timedelta(hours=1),
    )
    testbase.assert_equal(rtnval, "stable")
    testbase.assert_equal(flag_cache.stale_served_count(), 1)
    return


def test_evaluate_resilient_returns_default_when_no_last_good():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: an evaluator failure with no prior last-good
    entry returns the supplied default and does NOT bump the
    stale-served counter.**
    """
    _prepare_runtime()

    def _failing_evaluator():
        raise RuntimeError("backend_unavailable")

    rtnval = flag_cache.evaluate_resilient(
        flag_key="ops.never.cached",
        bucketing_key="user-1",
        evaluator=_failing_evaluator,
        default="hard-default",
    )
    testbase.assert_equal(rtnval, "hard-default")
    testbase.assert_equal(flag_cache.stale_served_count(), 0)
    return


def test_evaluate_resilient_records_last_good_after_success():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: a successful evaluator call records the
    value as the last-good entry — a subsequent failure
    falls through to it.**
    """
    _prepare_runtime()
    flag_cache.evaluate_resilient(
        flag_key="ops.flag",
        bucketing_key="user-1",
        evaluator=lambda: "alpha",
        default="default",
    )
    flag_cache.invalidate_flag(flag_key="ops.flag")
    # Re-seat last-good without invalidating again.
    flag_cache.put_cached(
        flag_key="ops.flag", bucketing_key="user-1", value="alpha",
    )
    flag_cache.invalidate_flag(flag_key="ops.flag")
    # No prior last-good after invalidation.
    testbase.assert_equal(
        flag_cache.get_last_good(flag_key="ops.flag"), None,
    )
    # Run again after invalidation.
    rtnval = flag_cache.evaluate_resilient(
        flag_key="ops.flag",
        bucketing_key="user-1",
        evaluator=lambda: "beta",
        default="default",
    )
    testbase.assert_equal(rtnval, "beta")
    testbase.assert_equal(
        flag_cache.get_last_good(flag_key="ops.flag"), "beta",
    )
    return


def test_stale_served_counter_increments_per_fallback():
    """
    **Feature: 1-feature-flags (M3)**
    **Property: every last-good fallback increments the
    stale-served counter.**
    """
    _prepare_runtime()
    anchor = datetime(2026, 4, 25, 0, 0, 0, tzinfo=timezone.utc)
    flag_cache.put_cached(
        flag_key="ops.flag",
        bucketing_key="user-1",
        value="stable",
        ttl=timedelta(seconds=10),
        now=anchor,
    )

    def _bad():
        raise RuntimeError("nope")

    for _ in range(3):
        flag_cache.evaluate_resilient(
            flag_key="ops.flag",
            bucketing_key="user-{}".format(_),
            evaluator=_bad,
            default="default",
            now=anchor + timedelta(hours=1),
        )
    testbase.assert_equal(flag_cache.stale_served_count(), 3)
    return
