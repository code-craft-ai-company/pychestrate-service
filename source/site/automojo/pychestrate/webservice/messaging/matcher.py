"""
.. module:: messaging.matcher
    :synopsis: Pure pattern matcher for the M2 wildcard topic surface.

The matcher implements the canonical Pychestrate topic
matching contract documented in ``0-message-bus`` M2:

* Topic strings are dot-separated: ``entity.user.created``,
  ``entity.run.completed.success``, ``system_health.probe.failed``.
* ``*`` in a pattern matches *exactly one* segment. So
  ``entity.*.created`` matches ``entity.user.created`` but
  not ``entity.org.user.created``.
* ``#`` in a pattern matches *zero or more* segments. So
  ``entity.#`` matches ``entity.user.created`` and
  ``entity`` itself.
* Literal segments must match exactly (case-sensitive).
* Empty pattern matches only the empty topic.

The matcher is a pure function with no I/O so it can be used
as a building block by the M2 bus dispatcher, by the test
surface, and by extension hooks that bind subscribers to
topic patterns instead of literal topics.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import List


SEGMENT_DELIMITER: str = "."
SINGLE_SEGMENT_WILDCARD: str = "*"
MULTI_SEGMENT_WILDCARD: str = "#"


def match_pattern(*, pattern: str, topic: str) -> bool:
    """
        Return ``True`` when ``topic`` matches ``pattern``
        under the canonical Pychestrate matching rules.

        :param pattern: Pattern string. May contain literal
                        segments, ``*`` (single-segment
                        wildcard), and ``#`` (multi-segment
                        wildcard).
        :param topic: Concrete topic string to match against.

        :returns: ``True`` on match, ``False`` otherwise.
    """
    if pattern is None or topic is None:
        return False
    pattern_segments = _split_segments(value=pattern)
    topic_segments = _split_segments(value=topic)
    rtnval = _match_segments(
        pattern_segments=pattern_segments,
        topic_segments=topic_segments,
    )
    return rtnval


def is_pattern(*, pattern: str) -> bool:
    """
        Return ``True`` when ``pattern`` contains at least
        one wildcard segment. Useful for callers that
        short-circuit the pattern path on literal-only
        subscriptions.
    """
    if pattern is None:
        return False
    for seg in _split_segments(value=pattern):
        if seg == SINGLE_SEGMENT_WILDCARD:
            return True
        if seg == MULTI_SEGMENT_WILDCARD:
            return True
    return False


def _split_segments(*, value: str) -> List[str]:
    if value is None or len(value) == 0:
        return []
    rtnval = value.split(SEGMENT_DELIMITER)
    return rtnval


def _match_segments(
        *,
        pattern_segments: List[str],
        topic_segments: List[str]
    ) -> bool:
    """
        Recursive segment-by-segment matcher. Handles ``*``
        as a one-segment match and ``#`` as a zero-or-more
        match.
    """
    if len(pattern_segments) == 0:
        return len(topic_segments) == 0

    head_pattern = pattern_segments[0]
    rest_pattern = pattern_segments[1:]

    if head_pattern == MULTI_SEGMENT_WILDCARD:
        # ``#`` can swallow zero, one, two, ... segments.
        # Try the shortest match first then expand.
        if len(rest_pattern) == 0:
            # ``#`` alone (or trailing) matches everything
            # remaining including the empty tail.
            return True
        for split_index in range(0, len(topic_segments) + 1):
            tail_topic = topic_segments[split_index:]
            if _match_segments(
                pattern_segments=rest_pattern,
                topic_segments=tail_topic,
            ) is True:
                return True
        return False

    if len(topic_segments) == 0:
        return False

    head_topic = topic_segments[0]
    rest_topic = topic_segments[1:]

    if head_pattern == SINGLE_SEGMENT_WILDCARD:
        rtnval = _match_segments(
            pattern_segments=rest_pattern,
            topic_segments=rest_topic,
        )
        return rtnval

    if head_pattern == head_topic:
        rtnval = _match_segments(
            pattern_segments=rest_pattern,
            topic_segments=rest_topic,
        )
        return rtnval

    return False
