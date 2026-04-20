"""
.. module:: test_messaging_bus
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests for the in-process event bus + outbox helpers.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.messaging import event_bus
from automojo.pychestrate.webservice.messaging.event_bus import EntityEvent, publish, reset_for_testing, subscribe, unsubscribe


def test_publish_delivers_synchronously():
    """
    **Feature: 0-message-bus (stub)**
    **Property: Published events deliver to subscribers in order.**
    """
    reset_for_testing()
    received = []

    def _handler(evt: EntityEvent) -> None:
        received.append(evt)
        return

    subscribe(topic="entity.test.alpha", subscriber=_handler)

    publish(event=EntityEvent(topic="entity.test.alpha", payload={"seq": 1}, source_event_id="e1"))
    publish(event=EntityEvent(topic="entity.test.alpha", payload={"seq": 2}, source_event_id="e2"))

    testbase.assert_equal(len(received), 2)
    testbase.assert_equal(received[0].payload["seq"], 1)
    testbase.assert_equal(received[1].payload["seq"], 2)
    return


def test_unsubscribe_stops_delivery():
    """
    **Feature: 0-message-bus (stub)**
    **Property: An unsubscribed handler no longer receives events.**
    """
    reset_for_testing()
    received = []

    def _handler(evt: EntityEvent) -> None:
        received.append(evt)
        return

    subscribe(topic="entity.test.beta", subscriber=_handler)
    publish(event=EntityEvent(topic="entity.test.beta", payload={}, source_event_id="e1"))
    unsubscribe(topic="entity.test.beta", subscriber=_handler)
    publish(event=EntityEvent(topic="entity.test.beta", payload={}, source_event_id="e2"))

    testbase.assert_equal(len(received), 1)
    return


def test_subscriber_exception_does_not_block_other_subscribers():
    """
    **Feature: 0-message-bus (stub)**
    **Property: A faulted subscriber is isolated; delivery continues.**
    """
    reset_for_testing()
    delivered = []

    def _bad(evt: EntityEvent) -> None:
        raise RuntimeError("simulated subscriber failure")

    def _good(evt: EntityEvent) -> None:
        delivered.append(evt)
        return

    subscribe(topic="entity.test.gamma", subscriber=_bad)
    subscribe(topic="entity.test.gamma", subscriber=_good)

    publish(event=EntityEvent(topic="entity.test.gamma", payload={}, source_event_id="e1"))

    testbase.assert_equal(len(delivered), 1)
    return


def test_unknown_topic_is_a_noop():
    """
    **Feature: 0-message-bus (stub)**
    **Property: Publishing to a topic with no subscribers does not raise.**
    """
    reset_for_testing()
    # Should not raise.
    publish(event=EntityEvent(topic="entity.test.no_listeners", payload={}, source_event_id="e1"))
    return
