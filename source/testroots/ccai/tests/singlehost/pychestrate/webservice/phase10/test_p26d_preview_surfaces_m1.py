"""
.. module:: test_p26d_preview_surfaces_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Regression tests for audit ORG-F14 -- pages whose
               backend works only in part say so.

.. moduleauthor:: Code Craft AI LLC

The sidebar and the project sub-navigation led to pages whose backend
could not produce their data or effects, with nothing on the page to
say so. After the Layer-7 fixes (audit ORC-04) Timeseries, Dashboards,
SLOs and Test Metrics work; the pages that still work only in part are
labelled "(preview)" and explain what is missing:

* Alert Rules -- evaluated, but no notification is sent;
* Webhooks -- inbound deliveries start nothing, outbound subscriptions
  receive test events only;
* Resources and Pools -- dispatch does not allocate from them;
* project release Channels and Schedules -- nothing can create them
  and nothing runs a schedule (their empty states pointed to an API
  that does not exist).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Dict

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (
    NAV_ENTRIES,
    PREVIEW_LABEL_SUFFIX,
)

from ccai.testshared.factories.webui.dataclass_fixtures import MODE_SPARSE
from ccai.testshared.factories.webui.template_contexts import (
    build_template_context,
)

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


CHANNELS_TEMPLATE: str = "projects/releases/channel_list.html"
SCHEDULES_TEMPLATE: str = "projects/releases/schedule_list.html"


def _labels_by_route() -> Dict[str, str]:
    rtnval = {entry.route: entry.label for entry in NAV_ENTRIES}
    return rtnval


def _render_empty(*, template_name: str) -> str:
    """
        Render ``template_name`` with its lists empty (the state these
        pages are always in).
    """
    env = strict_environment()
    context = build_template_context(
        template_name=template_name,
        variable_names=undeclared_variables(template_name=template_name),
        mode=MODE_SPARSE,
    )
    rtnval = env.get_template(template_name).render(context)
    return rtnval


# ---------------------------------------------------------------------------
# Sidebar labels
# ---------------------------------------------------------------------------


def test_alert_rules_entry_is_labelled_preview():
    """
    **Feature: honest surfaces -- audit ORG-F14**
    **Property: the Alert Rules entry is labelled as a preview (rules
    are evaluated but notify nobody).**
    """
    testbase.assert_equal(_labels_by_route()["/metric-alerts"], "Alert Rules" + PREVIEW_LABEL_SUFFIX)
    return


def test_webhooks_entry_is_labelled_preview():
    """
    **Feature: honest surfaces -- audit ORG-F14**
    **Property: the Webhooks entry is labelled as a preview (inbound
    deliveries start nothing; outbound receives test events only).**
    """
    testbase.assert_equal(_labels_by_route()["/webhooks"], "Webhooks" + PREVIEW_LABEL_SUFFIX)
    return


def test_resource_pools_entry_names_resources_and_pools_and_is_labelled_preview():
    """
    **Feature: honest surfaces -- audit ORG-F14, RES-05**
    **Property: the /resource-pools entry says what it manages (resources
    and pools) and that it is a preview (dispatch does not allocate from
    the pools).**
    """
    testbase.assert_equal(
        _labels_by_route()["/resource-pools"],
        "Resources and Pools" + PREVIEW_LABEL_SUFFIX,
    )
    return


def test_working_insights_entries_are_not_labelled_preview():
    """
    **Feature: honest surfaces -- audit ORG-F14**
    **Property: Timeseries, Dashboards, SLOs and Test Metrics -- which
    now read the metric writer's samples -- carry no preview label.**
    """
    labels = _labels_by_route()
    flagged = [
        route for route in ("/timeseries", "/dashboards", "/slos", "/test-metrics")
        if labels[route].endswith(PREVIEW_LABEL_SUFFIX)
    ]
    testbase.assert_equal(flagged, [])
    return


# ---------------------------------------------------------------------------
# Project release Channels / Schedules
# ---------------------------------------------------------------------------


def test_project_channels_page_says_it_is_a_preview():
    """
    **Feature: honest surfaces -- audit ORG-F14**
    **Property: the project release Channels page explains that
    channels cannot be created yet.**
    """
    rendered = _render_empty(template_name=CHANNELS_TEMPLATE)
    testbase.assert_true('data-role="preview-notice"' in rendered)
    return


def test_project_channels_page_does_not_point_to_a_missing_api():
    """
    **Feature: honest surfaces -- audit ORG-F14**
    **Property: the empty state no longer says channels "are
    configured via the API" -- no API manages them.**
    """
    rendered = _render_empty(template_name=CHANNELS_TEMPLATE)
    testbase.assert_equal("configured via the API" in rendered, False)
    return


def test_project_schedules_page_says_it_is_a_preview():
    """
    **Feature: honest surfaces -- audit ORG-F14**
    **Property: the project release Schedules page explains that
    schedules cannot be created and never run.**
    """
    rendered = _render_empty(template_name=SCHEDULES_TEMPLATE)
    testbase.assert_true('data-role="preview-notice"' in rendered)
    return


def test_project_schedules_page_does_not_point_to_a_missing_api():
    """
    **Feature: honest surfaces -- audit ORG-F14**
    **Property: the empty state no longer says schedules "are
    configured via the API" -- no API manages them.**
    """
    rendered = _render_empty(template_name=SCHEDULES_TEMPLATE)
    testbase.assert_equal("configured via the API" in rendered, False)
    return


def test_project_subnav_no_longer_lists_channels_and_schedules():
    """
    **Feature: honest surfaces -- audit ORG-F14, PRJ-08**
    **Property: the project sub-navigation does not list the Channels and
    Schedules tabs (nothing can fill them; the pages still open, with the
    preview notice tested above), so it has no "(preview)" tab to label.**
    """
    rendered = _render_empty(template_name=CHANNELS_TEMPLATE)
    testbase.assert_equal(
        (
            "Channels (preview)" in rendered, "Schedules (preview)" in rendered,
            "pyc-subnav__section\">Releases" in rendered,
        ),
        (False, False, True),
    )
    return
