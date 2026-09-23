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
from typing import Any, Dict, Optional

from ccai import testbase

from ccai.testshared.factories.webui.dataclass_fixtures import (
    MODE_SPARSE,
    build_fixture,
)
from ccai.testshared.factories.webui.template_contexts import (
    build_template_context,
)

from ccai.pychestrate.core.managers.allocation_manager import ReservationResponse
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
