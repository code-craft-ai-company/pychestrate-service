"""
.. module:: test_p30y_pod_guide_link_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The enrollment token page links to the pod guide (CLI-14).

.. moduleauthor:: Code Craft AI LLC

The token page printed the two commands and nothing more, while the
pod-side docs disagreed with it. The guide in the client repository is
now the one description of the whole path, and the page that mints the
token links to it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Dict, Optional

from ccai import testbase

from ccai.testshared.factories.webui.dataclass_fixtures import MODE_POPULATED, MODE_SPARSE
from ccai.testshared.factories.webui.template_contexts import build_template_context

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


TEMPLATE_NAME: str = "config/enrollment/list.html"

GUIDE_PATH: str = "pychestrate-client/blob/main/userguide/01-00-quickstart.rst"


def _render(*, mode: str) -> str:
    variables = undeclared_variables(template_name=TEMPLATE_NAME)
    context = build_template_context(template_name=TEMPLATE_NAME, variable_names=variables, mode=mode)
    rtnval = strict_environment().get_template(TEMPLATE_NAME).render(context)
    return rtnval


def test_the_minted_token_panel_links_to_the_pod_guide():
    """
    **Feature: pod onboarding (CLI-14)**
    **Property: after a token is minted, the panel with the commands
    links to the pod guide in the client repository.**
    """
    html = _render(mode=MODE_POPULATED)

    testbase.assert_equal(GUIDE_PATH in html, True)
    return


def test_the_token_page_without_a_minted_token_does_not_show_the_guide_link():
    """
    **Feature: pod onboarding (CLI-14)**
    **Property: the guide link belongs to the minted-token panel; the
    plain page does not carry it.**
    """
    html = _render(mode=MODE_SPARSE)

    testbase.assert_equal(GUIDE_PATH in html, False)
    return
