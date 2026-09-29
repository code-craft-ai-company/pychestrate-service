"""
.. module:: test_p31zzp_two_resource_systems_named_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The two sets of resource records are named and told apart (RES-05).

.. moduleauthor:: Code Craft AI LLC

Two unconnected sets of resource records sat under one Fleet menu (a pool named
``android-phones`` existed in both, with different members), one of them
reachable only through another page's sub-navigation, and both navigations
showed at once with different names for the same page ("Health Status" and
"Resource Health"). Until the older set is merged into the newer one (see
``specs/model-convergence.md``), the menu names them plainly ("Resources and
Pools" for the newer, "Older Resources" for the older), the older pages'
sub-navigation uses the menu's names, and the older pages say which records
they hold and where the newer ones are.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re

from typing import Dict, List

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import NAV_ENTRIES

from ccai.testshared.factories.webui.dataclass_fixtures import MODE_SPARSE
from ccai.testshared.factories.webui.template_contexts import build_template_context

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


def _render(template_name: str, **overrides: str) -> str:
    context = build_template_context(
        template_name=template_name,
        variable_names=undeclared_variables(template_name=template_name),
        mode=MODE_SPARSE,
    )
    context.update(overrides)
    rendered = html.unescape(strict_environment().get_template(template_name).render(context))
    return re.sub(r"[ \t\r\n]+", " ", rendered)


def _fleet_labels() -> Dict[str, str]:
    return {entry.route: entry.label for entry in NAV_ENTRIES if entry.entry_id.startswith("fleet.")}


def test_the_fleet_menu_names_the_newer_and_the_older_resources_and_lists_the_older_ones():
    """
    **Feature: two resource systems, named (RES-05)**
    **Property: Fleet has "Resources and Pools (preview)" for the newer records
    and "Older Resources" (``/resources/list``, which no menu reached before)
    for the older ones, and no two Fleet entries share a label.**
    """
    labels = _fleet_labels()

    testbase.assert_equal(
        (
            labels.get("/resource-pools"),
            labels.get("/resources/list"),
            len(set(labels.values())) == len(labels),
        ),
        ("Resources and Pools (preview)", "Older Resources", True),
    )
    return


def test_the_older_pages_use_the_menus_names_for_their_shared_destinations():
    """
    **Feature: two resource systems, named (RES-05)**
    **Property: the older pages' sub-navigation calls the health page
    "Resource Health", as the sidebar does (it said "Health Status"), and
    IP Pools and Reservations agree too; its first section says these are the
    older records.**
    """
    page = _render("resources/resources/list.html", request_endpoint="resources.resource_list")
    nav = re.search(r'<nav class="pyc-subnav".*?</nav>', page, re.S).group(0)
    names = [re.sub(r"<[^>]+>|\s+", " ", text).strip() for _href, text in re.findall(r'<a href="([^"]*)"[^>]*>(.*?)</a>', nav)]
    sidebar = _fleet_labels()

    testbase.assert_equal(
        (
            "Resource Health" in names and "Health Status" not in names,
            sidebar["/resources/health"] in names,
            sidebar["/resources/ip-pools"] in names,
            "Older resource records" in nav,
        ),
        (True, True, True, True),
    )
    return


def test_the_older_resource_and_pool_pages_say_which_records_they_hold():
    """
    **Feature: two resource systems, named (RES-05)**
    **Property: the older resources list and pool list carry a notice that
    they hold the older records, that jobs do not use them, and link to
    Resources and Pools; the IP pools page, which has no newer counterpart,
    carries none.**
    """
    resources = _render("resources/resources/list.html", request_endpoint="resources.resource_list")
    pools = _render("resources/pools/list.html", request_endpoint="resources.pool_list")
    ip_pools = _render("resources/ip_pools/list.html", request_endpoint="resources.ip_pool_list")

    def has_notice(page: str) -> bool:
        return 'data-role="preview-notice"' in page and "older set of resource records" in page and 'href="/resource-pools"' in page

    testbase.assert_equal(
        (has_notice(resources), has_notice(pools), "older set of resource records" in ip_pools),
        (True, True, False),
    )
    return
