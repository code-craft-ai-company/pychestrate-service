"""
.. module:: test_p16b_messaging_overflow_m2
    :synopsis: Tests for P16b — 0-message-bus M2 overflow policies.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.messaging.overflow import (
    BoundedQueue,
    OfferOutcome,
    OverflowPolicy,
)


# -------------------------------------
# Construction
# -------------------------------------

def test_bounded_queue_rejects_non_positive_maxsize():
    """
    **Feature: 0-message-bus (M2)**
    **Property: BoundedQueue rejects maxsize <= 0 with
    ValueError so caller misuse surfaces loudly.**
    """
    raised_zero = False
    raised_neg = False
    try:
        BoundedQueue(maxsize=0, policy=OverflowPolicy.DROP_OLDEST)
    except ValueError:
        raised_zero = True
    try:
        BoundedQueue(maxsize=-1, policy=OverflowPolicy.DROP_OLDEST)
    except ValueError:
        raised_neg = True
    testbase.assert_equal(raised_zero, True)
    testbase.assert_equal(raised_neg, True)
    return


def test_bounded_queue_starts_empty():
    """
    **Feature: 0-message-bus (M2)**
    **Property: a fresh BoundedQueue is empty and not full.**
    """
    queue = BoundedQueue(maxsize=3, policy=OverflowPolicy.DROP_OLDEST)
    testbase.assert_equal(queue.size(), 0)
    testbase.assert_equal(queue.is_empty(), True)
    testbase.assert_equal(queue.is_full(), False)
    return


# -------------------------------------
# Offer + pop_oldest under capacity
# -------------------------------------

def test_offer_below_capacity_accepts():
    """
    **Feature: 0-message-bus (M2)**
    **Property: offers below the queue's maxsize are
    accepted and observed in the snapshot.**
    """
    queue = BoundedQueue(maxsize=3, policy=OverflowPolicy.DROP_OLDEST)
    outcome_one = queue.offer(event="a")
    outcome_two = queue.offer(event="b")
    testbase.assert_equal(outcome_one.accepted, True)
    testbase.assert_equal(outcome_two.accepted, True)
    testbase.assert_equal(queue.snapshot(), ["a", "b"])
    return


def test_pop_oldest_drains_in_fifo_order():
    """
    **Feature: 0-message-bus (M2)**
    **Property: pop_oldest returns events in insertion order;
    returns None on empty.**
    """
    queue = BoundedQueue(maxsize=3, policy=OverflowPolicy.DROP_OLDEST)
    queue.offer(event="a")
    queue.offer(event="b")
    queue.offer(event="c")
    testbase.assert_equal(queue.pop_oldest(), "a")
    testbase.assert_equal(queue.pop_oldest(), "b")
    testbase.assert_equal(queue.pop_oldest(), "c")
    testbase.assert_equal(queue.pop_oldest(), None)
    return


# -------------------------------------
# DROP_OLDEST policy
# -------------------------------------

def test_drop_oldest_evicts_head_and_appends_new():
    """
    **Feature: 0-message-bus (M2)**
    **Property: under DROP_OLDEST, an offer to a full queue
    drops the head and appends the new event. Outcome
    carries accepted=True + dropped=True + the evicted
    event.**
    """
    queue = BoundedQueue(maxsize=2, policy=OverflowPolicy.DROP_OLDEST)
    queue.offer(event="a")
    queue.offer(event="b")
    outcome = queue.offer(event="c")
    testbase.assert_equal(outcome.accepted, True)
    testbase.assert_equal(outcome.dropped, True)
    testbase.assert_equal(outcome.dropped_event, "a")
    testbase.assert_equal(queue.snapshot(), ["b", "c"])
    return


def test_drop_oldest_can_evict_repeatedly():
    """
    **Feature: 0-message-bus (M2)**
    **Property: repeated DROP_OLDEST offers continue to
    evict the head — the queue length stays at maxsize and
    the snapshot shows the most recent N events.**
    """
    queue = BoundedQueue(maxsize=2, policy=OverflowPolicy.DROP_OLDEST)
    for letter in ("a", "b", "c", "d", "e"):
        queue.offer(event=letter)
    testbase.assert_equal(queue.snapshot(), ["d", "e"])
    return


# -------------------------------------
# DROP_NEWEST policy
# -------------------------------------

def test_drop_newest_rejects_new_when_full():
    """
    **Feature: 0-message-bus (M2)**
    **Property: under DROP_NEWEST, an offer to a full queue
    rejects the new event and leaves the buffer untouched.
    Outcome carries accepted=False + dropped=True + the new
    event as the sacrificed one.**
    """
    queue = BoundedQueue(maxsize=2, policy=OverflowPolicy.DROP_NEWEST)
    queue.offer(event="a")
    queue.offer(event="b")
    outcome = queue.offer(event="c")
    testbase.assert_equal(outcome.accepted, False)
    testbase.assert_equal(outcome.dropped, True)
    testbase.assert_equal(outcome.dropped_event, "c")
    testbase.assert_equal(queue.snapshot(), ["a", "b"])
    return


def test_drop_newest_recovers_after_pop():
    """
    **Feature: 0-message-bus (M2)**
    **Property: popping an event from a DROP_NEWEST queue
    frees a slot — the next offer is accepted normally.**
    """
    queue = BoundedQueue(maxsize=2, policy=OverflowPolicy.DROP_NEWEST)
    queue.offer(event="a")
    queue.offer(event="b")
    queue.pop_oldest()
    outcome = queue.offer(event="c")
    testbase.assert_equal(outcome.accepted, True)
    testbase.assert_equal(outcome.dropped, False)
    testbase.assert_equal(queue.snapshot(), ["b", "c"])
    return


# -------------------------------------
# BLOCK_PUBLISHER policy
# -------------------------------------

def test_block_publisher_signals_would_block_when_full():
    """
    **Feature: 0-message-bus (M2)**
    **Property: under BLOCK_PUBLISHER, an offer to a full
    queue returns OfferOutcome(would_block=True) and leaves
    the buffer untouched. The dispatcher wraps this in a
    real waiter for the production path.**
    """
    queue = BoundedQueue(maxsize=2, policy=OverflowPolicy.BLOCK_PUBLISHER)
    queue.offer(event="a")
    queue.offer(event="b")
    outcome = queue.offer(event="c")
    testbase.assert_equal(outcome.accepted, False)
    testbase.assert_equal(outcome.would_block, True)
    testbase.assert_equal(outcome.dropped, False)
    testbase.assert_equal(queue.snapshot(), ["a", "b"])
    return


def test_block_publisher_accepts_after_slot_frees():
    """
    **Feature: 0-message-bus (M2)**
    **Property: a BLOCK_PUBLISHER queue accepts the next
    offer once a slot is popped — try_offer recovers without
    needing a thread.**
    """
    queue = BoundedQueue(maxsize=2, policy=OverflowPolicy.BLOCK_PUBLISHER)
    queue.offer(event="a")
    queue.offer(event="b")
    testbase.assert_equal(queue.try_offer(event="c"), False)
    queue.pop_oldest()
    testbase.assert_equal(queue.try_offer(event="c"), True)
    testbase.assert_equal(queue.snapshot(), ["b", "c"])
    return


# -------------------------------------
# Outcome shape
# -------------------------------------

def test_offer_outcome_default_flags_are_false():
    """
    **Feature: 0-message-bus (M2)**
    **Property: OfferOutcome has accepted/dropped/would_block
    flags that default to False; only accepted is required.**
    """
    outcome = OfferOutcome(accepted=True)
    testbase.assert_equal(outcome.accepted, True)
    testbase.assert_equal(outcome.dropped, False)
    testbase.assert_equal(outcome.would_block, False)
    testbase.assert_equal(outcome.dropped_event, None)
    return


# -------------------------------------
# Read helpers
# -------------------------------------

def test_size_and_is_full_track_offers_and_pops():
    """
    **Feature: 0-message-bus (M2)**
    **Property: size and is_full reflect the queue's state
    across offers and pops.**
    """
    queue = BoundedQueue(maxsize=3, policy=OverflowPolicy.DROP_OLDEST)
    testbase.assert_equal(queue.size(), 0)
    queue.offer(event="a")
    testbase.assert_equal(queue.size(), 1)
    testbase.assert_equal(queue.is_full(), False)
    queue.offer(event="b")
    queue.offer(event="c")
    testbase.assert_equal(queue.size(), 3)
    testbase.assert_equal(queue.is_full(), True)
    queue.pop_oldest()
    testbase.assert_equal(queue.size(), 2)
    testbase.assert_equal(queue.is_full(), False)
    return


def test_maxsize_and_policy_accessors_return_constructor_values():
    """
    **Feature: 0-message-bus (M2)**
    **Property: maxsize() and policy() return the values
    supplied at construction time.**
    """
    queue = BoundedQueue(
        maxsize=7, policy=OverflowPolicy.DROP_NEWEST,
    )
    testbase.assert_equal(queue.maxsize(), 7)
    testbase.assert_equal(queue.policy(), OverflowPolicy.DROP_NEWEST)
    return
