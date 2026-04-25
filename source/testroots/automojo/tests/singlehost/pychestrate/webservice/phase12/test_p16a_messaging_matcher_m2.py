"""
.. module:: test_p16a_messaging_matcher_m2
    :synopsis: Tests for P16a — 0-message-bus M2 wildcard matcher.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from automojo import testbase

from automojo.pychestrate.webservice.messaging.matcher import (
    is_pattern,
    match_pattern,
)


# -------------------------------------
# Literal matches
# -------------------------------------

def test_literal_pattern_matches_identical_topic():
    """
    **Feature: 0-message-bus (M2)**
    **Property: a literal pattern matches the exact same
    topic.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.user.created",
            topic="entity.user.created",
        ),
        True,
    )
    return


def test_literal_pattern_rejects_different_topic():
    """
    **Feature: 0-message-bus (M2)**
    **Property: a literal pattern rejects a topic that
    differs in any segment.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.user.created",
            topic="entity.user.deleted",
        ),
        False,
    )
    return


def test_literal_pattern_is_case_sensitive():
    """
    **Feature: 0-message-bus (M2)**
    **Property: literal segments compare case-sensitively.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="Entity.User.Created",
            topic="entity.user.created",
        ),
        False,
    )
    return


def test_pattern_does_not_match_when_lengths_differ():
    """
    **Feature: 0-message-bus (M2)**
    **Property: a pattern with N segments does not match a
    topic with M segments unless wildcards are involved.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.user",
            topic="entity.user.created",
        ),
        False,
    )
    testbase.assert_equal(
        match_pattern(
            pattern="entity.user.created",
            topic="entity.user",
        ),
        False,
    )
    return


# -------------------------------------
# Single-segment wildcard `*`
# -------------------------------------

def test_single_wildcard_matches_one_segment_in_middle():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``*`` in the middle of a pattern matches
    exactly one segment.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.*.created",
            topic="entity.user.created",
        ),
        True,
    )
    testbase.assert_equal(
        match_pattern(
            pattern="entity.*.created",
            topic="entity.project.created",
        ),
        True,
    )
    return


def test_single_wildcard_at_head_or_tail():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``*`` works at the head or tail of a
    pattern.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="*.user.created",
            topic="entity.user.created",
        ),
        True,
    )
    testbase.assert_equal(
        match_pattern(
            pattern="entity.user.*",
            topic="entity.user.created",
        ),
        True,
    )
    return


def test_single_wildcard_does_not_span_dots():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``*`` matches exactly one segment — it does
    NOT span dots.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.*.created",
            topic="entity.user.profile.created",
        ),
        False,
    )
    testbase.assert_equal(
        match_pattern(
            pattern="entity.*",
            topic="entity",
        ),
        False,
    )
    return


def test_multiple_single_wildcards_compose():
    """
    **Feature: 0-message-bus (M2)**
    **Property: a pattern can contain multiple ``*`` wildcards
    that each match exactly one segment.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.*.*.created",
            topic="entity.org.user.created",
        ),
        True,
    )
    testbase.assert_equal(
        match_pattern(
            pattern="entity.*.*.created",
            topic="entity.user.created",
        ),
        False,
    )
    return


# -------------------------------------
# Multi-segment wildcard `#`
# -------------------------------------

def test_multi_wildcard_matches_zero_segments():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``#`` matches zero segments — pattern
    ``entity.#`` matches just ``entity``.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.#",
            topic="entity",
        ),
        True,
    )
    return


def test_multi_wildcard_matches_one_segment():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``#`` matches one segment.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.#",
            topic="entity.user",
        ),
        True,
    )
    return


def test_multi_wildcard_matches_many_segments():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``#`` matches multiple segments.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.#",
            topic="entity.org.user.profile.created",
        ),
        True,
    )
    return


def test_multi_wildcard_at_head_matches_anything():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``#`` at the head matches every topic.**
    """
    testbase.assert_equal(
        match_pattern(pattern="#", topic="entity.user.created"),
        True,
    )
    testbase.assert_equal(
        match_pattern(pattern="#", topic=""),
        True,
    )
    return


def test_multi_wildcard_in_middle_with_literal_tail():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``entity.#.created`` matches every topic
    that starts with entity and ends with created.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.#.created",
            topic="entity.user.created",
        ),
        True,
    )
    testbase.assert_equal(
        match_pattern(
            pattern="entity.#.created",
            topic="entity.org.user.created",
        ),
        True,
    )
    testbase.assert_equal(
        match_pattern(
            pattern="entity.#.created",
            topic="entity.user.deleted",
        ),
        False,
    )
    return


def test_multi_wildcard_with_literal_does_not_match_unrelated_topic():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``entity.#`` rejects topics that don't start
    with ``entity``.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.#",
            topic="system.health.probe.failed",
        ),
        False,
    )
    return


def test_multi_wildcard_can_combine_with_single_wildcard():
    """
    **Feature: 0-message-bus (M2)**
    **Property: ``*`` and ``#`` can compose in the same
    pattern.**
    """
    testbase.assert_equal(
        match_pattern(
            pattern="entity.*.#",
            topic="entity.user.created",
        ),
        True,
    )
    testbase.assert_equal(
        match_pattern(
            pattern="entity.*.#",
            topic="entity.user.org.created",
        ),
        True,
    )
    testbase.assert_equal(
        match_pattern(
            pattern="entity.*.#",
            topic="entity",
        ),
        False,
    )
    return


# -------------------------------------
# Edge cases
# -------------------------------------

def test_empty_pattern_only_matches_empty_topic():
    """
    **Feature: 0-message-bus (M2)**
    **Property: an empty pattern only matches an empty topic.**
    """
    testbase.assert_equal(match_pattern(pattern="", topic=""), True)
    testbase.assert_equal(
        match_pattern(pattern="", topic="entity"),
        False,
    )
    testbase.assert_equal(
        match_pattern(pattern="entity", topic=""),
        False,
    )
    return


def test_none_inputs_return_false():
    """
    **Feature: 0-message-bus (M2)**
    **Property: None pattern or topic returns False — the
    matcher never raises on bad inputs.**
    """
    testbase.assert_equal(
        match_pattern(pattern=None, topic="entity.user.created"),
        False,
    )
    testbase.assert_equal(
        match_pattern(pattern="entity.#", topic=None),
        False,
    )
    return


# -------------------------------------
# is_pattern helper
# -------------------------------------

def test_is_pattern_detects_wildcards():
    """
    **Feature: 0-message-bus (M2)**
    **Property: is_pattern returns True iff the pattern
    contains at least one wildcard segment.**
    """
    testbase.assert_equal(is_pattern(pattern="entity.user.created"), False)
    testbase.assert_equal(is_pattern(pattern="entity.*.created"), True)
    testbase.assert_equal(is_pattern(pattern="entity.#"), True)
    testbase.assert_equal(is_pattern(pattern=""), False)
    testbase.assert_equal(is_pattern(pattern=None), False)
    return
