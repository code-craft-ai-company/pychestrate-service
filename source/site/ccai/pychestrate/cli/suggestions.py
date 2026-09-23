"""
.. module:: cli.suggestions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: "Did you mean ...?" for mistyped commands, verbs,
               options and fields.

.. moduleauthor:: Code Craft AI LLC

Every "unknown X" error ``pyc`` prints names the closest known
spellings (:func:`difflib.get_close_matches`), so a typo costs one
glance instead of a trip to ``--help``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import difflib

from typing import Iterable, List


#: How similar a candidate must be to be suggested (0..1).
SUGGESTION_CUTOFF: float = 0.6

#: At most this many suggestions are offered.
SUGGESTION_LIMIT: int = 3


def closest_matches(*, word: str, candidates: Iterable[str]) -> List[str]:
    """
        The known spellings closest to ``word``, best first.

        :param word: What was typed.
        :param candidates: Known spellings.

        :returns: Up to :data:`SUGGESTION_LIMIT` matches (possibly
                  none).
    """
    unique_candidates = sorted(set(str(candidate) for candidate in candidates))
    rtnval = difflib.get_close_matches(
        str(word), unique_candidates, n=SUGGESTION_LIMIT, cutoff=SUGGESTION_CUTOFF
    )
    return rtnval


def did_you_mean(*, word: str, candidates: Iterable[str]) -> str:
    """
        ``"did you mean 'x' or 'y'?"`` for ``word``, or ``""`` when
        nothing is close.

        :param word: What was typed.
        :param candidates: Known spellings.

        :returns: Sentence or empty text.
    """
    matches = closest_matches(word=word, candidates=candidates)
    if len(matches) == 0:
        rtnval = ""
        return rtnval
    quoted = ["'{}'".format(match) for match in matches]
    if len(quoted) == 1:
        joined = quoted[0]
    else:
        joined = "{} or {}".format(", ".join(quoted[:-1]), quoted[-1])
    rtnval = "did you mean {}?".format(joined)
    return rtnval


__all__ = [
    "SUGGESTION_CUTOFF",
    "SUGGESTION_LIMIT",
    "closest_matches",
    "did_you_mean",
]
