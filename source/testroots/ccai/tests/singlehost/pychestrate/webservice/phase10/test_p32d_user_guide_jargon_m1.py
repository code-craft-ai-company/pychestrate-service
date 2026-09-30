"""
.. module:: test_p32d_user_guide_jargon_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The user-facing chapters of the guide carry no project-history jargon (DOC-21).

.. moduleauthor:: Code Craft AI LLC

The guide read like the project's history: pull-request numbers ("PR p17g"),
implementation phases and layers ("Phase 10", "Layer 9", "the Phase-2 bus"),
milestone codes, and the word "agent" for the pod client that the client's own
README says is never called that. This lint reads the operator- and
user-facing chapters and fails when any of them comes back. The chapters
written for people changing the service (09 to 12: code organisation, coding
standards, extensions and the authentication stack) are not read: that is
contributor material (see the finding on the guide's audience), and they cite
pull requests and phases on purpose.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import glob
import os
import re

from typing import Dict, List

from ccai import testbase


#: Chapters for people who change the service; the lint does not read them.
CONTRIBUTOR_CHAPTER = re.compile(r"^(09|10|11|12)-")

RULES = {
    "a pull request number": re.compile(r"\bPR ?#?\d+|\bPR p\d+[a-z]*"),
    "an implementation phase or layer": re.compile(r"\b(?:Phase|Layer)[ -]?\d+"),
    "a milestone code": re.compile(r"\bM\d\b"),
    "\"agent\" for the pod client": re.compile(r"\bagent\b(?! rollout)", re.I),
}


def _chapters() -> Dict[str, str]:
    current = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(current, "userguide")) and current != os.path.dirname(current):
        current = os.path.dirname(current)
    found: Dict[str, str] = {}
    for path in sorted(glob.glob(os.path.join(current, "userguide", "*.rst"))):
        name = os.path.basename(path)
        if CONTRIBUTOR_CHAPTER.match(name) is None:
            with open(path, encoding="utf-8") as handle:
                found[name] = handle.read()
    return found


def _findings(chapters: Dict[str, str]) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    for name, text in chapters.items():
        prose = re.sub(r"::\n(?:(?:[ \t]+.*)?\n)+", "\n", text)
        for rule, pattern in RULES.items():
            if pattern.search(prose) is not None:
                found.setdefault(rule, []).append(name)
    return found


def test_no_user_facing_chapter_carries_project_history_jargon():
    """
    **Feature: a readable user guide (DOC-21)**
    **Property: no operator- or user-facing chapter mentions a pull-request
    number, an implementation phase or layer, a milestone code, or calls the pod
    client an agent (code blocks are not read).**
    """
    chapters = _chapters()

    testbase.assert_equal((len(chapters) >= 10, _findings(chapters)), (True, {}))
    return


def test_the_lint_reads_the_chapters_it_claims_to_and_its_rules_bite():
    """
    **Feature: a readable user guide (DOC-21)**
    **Property: the lint reads the user-facing chapters and none of 09 to 12,
    and each rule flags a sample of the thing it forbids.**
    """
    chapters = _chapters()
    sample = "Added in PR p17g and PR #160 (Phase 10, Layer-9, M2): the agent runs."
    hits = _findings({"sample.rst": sample})

    testbase.assert_equal(
        (
            any(CONTRIBUTOR_CHAPTER.match(name) for name in chapters),
            "17-00-site-shell.rst" in chapters,
            sorted(hits),
        ),
        (
            False,
            True,
            ['"agent" for the pod client', "a milestone code", "a pull request number", "an implementation phase or layer"],
        ),
    )
    return
