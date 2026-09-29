"""
.. module:: test_p31zo_table_structure_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: No table row is opened inside another table row (ADM-44).

.. moduleauthor:: Code Craft AI LLC

``ui.empty_state(..., colspan=N)`` writes a whole ``<tr><td colspan=N>`` row,
and callers wrapped it in a ``<tr>`` of their own. HTML does not allow a row
inside a row: the parser closes the outer one, leaving an empty row (a stray
border and a wrong cell count) before the message. This renders every
template, with every list full and with every list empty, and reads the tags
as written (not as a browser repairs them) to make sure it cannot come back.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from html.parser import HTMLParser
from typing import List, Tuple

from ccai import testbase

from ccai.testshared.factories.webui.dataclass_fixtures import MODE_POPULATED, MODE_SPARSE
from ccai.testshared.factories.webui.template_contexts import build_template_context

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    enumerate_templates,
    strict_environment,
    undeclared_variables,
)


class _RowNesting(HTMLParser):
    """Records each ``<tr>`` that starts while another row of the same table is still open."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._open_rows: List[int] = [0]
        self.offences: List[Tuple[int, int]] = []
        return

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "table":
            self._open_rows.append(0)
        elif tag == "tr":
            if self._open_rows[-1] > 0:
                self.offences.append(self.getpos())
            self._open_rows[-1] += 1
        return

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and len(self._open_rows) > 1:
            self._open_rows.pop()
        elif tag == "tr" and self._open_rows[-1] > 0:
            self._open_rows[-1] -= 1
        return


def _nested_rows(*, html: str) -> List[Tuple[int, int]]:
    parser = _RowNesting()
    parser.feed(html)
    return parser.offences


def test_the_row_nesting_check_sees_a_row_inside_a_row_and_accepts_a_table_in_a_cell():
    """
    **Feature: table structure (ADM-44)**
    **Property: the check flags ``<tr><tr>`` and ``<tr>{{ row }}</tr>``, and
    does not flag a table nested in a cell or two sibling rows.**
    """
    nested = "<table><tbody><tr><tr><td>x</td></tr></tr></tbody></table>"
    sibling = "<table><tbody><tr><td>a</td></tr><tr><td>b</td></tr></tbody></table>"
    in_cell = "<table><tr><td><table><tr><td>inner</td></tr></table></td></tr></table>"

    testbase.assert_equal(
        (len(_nested_rows(html=nested)), _nested_rows(html=sibling), _nested_rows(html=in_cell)),
        (1, [], []),
    )
    return


def test_no_template_opens_a_table_row_inside_a_table_row():
    """
    **Feature: table structure (ADM-44)**
    **Property: rendered with every list full and every list empty, no
    template writes a ``<tr>`` while another row of the same table is open.**
    """
    env = strict_environment()
    offenders = {}
    for template_name in enumerate_templates():
        if template_name.rsplit("/", 1)[-1].startswith("_"):
            continue  # macro libraries render to nothing on their own
        for mode in (MODE_POPULATED, MODE_SPARSE):
            context = build_template_context(
                template_name=template_name,
                variable_names=undeclared_variables(template_name=template_name),
                mode=mode,
            )
            found = _nested_rows(html=env.get_template(template_name).render(context))
            if len(found) > 0:
                offenders["{} ({})".format(template_name, mode)] = len(found)

    testbase.assert_equal(offenders, {})
    return
