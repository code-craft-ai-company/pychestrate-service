"""
.. module:: test_p31zzb_heading_order_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A page's headings do not skip a level (WCAG 1.3.1, axe heading-order).

.. moduleauthor:: Code Craft AI LLC

The Enrollment Tokens page went from its h1 straight to an h3 ("Mint New
Token"). Every server-rendered template is rendered with every list full and
with every list empty, and the headings of each are read in order: a heading
may be at most one level deeper than the one before it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from html.parser import HTMLParser
from typing import Dict, List

from ccai import testbase

from ccai.testshared.factories.webui.dataclass_fixtures import MODE_POPULATED, MODE_SPARSE
from ccai.testshared.factories.webui.template_contexts import build_template_context

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    enumerate_templates,
    strict_environment,
    undeclared_variables,
)


class _Headings(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.levels: List[int] = []
        return

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if len(tag) == 2 and tag[0] == "h" and tag[1] in "123456":
            self.levels.append(int(tag[1]))
        return


def _skips(levels: List[int]) -> List[str]:
    """The jumps of more than one level down (h1 then h3), as text."""
    found = []
    previous = 0
    for level in levels:
        if previous > 0 and level > previous + 1:
            found.append("h{} after h{}".format(level, previous))
        previous = level
    return found


def test_the_check_sees_a_skipped_level_and_accepts_going_back_up():
    """
    **Feature: heading order (WCAG 1.3.1)**
    **Property: h1 then h3 is a skip; h1, h2, h3, h2, h3 is not.**
    """
    testbase.assert_equal(
        (_skips([1, 3]), _skips([1, 2, 3, 2, 3]), _skips([2, 3, 4])),
        (["h3 after h1"], [], []),
    )
    return


def test_no_template_skips_a_heading_level():
    """
    **Feature: heading order (WCAG 1.3.1)**
    **Property: rendered with every list full and every list empty, no
    template has a heading more than one level below the one before it.**
    """
    env = strict_environment()
    offenders: Dict[str, List[str]] = {}
    for template_name in enumerate_templates():
        if template_name.rsplit("/", 1)[-1].startswith("_"):
            continue
        for mode in (MODE_POPULATED, MODE_SPARSE):
            context = build_template_context(
                template_name=template_name,
                variable_names=undeclared_variables(template_name=template_name),
                mode=mode,
            )
            parser = _Headings()
            parser.feed(env.get_template(template_name).render(context))
            skipped = _skips(parser.levels)
            if skipped:
                offenders["{} ({})".format(template_name, mode)] = skipped

    testbase.assert_equal(offenders, {})
    return
