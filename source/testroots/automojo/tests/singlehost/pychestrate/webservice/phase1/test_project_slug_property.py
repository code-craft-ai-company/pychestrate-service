"""
.. module:: test_project_slug_property
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Property-style test for canonicalize_project_slug (2-projects TT-2 Property 1).

.. moduleauthor:: Automation Mojo LLC

The real ``hypothesis`` package is not a dependency of this repository.
Instead we build a deterministic generator keyed off a seeded
:class:`random.Random` to produce 1024 random strings drawn from a
broad Unicode sample and assert the canonicalize-then-canonicalize
invariant described in ``specs/2-projects/requirements.md`` Property 1.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import random
import string

from automojo import testbase

from automojo.pychestrate.webservice.projects.exceptions import SlugValidationError
from automojo.pychestrate.webservice.projects.slug import canonicalize_project_slug


_CASES: int = 1024
_SEED: int = 20260424

_SAMPLE_ALPHABET: str = (
    string.ascii_letters
    + string.digits
    + "-_ "
    + "".join(chr(codepoint) for codepoint in range(0x21, 0x7F))
    + "ñåçé"
)


def _generate_random_strings() -> list:
    """
        Build a deterministic list of candidate slug strings.

        :returns: List of raw strings covering edge cases and random
                  samples in the 0..64 length range.
    """
    rng = random.Random(_SEED)
    candidates = []

    # Deterministic edge cases that must be covered on every run.
    edge_cases = [
        "",
        " ",
        "\t\n",
        "a",
        "abc",
        "ABC",
        "  leading-space",
        "trailing-space  ",
        "bad!char",
        "1-leading-digit",
        "x" * 128,
        "a-" + ("b" * 80),
        "slug-with-digits-123",
        "UPPER-case-mixed-123",
        "---",
        "--a",
        "--",
    ]
    candidates.extend(edge_cases)

    for _ in range(_CASES - len(edge_cases)):
        size = rng.randint(0, 64)
        chars = []
        for _ in range(size):
            chars.append(rng.choice(_SAMPLE_ALPHABET))
        candidates.append("".join(chars))

    return candidates


def test_canonicalize_is_idempotent_across_random_inputs():
    """
    **Feature: 2-projects TT-2 (Property 1)**
    **Property: canonicalize_project_slug(canonicalize_project_slug(s)) ==
    canonicalize_project_slug(s) for any s, or both raise
    SlugValidationError identically.**
    """
    candidates = _generate_random_strings()
    testbase.assert_equal(len(candidates) >= 1000, True)

    for raw in candidates:
        first_value = None
        first_error = None
        try:
            first_value = canonicalize_project_slug(raw_slug=raw)
        except SlugValidationError as xcpt:
            first_error = str(xcpt)

        if first_error is not None:
            continue

        second_value = None
        second_error = None
        try:
            second_value = canonicalize_project_slug(raw_slug=first_value)
        except SlugValidationError as xcpt:
            second_error = str(xcpt)

        testbase.assert_equal(second_error, None)
        testbase.assert_equal(second_value, first_value)
    return


def test_canonicalize_output_matches_required_pattern_or_raises():
    """
    **Feature: 2-projects TT-2 (Property 1 tail)**
    **Property: The result of canonicalize_project_slug always matches
    ^[a-z][a-z0-9-]{1,62}$ or the call raised SlugValidationError.**
    """
    import re
    pattern = re.compile(r"^[a-z][a-z0-9-]{1,62}$")

    candidates = _generate_random_strings()
    for raw in candidates:
        try:
            canonical = canonicalize_project_slug(raw_slug=raw)
        except SlugValidationError:
            continue
        testbase.assert_equal(pattern.match(canonical) is not None, True)
    return
