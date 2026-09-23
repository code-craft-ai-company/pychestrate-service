"""
.. module:: test_p30r_resources_template_regressions_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Rendered-template regression locks for the resources audit
               fixes (September 2026 audit, RES-* findings).

.. moduleauthor:: Code Craft AI LLC

Each test renders a real resources template through the strict jinja
environment the render-smoke suite uses, with the fixture context for the
variables the template reads and the values under test overridden, and
checks one property of the HTML.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from ccai import testbase

from ccai.testshared.factories.webui.dataclass_fixtures import (
    MODE_SPARSE,
    build_fixture,
)
from ccai.testshared.factories.webui.template_contexts import (
    build_template_context,
)

from ccai.pychestrate.core.managers.allocation_manager import ReservationResponse
from ccai.pychestrate.core.managers.ip_pool_manager import IPPoolResponse
from ccai.pychestrate.core.managers.resource_manager import (
    ResourcePoolResponse,
    ResourceResponse,
    TagResponse,
)
from ccai.pychestrate.webservice.webinterface.foundation import templating

from ccai.tests.singlehost.pychestrate.webservice.phase13._template_harness import (
    strict_environment,
    undeclared_variables,
)


def _render(*, template_name: str, overrides: Optional[Dict[str, Any]] = None) -> str:
    """
        Render ``template_name`` with the sparse fixture context plus
        ``overrides``.
    """
    env = strict_environment()
    variables = undeclared_variables(template_name=template_name)
    context = build_template_context(
        template_name=template_name, variable_names=variables, mode=MODE_SPARSE
    )
    if overrides is not None:
        context.update(overrides)
    rtnval = env.get_template(template_name).render(context)
    return rtnval


def _input_tag(*, html: str, input_id: str) -> str:
    match = re.search(r'<input[^>]*\bid="{}"[^>]*>'.format(re.escape(input_id)), html, re.DOTALL)
    rtnval = match.group(0) if match is not None else ""
    return rtnval


def _stored_reservation() -> Any:
    rtnval = build_fixture(
        ReservationResponse,
        mode=MODE_SPARSE,
        overrides={
            "start_time": datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc),
            "end_time": datetime(2026, 9, 23, 19, 30, tzinfo=timezone.utc),
        },
    )
    return rtnval


# ---------------------------------------------------------------------------
# RES-17: the reservation edit form's pre-fill
# ---------------------------------------------------------------------------


def test_input_datetime_renders_plain_datetime_local_text():
    """
    **Feature: resources (RES-17 edit pre-fill)**
    **Property: input_datetime renders an aware UTC datetime as
    YYYY-MM-DDTHH:MM with no markup.**
    """
    rendered = templating.input_datetime_filter(datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc))

    testbase.assert_equal(rendered, "2026-09-23T17:00")
    return


def test_input_datetime_renders_in_the_named_zone():
    """
    **Feature: resources (RES-17 edit pre-fill)**
    **Property: input_datetime with zone America/Los_Angeles renders
    17:00 UTC on 23 September (PDT) as 10:00.**
    """
    rendered = templating.input_datetime_filter(
        datetime(2026, 9, 23, 17, 0, tzinfo=timezone.utc), "America/Los_Angeles"
    )

    testbase.assert_equal(rendered, "2026-09-23T10:00")
    return


def test_input_datetime_takes_a_naive_value_as_utc():
    """
    **Feature: resources (RES-17 edit pre-fill)**
    **Property: a naive value is rendered as UTC.**
    """
    rendered = templating.input_datetime_filter(datetime(2026, 9, 23, 17, 0), "Europe/Berlin")

    testbase.assert_equal(rendered, "2026-09-23T19:00")
    return


def test_input_datetime_renders_none_as_an_empty_value():
    """
    **Feature: resources (RES-17 edit pre-fill)**
    **Property: None renders as an empty string (a blank input), not as
    a placeholder dash or markup.**
    """
    rendered = templating.input_datetime_filter(None)

    testbase.assert_equal(rendered, "")
    return


def test_reservation_edit_prefills_the_stored_start_time():
    """
    **Feature: resources (RES-17 edit pre-fill)**
    **Property: the edit form's start input carries the stored start
    (17:00 UTC) as value="2026-09-23T17:00".**
    """
    html = _render(
        template_name="resources/reservations/edit.html",
        overrides={"reservation": _stored_reservation(), "form_data": None, "viewer_timezone": ""},
    )

    testbase.assert_true('value="2026-09-23T17:00"' in _input_tag(html=html, input_id="start_time"), html[:2000])
    return


def test_reservation_edit_leaks_no_time_markup_into_the_page():
    """
    **Feature: resources (RES-17 edit pre-fill)**
    **Property: no fragment of a <time> element ("UTC">) is printed
    under the date fields of the edit form.**
    """
    html = _render(
        template_name="resources/reservations/edit.html",
        overrides={"reservation": _stored_reservation(), "form_data": None, "viewer_timezone": ""},
    )

    testbase.assert_equal('UTC">' in html, False)
    return


# ---------------------------------------------------------------------------
# RES-02: the zone the times are typed in, beside the inputs
# ---------------------------------------------------------------------------


def test_reservation_create_names_the_time_zone_beside_the_inputs():
    """
    **Feature: resources (RES-02 reservation times)**
    **Property: the create form shows "Times are in UTC" next to the
    start/end inputs on a fresh form, and both inputs point at that
    note.**
    """
    html = _render(
        template_name="resources/reservations/create.html",
        overrides={"form_data": None, "viewer_timezone": ""},
    )
    note = re.search(r'id="reservation-zone-note"[^>]*>(.*?)</p>', html, re.DOTALL)
    note_text = ""
    if note is not None:
        note_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", note.group(1))).strip()

    testbase.assert_equal(
        (note_text, 'aria-describedby="reservation-zone-note"' in _input_tag(html=html, input_id="end_time")),
        ("Times are in UTC.", True),
    )
    return


def test_reservation_create_no_longer_claims_the_server_time_zone():
    """
    **Feature: resources (RES-02 reservation times)**
    **Property: the create form no longer says times are interpreted in
    the server's time zone.**
    """
    html = _render(
        template_name="resources/reservations/create.html",
        overrides={"form_data": None, "viewer_timezone": ""},
    )

    testbase.assert_equal("server's time zone" in html, False)
    return


def test_reservation_forms_carry_the_zone_field():
    """
    **Feature: resources (RES-02 reservation times)**
    **Property: a re-rendered edit form echoes the zone the times were
    typed in into the hidden tz field.**
    """
    html = _render(
        template_name="resources/reservations/edit.html",
        overrides={"reservation": _stored_reservation(), "viewer_timezone": "America/Los_Angeles"},
    )

    testbase.assert_true('name="tz" value="America/Los_Angeles"' in html, html[:2000])
    return


# ---------------------------------------------------------------------------
# RES-32: the resource-list filter is not part of the POST form
# ---------------------------------------------------------------------------


def _forms(*, html: str) -> List[Tuple[str, str]]:
    """
        Every ``<form>`` in ``html`` as ``(opening_tag, body)``.
    """
    rtnval = [
        (match.group(1), match.group(2))
        for match in re.finditer(r"(<form\b[^>]*>)(.*?)</form>", html, re.DOTALL)
    ]
    return rtnval


def test_reservation_filter_form_carries_only_the_filter_fields():
    """
    **Feature: resources (RES-32 filter outside the POST form)**
    **Property: "Apply filter" submits a GET form whose only named
    fields are pool_id and resource_type (no CSRF token, no reservation
    draft).**
    """
    html = _render(
        template_name="resources/reservations/create.html",
        overrides={"form_data": None, "viewer_timezone": ""},
    )
    get_forms = [body for tag, body in _forms(html=html) if 'method="get"' in tag]
    names = sorted(set(re.findall(r'\bname="([^"]+)"', get_forms[0]))) if len(get_forms) == 1 else []

    testbase.assert_equal(names, ["pool_id", "resource_type"])
    return


def test_reservation_form_has_no_get_submit_button():
    """
    **Feature: resources (RES-32 filter outside the POST form)**
    **Property: no button inside the reservation POST form switches it
    to GET (formmethod="get"), which is what put the CSRF token and the
    draft in the URL.**
    """
    html = _render(
        template_name="resources/reservations/create.html",
        overrides={"form_data": None, "viewer_timezone": ""},
    )
    post_bodies = [body for tag, body in _forms(html=html) if 'method="post"' in tag]

    testbase.assert_equal(any("formmethod" in body for body in post_bodies), False)
    return


# ---------------------------------------------------------------------------
# RES-13: the gateway and in-range DNS servers show as reserved
# ---------------------------------------------------------------------------


def test_ip_pool_detail_shows_the_gateway_as_reserved():
    """
    **Feature: resources (RES-13 infrastructure addresses)**
    **Property: the IP pool detail page lists the gateway, labelled
    "(gateway)", in its Reserved Addresses row.**
    """
    pool = build_fixture(
        IPPoolResponse,
        mode=MODE_SPARSE,
        overrides={"cidr": "10.20.30.0/28", "gateway": "10.20.30.1", "infrastructure_ips": {"10.20.30.1": "gateway"}},
    )
    html = _render(template_name="resources/ip_pools/detail.html", overrides={"pool": pool})
    row = re.search(r"Reserved Addresses</th>\s*<td>(.*?)</td>", html, re.DOTALL)
    row_text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>|\{#.*?#\}", "", row.group(1))).strip() if row is not None else ""

    testbase.assert_equal(row_text, "10.20.30.1 (gateway)")
    return


# ---------------------------------------------------------------------------
# RES-07: the resource edit form says when its tag list was shown
# ---------------------------------------------------------------------------


def _resource_edit_html() -> str:
    resource = build_fixture(
        ResourceResponse, mode=MODE_SPARSE, overrides={"tags": ["alpha", "zeta-beyond-the-list"]},
    )
    listed = [build_fixture(TagResponse, mode=MODE_SPARSE, overrides={"name": "alpha"})]
    rtnval = _render(
        template_name="resources/resources/edit.html",
        overrides={"resource": resource, "all_tags": listed, "form_data": None},
    )
    return rtnval


def test_resource_edit_form_marks_that_the_tag_list_was_shown():
    """
    **Feature: resources (RES-07 clearing fields on edit)**
    **Property: the edit form carries the hidden tags_present marker with
    its tag checkboxes, so unticking every tag can be told apart from
    "no tag list".**
    """
    html = _resource_edit_html()

    testbase.assert_true('name="tags_present"' in html, html[:1500])
    return


def test_resource_edit_form_keeps_tags_beyond_the_listed_page():
    """
    **Feature: resources (RES-07 clearing fields on edit)**
    **Property: a tag on the resource that is not in the listed tags is
    still rendered, ticked, so saving the form never drops it unseen.**
    """
    html = _resource_edit_html()
    box = re.search(r'<input[^>]*value="zeta-beyond-the-list"[^>]*>', html, re.DOTALL)

    testbase.assert_true(box is not None and "checked" in box.group(0), html[:1500])
    return


# ---------------------------------------------------------------------------
# RES-46: IPv6-sized address counts are readable
# ---------------------------------------------------------------------------


def test_humanize_count_shows_an_ipv6_64_as_a_power_of_two():
    """
    **Feature: resources (RES-46 large counts)**
    **Property: the 18446744073709551615 usable addresses of an IPv6 /64
    read as "≈ 2⁶⁴".**
    """
    testbase.assert_equal(templating.humanize_count_filter(18446744073709551615), "≈ 2⁶⁴")
    return


def test_humanize_count_uses_words_for_millions():
    """
    **Feature: resources (RES-46 large counts)**
    **Property: a /8's 16777214 usable addresses read as "16.8 million".**
    """
    testbase.assert_equal(templating.humanize_count_filter(16777214), "16.8 million")
    return


def test_humanize_count_keeps_small_counts_exact():
    """
    **Feature: resources (RES-46 large counts)**
    **Property: counts below a million stay exact, with thousands
    separators ("65,534").**
    """
    testbase.assert_equal(templating.humanize_count_filter(65534), "65,534")
    return


def test_ip_pool_list_does_not_print_raw_ipv6_counts():
    """
    **Feature: resources (RES-46 large counts)**
    **Property: the IP pool list shows an IPv6 /64's counts as "≈ 2⁶⁴"
    and never prints the 20-digit number as visible text (it stays in
    the tooltip).**
    """
    pool = build_fixture(IPPoolResponse, mode=MODE_SPARSE, overrides={
        "cidr": "2001:db8::/64", "total_addresses": 18446744073709551615,
        "available_count": 18446744073709551613, "reserved_count": 2, "allocated_count": 0,
    })
    html = _render(
        template_name="resources/ip_pools/list.html",
        overrides={"pools": [pool], "page": 1, "per_page": 20, "total_pages": 1, "page_window": [1]},
    )
    visible = re.sub(r"<[^>]+>", " ", html)

    testbase.assert_equal(("18446744073709551615" in visible, "≈ 2⁶⁴" in visible), (False, True))
    return


# ---------------------------------------------------------------------------
# RES-47: no phantom "Default" pool
# ---------------------------------------------------------------------------


def _pool_less_resource() -> Any:
    rtnval = build_fixture(
        ResourceResponse, mode=MODE_SPARSE, overrides={"pool_id": None, "pool_name": None, "tags": []},
    )
    return rtnval


def test_resource_detail_shows_a_dash_for_no_pool():
    """
    **Feature: resources (RES-47 no phantom pool)**
    **Property: a resource in no pool shows "—" in its Pool row, not a
    "Default" pool that does not exist.**
    """
    html = _render(template_name="resources/resources/detail.html", overrides={"resource": _pool_less_resource()})
    row = re.search(r'<th scope="row">Pool</th>\s*<td>(.*?)</td>', html, re.DOTALL)

    testbase.assert_equal(row.group(1).strip() if row is not None else None, "—")
    return


def test_resource_list_shows_a_dash_for_no_pool():
    """
    **Feature: resources (RES-47 no phantom pool)**
    **Property: the resource list never labels a pool-less resource as
    being in a "Default" pool.**
    """
    html = _render(
        template_name="resources/resources/list.html",
        overrides={"resources": [_pool_less_resource()], "resource_total": 1},
    )

    testbase.assert_equal(">Default<" in html, False)
    return


def test_health_dashboard_shows_a_dash_for_no_pool():
    """
    **Feature: resources (RES-47 no phantom pool)**
    **Property: the health dashboard never labels a pool-less resource
    as being in a "Default" pool.**
    """
    groups = {"online": [_pool_less_resource()], "degraded": [], "maintenance": [], "offline": []}
    html = _render(
        template_name="resources/health/dashboard.html",
        overrides={"health_groups": groups, "health_counts": {"online": 1, "degraded": 0, "maintenance": 0, "offline": 0}, "total_count": 1},
    )

    testbase.assert_equal(">Default<" in html, False)
    return


def test_create_form_offers_no_pool_when_none_is_the_default():
    """
    **Feature: resources (RES-47 no phantom pool)**
    **Property: with no pool flagged as the default, the create form's
    empty choice reads "No pool", not "Default Pool".**
    """
    pools = [build_fixture(ResourcePoolResponse, mode=MODE_SPARSE, overrides={"name": "lab-a", "is_default": False})]
    html = _render(template_name="resources/resources/create.html", overrides={"pools": pools, "form_data": None})

    testbase.assert_equal(re.search(r'<option value="">([^<]*)</option>', html).group(1), "No pool")
    return


def test_create_form_names_the_real_default_pool():
    """
    **Feature: resources (RES-47 no phantom pool)**
    **Property: when a pool is flagged as the default, the empty choice
    names it ("Default pool (lab-a)"), since that is where the resource
    goes.**
    """
    pools = [build_fixture(ResourcePoolResponse, mode=MODE_SPARSE, overrides={"name": "lab-a", "is_default": True})]
    html = _render(template_name="resources/resources/create.html", overrides={"pools": pools, "form_data": None})

    testbase.assert_equal(re.search(r'<option value="">([^<]*)</option>', html).group(1), "Default pool (lab-a)")
    return
