"""
.. module:: test_p31l_adm_form_field_errors_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Admin forms show a refused value's error next to its
               field and keep what was typed (ADM-11).

.. moduleauthor:: Code Craft AI LLC

Every admin form used to flash ``str(exc)`` above the page, never set
``aria-invalid``, and several edit forms threw away what was typed.
A validation error that names a field now renders next to that field
(``<name>-error``, ``aria-invalid``, ``aria-describedby``), is listed
in the error summary at the top of the form, and the form comes back
with the submitted values and a 400.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from typing import Any, Dict

from ccai import testbase

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import (
    create_project_via_ui,
    post_form,
)


GOOD_PASSWORD: str = "Correct-Horse-Battery-9"


def _setup() -> Dict[str, Any]:
    handle = ensure_app()
    cookies = logged_in_cookies(wsgi_app=handle.wsgi_app)
    rtnval = {"wsgi_app": handle.wsgi_app, "cookies": cookies}
    return rtnval


def _unique(prefix: str) -> str:
    rtnval = "{}-{}".format(prefix, uuid.uuid4().hex[:8])
    return rtnval


def _create_user(setup: Dict[str, Any], **overrides: str) -> Any:
    fields = {
        "username": _unique("fe"),
        "email": "{}@example.com".format(_unique("fe")),
        "password_setup": "password",
        "password": GOOD_PASSWORD,
        "display_name": "Field Errors",
        "firstname": "",
        "lastname": "",
    }
    fields.update(overrides)
    rtnval = post_form(
        wsgi_app=setup["wsgi_app"], path="/admin/users/create", cookies=setup["cookies"], fields=fields,
    )
    return rtnval


def _user_id_for(setup: Dict[str, Any], *, username: str) -> str:
    page = drive_request(
        wsgi_app=setup["wsgi_app"], method="GET", path="/admin/users",
        query_string="search=" + username, cookies=setup["cookies"],
    ).text
    match = re.search(r'href="/admin/users/([0-9a-f-]{36})"[^>]*>\s*' + re.escape(username), page)
    testbase.assert_true(match is not None, "user {} not listed".format(username))
    rtnval = match.group(1)
    return rtnval


def _input_tag(html: str, *, field_id: str) -> str:
    match = re.search(r'<input[^>]*\bid="' + re.escape(field_id) + r'"[^>]*>', html, re.S)
    rtnval = match.group(0) if match is not None else ""
    return rtnval


def test_create_user_bad_email_is_shown_next_to_the_email_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: creating a user with email "not-an-email@x" is refused
    with a 400 whose email input is aria-invalid and described by the
    email-error message.**
    """
    setup = _setup()
    response = _create_user(setup, email="not-an-email@x")
    email_input = _input_tag(response.text, field_id="email")

    testbase.assert_equal(
        (response.status_code, 'id="email-error"' in response.text,
         'aria-invalid="true"' in email_input, 'aria-describedby="email-error"' in email_input),
        (400, True, True, True),
    )
    return


def test_create_user_error_is_listed_in_the_summary_with_a_link_to_its_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: the refused create page opens with an error summary
    that links to the email input.**
    """
    setup = _setup()
    response = _create_user(setup, email="not-an-email@x")

    testbase.assert_equal(
        ('data-role="error-summary"' in response.text, 'href="#email"' in response.text),
        (True, True),
    )
    return


def test_create_user_refusal_keeps_the_typed_values():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: after a refused create the username and first name the
    admin typed are still in the form.**
    """
    setup = _setup()
    username = _unique("keep")
    response = _create_user(setup, username=username, firstname="Grace", email="broken@")

    testbase.assert_equal(
        ('value="{}"'.format(username) in _input_tag(response.text, field_id="username"),
         'value="Grace"' in _input_tag(response.text, field_id="firstname")),
        (True, True),
    )
    return


def test_create_user_duplicate_username_is_shown_next_to_the_username_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a second user with an existing username is refused with
    the error next to the username input.**
    """
    setup = _setup()
    username = _unique("dup")
    _create_user(setup, username=username)
    response = _create_user(setup, username=username)

    testbase.assert_equal(
        (response.status_code, 'id="username-error"' in response.text),
        (400, True),
    )
    return


def test_password_error_keeps_the_rules_description_on_the_input():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a refused password leaves the password input described
    by both the password rules and the error (one aria-describedby).**
    """
    setup = _setup()
    response = _create_user(setup, password="short")
    password_input = _input_tag(response.text, field_id="password")

    testbase.assert_equal(
        (response.status_code, password_input.count("aria-describedby="),
         'aria-describedby="password-rules password-error"' in password_input),
        (400, 1, True),
    )
    return


def test_edit_user_bad_email_keeps_the_typed_values_and_marks_the_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: saving a user's edit form with email "broken@" answers
    400, marks the email input, and keeps the display name that was
    typed rather than the stored one.**
    """
    setup = _setup()
    username = _unique("edit")
    _create_user(setup, username=username)
    user_id = _user_id_for(setup, username=username)
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/admin/users/{}/edit".format(user_id),
        cookies=setup["cookies"],
        fields={"email": "broken@", "display_name": "Typed Name", "firstname": "", "lastname": "", "is_active": "on"},
    )

    testbase.assert_equal(
        (response.status_code, 'id="email-error"' in response.text,
         'value="Typed Name"' in _input_tag(response.text, field_id="display_name"),
         'value="broken@"' in _input_tag(response.text, field_id="email")),
        (400, True, True, True),
    )
    return


# ---------------------------------------------------------------------------
# Global variables
# ---------------------------------------------------------------------------


def _create_variable(setup: Dict[str, Any], **overrides: str) -> Any:
    fields = {
        "name": _unique("fev").replace("-", "_"),
        "var_type": "integer",
        "value": "5",
        "default_value": "",
        "description": "",
    }
    fields.update(overrides)
    rtnval = post_form(
        wsgi_app=setup["wsgi_app"], path="/admin/variables/create", cookies=setup["cookies"], fields=fields,
    )
    return rtnval


def _textarea_text(html: str, *, field_id: str) -> str:
    match = re.search(r'<textarea[^>]*\bid="' + re.escape(field_id) + r'"[^>]*>(.*?)</textarea>', html, re.S)
    rtnval = match.group(1) if match is not None else ""
    return rtnval


def test_create_variable_unparseable_value_is_shown_next_to_the_value_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: an integer variable with the value "forty-two" is
    refused (400) with the error next to the value input, which keeps
    what was typed.**
    """
    setup = _setup()
    response = _create_variable(setup, value="forty-two")

    testbase.assert_equal(
        (response.status_code, 'id="value-error"' in response.text,
         'aria-invalid="true"' in re.search(r'<textarea[^>]*\bid="value"[^>]*>', response.text).group(0),
         _textarea_text(response.text, field_id="value")),
        (400, True, True, "forty-two"),
    )
    return


def test_create_variable_unparseable_default_is_blamed_on_the_default_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a bad default value marks the default value input, not
    the value input.**
    """
    setup = _setup()
    response = _create_variable(setup, default_value="nope")

    testbase.assert_equal(
        ('id="default_value-error"' in response.text, 'id="value-error"' in response.text),
        (True, False),
    )
    return


def test_create_variable_duplicate_name_is_shown_next_to_the_name_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: creating a variable whose name exists is refused with
    the error next to the name input.**
    """
    setup = _setup()
    name = _unique("dupv").replace("-", "_")
    _create_variable(setup, name=name)
    response = _create_variable(setup, name=name)

    testbase.assert_equal(
        (response.status_code, 'id="name-error"' in response.text), (400, True),
    )
    return


def test_edit_variable_bad_value_keeps_the_typed_text_and_marks_the_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: saving an integer variable with "seven" answers 400,
    marks the value input, and shows "seven" and the typed description
    instead of the stored ones.**
    """
    setup = _setup()
    name = _unique("editv").replace("-", "_")
    _create_variable(setup, name=name, value="7", description="stored description")
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/admin/variables/{}/edit".format(name),
        cookies=setup["cookies"],
        fields={"value": "seven", "description": "typed description"},
    )

    testbase.assert_equal(
        (response.status_code, 'id="value-error"' in response.text,
         _textarea_text(response.text, field_id="value"),
         _textarea_text(response.text, field_id="description")),
        (400, True, "seven", "typed description"),
    )
    return


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------


def _create_role(setup: Dict[str, Any], **overrides: Any) -> Any:
    fields = {"name": _unique("role"), "description": "made by a test"}
    fields.update(overrides)
    rtnval = post_form(
        wsgi_app=setup["wsgi_app"], path="/admin/roles/create", cookies=setup["cookies"], fields=fields,
    )
    return rtnval


def test_create_role_without_a_name_is_shown_next_to_the_name_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: creating a role with a blank name is refused (400) with
    the error next to the name input, and the typed description is
    kept.**
    """
    setup = _setup()
    response = _create_role(setup, name="", description="typed description")

    testbase.assert_equal(
        (response.status_code, 'id="name-error"' in response.text,
         _textarea_text(response.text, field_id="description")),
        (400, True, "typed description"),
    )
    return


def test_create_role_duplicate_name_is_shown_next_to_the_name_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a second role with an existing name is refused with the
    error next to the name input.**
    """
    setup = _setup()
    name = _unique("duprole")
    _create_role(setup, name=name)
    response = _create_role(setup, name=name)

    testbase.assert_equal(
        (response.status_code, 'id="name-error"' in response.text), (400, True),
    )
    return


def _role_id_for(setup: Dict[str, Any], *, name: str) -> str:
    page = drive_request(
        wsgi_app=setup["wsgi_app"], method="GET", path="/admin/roles",
        query_string="search=" + name, cookies=setup["cookies"],
    ).text
    match = re.search(r'href="/admin/roles/([0-9a-f-]{36})"[^>]*>\s*' + re.escape(name), page)
    testbase.assert_true(match is not None, "role {} not listed".format(name))
    rtnval = match.group(1)
    return rtnval


def test_edit_role_removing_every_permission_unconfirmed_is_a_permissions_error():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: saving a role that has permissions with none selected
    and no confirmation is refused (400) with the error on the
    permissions group, the typed description kept, and the confirmation
    disclosure open.**
    """
    setup = _setup()
    name = _unique("editrole")
    handle_permissions = re.findall(
        r'name="permission_keys" value="([^"]+)"',
        drive_request(wsgi_app=setup["wsgi_app"], method="GET", path="/admin/roles/create", cookies=setup["cookies"]).text,
    )
    testbase.assert_true(len(handle_permissions) > 0, "the catalog offered no permissions")
    _create_role(setup, name=name, permission_keys=handle_permissions[0])
    role_id = _role_id_for(setup, name=name)
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/admin/roles/{}/edit".format(role_id),
        cookies=setup["cookies"],
        fields={"description": "typed description"},
    )

    testbase.assert_equal(
        (response.status_code, 'id="permission_keys-error"' in response.text,
         '<details class="form-group" open>' in response.text,
         _textarea_text(response.text, field_id="description")),
        (400, True, True, "typed description"),
    )
    return


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


def _create_resource(setup: Dict[str, Any], **overrides: str) -> Any:
    fields = {
        "name": _unique("res"),
        "resource_type": "device",
        "pool_id": "",
        "description": "",
        "capacity": "1",
        "metadata": "{}",
    }
    fields.update(overrides)
    rtnval = post_form(
        wsgi_app=setup["wsgi_app"], path="/resources/create", cookies=setup["cookies"], fields=fields,
    )
    return rtnval


def test_create_resource_bad_metadata_is_shown_next_to_the_metadata_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a resource with metadata "{not json" is refused (400)
    with the error next to the metadata input, which keeps the typed
    text, and the typed name is kept.**
    """
    setup = _setup()
    name = _unique("resmeta")
    response = _create_resource(setup, name=name, metadata="{not json")

    testbase.assert_equal(
        (response.status_code, 'id="metadata-error"' in response.text,
         _textarea_text(response.text, field_id="metadata"),
         'value="{}"'.format(name) in _input_tag(response.text, field_id="name")),
        (400, True, "{not json", True),
    )
    return


def test_create_resource_zero_capacity_is_shown_next_to_the_capacity_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a resource with capacity 0 is refused with the error on
    the capacity input, not the metadata input.**
    """
    setup = _setup()
    response = _create_resource(setup, capacity="0")
    capacity_input = _input_tag(response.text, field_id="capacity")

    testbase.assert_equal(
        (response.status_code, 'id="capacity-error"' in response.text,
         'aria-invalid="true"' in capacity_input, 'id="metadata-error"' in response.text),
        (400, True, True, False),
    )
    return


def test_create_resource_duplicate_name_is_shown_next_to_the_name_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a second resource with an existing name is refused with
    the error next to the name input.**
    """
    setup = _setup()
    name = _unique("resdup")
    _create_resource(setup, name=name)
    response = _create_resource(setup, name=name)

    testbase.assert_equal(
        (response.status_code, 'id="name-error"' in response.text), (400, True),
    )
    return


def test_edit_resource_bad_metadata_answers_400_and_keeps_the_typed_description():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: saving a resource's edit form with metadata "[1, 2]"
    answers 400 with the error on the metadata input and keeps the
    description that was typed.**
    """
    setup = _setup()
    created = _create_resource(setup, name=_unique("resedit"))
    resource_id = (created.header("Location") or "").rstrip("/").split("/")[-1]
    testbase.assert_true(resource_id.isdigit(), "create redirected to {}".format(created.header("Location")))
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/resources/{}/edit".format(resource_id),
        cookies=setup["cookies"],
        fields={"description": "typed description", "capacity": "1", "metadata": "[1, 2]"},
    )

    testbase.assert_equal(
        (response.status_code, 'id="metadata-error"' in response.text,
         _textarea_text(response.text, field_id="description")),
        (400, True, "typed description"),
    )
    return


# ---------------------------------------------------------------------------
# IP pools
# ---------------------------------------------------------------------------


def _create_ip_pool(setup: Dict[str, Any], **overrides: str) -> Any:
    octet = uuid.uuid4().int % 200 + 20
    fields = {
        "name": _unique("ippool"),
        "cidr": "10.{}.{}.0/29".format(octet, uuid.uuid4().int % 200 + 20),
        "gateway": "",
        "dns_servers": "",
        "reserved_ips": "",
        "description": "",
    }
    fields.update(overrides)
    rtnval = post_form(
        wsgi_app=setup["wsgi_app"], path="/resources/ip-pools/create", cookies=setup["cookies"], fields=fields,
    )
    return rtnval


def test_create_ip_pool_bad_cidr_is_shown_next_to_the_cidr_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: an IP pool with range "not-a-range" is refused (400)
    with the error next to the CIDR input, and the typed name is
    kept.**
    """
    setup = _setup()
    name = _unique("ipbad")
    response = _create_ip_pool(setup, name=name, cidr="not-a-range")

    testbase.assert_equal(
        (response.status_code, 'id="cidr-error"' in response.text,
         'aria-invalid="true"' in _input_tag(response.text, field_id="cidr"),
         'value="{}"'.format(name) in _input_tag(response.text, field_id="name")),
        (400, True, True, True),
    )
    return


def test_create_ip_pool_bad_dns_server_is_shown_next_to_the_dns_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a DNS server "example" is refused with the error on the
    DNS servers input and the CIDR input left unmarked.**
    """
    setup = _setup()
    response = _create_ip_pool(setup, dns_servers="example")

    testbase.assert_equal(
        ('id="dns_servers-error"' in response.text, 'id="cidr-error"' in response.text),
        (True, False),
    )
    return


def test_create_ip_pool_duplicate_name_is_shown_next_to_the_name_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a second IP pool with an existing name is refused with
    the error next to the name input.**
    """
    setup = _setup()
    name = _unique("ipdup")
    _create_ip_pool(setup, name=name)
    response = _create_ip_pool(setup, name=name)

    testbase.assert_equal(
        (response.status_code, 'id="name-error"' in response.text), (400, True),
    )
    return


def test_edit_ip_pool_gateway_outside_the_range_answers_400_and_keeps_the_typed_text():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: saving an IP pool with a gateway outside its range
    answers 400 with the error on the gateway input and keeps the
    description that was typed.**
    """
    setup = _setup()
    created = _create_ip_pool(setup, cidr="10.77.{}.0/29".format(uuid.uuid4().int % 200 + 20))
    pool_id = (created.header("Location") or "").rstrip("/").split("/")[-1]
    testbase.assert_true(pool_id.isdigit(), "create redirected to {}".format(created.header("Location")))
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/resources/ip-pools/{}/edit".format(pool_id),
        cookies=setup["cookies"],
        fields={
            "gateway": "192.0.2.1", "dns_servers": "", "reserved_ips": "",
            "description": "typed description",
        },
    )

    testbase.assert_equal(
        (response.status_code, 'id="gateway-error"' in response.text,
         _textarea_text(response.text, field_id="description")),
        (400, True, "typed description"),
    )
    return


# ---------------------------------------------------------------------------
# Reservations
# ---------------------------------------------------------------------------


def _reservation_fields(resource_id: str, **overrides: str) -> Dict[str, str]:
    fields = {
        "resource_id": resource_id,
        "start_time": "2031-03-01T10:00",
        "end_time": "2031-03-01T11:00",
        "tz": "UTC",
        "mode": "exclusive",
        "job_id": "",
        "reason": "",
    }
    fields.update(overrides)
    return fields


def _new_resource_id(setup: Dict[str, Any]) -> str:
    created = _create_resource(setup)
    rtnval = (created.header("Location") or "").rstrip("/").split("/")[-1]
    testbase.assert_true(rtnval.isdigit(), "create redirected to {}".format(created.header("Location")))
    return rtnval


def test_create_reservation_without_times_marks_both_time_fields():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a reservation submitted with no start or end time is
    refused (400) with an error on each time input, and no banner.**
    """
    setup = _setup()
    response = post_form(
        wsgi_app=setup["wsgi_app"], path="/resources/reservations/create", cookies=setup["cookies"],
        fields=_reservation_fields(_new_resource_id(setup), start_time="", end_time=""),
    )

    testbase.assert_equal(
        (response.status_code, 'id="start_time-error"' in response.text, 'id="end_time-error"' in response.text),
        (400, True, True),
    )
    return


def test_create_reservation_without_a_resource_marks_the_resource_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a reservation with no resource chosen is refused with
    the error on the resource select, and the typed times are kept.**
    """
    setup = _setup()
    response = post_form(
        wsgi_app=setup["wsgi_app"], path="/resources/reservations/create", cookies=setup["cookies"],
        fields=_reservation_fields(""),
    )

    testbase.assert_equal(
        (response.status_code, 'id="resource_id-error"' in response.text,
         'value="2031-03-01T10:00"' in _input_tag(response.text, field_id="start_time")),
        (400, True, True),
    )
    return


def test_create_reservation_ending_before_it_starts_marks_the_end_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: an end time before the start time is refused with the
    error on the end time input.**
    """
    setup = _setup()
    response = post_form(
        wsgi_app=setup["wsgi_app"], path="/resources/reservations/create", cookies=setup["cookies"],
        fields=_reservation_fields(_new_resource_id(setup), start_time="2031-03-01T12:00", end_time="2031-03-01T11:00"),
    )
    end_input = _input_tag(response.text, field_id="end_time")

    testbase.assert_equal(
        (response.status_code, 'id="end_time-error"' in response.text,
         'aria-describedby="reservation-zone-note end_time-error"' in end_input),
        (400, True, True),
    )
    return


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def _create_project(setup: Dict[str, Any], **overrides: str) -> Any:
    fields = {"name": _unique("prj"), "description": "", "metadata": ""}
    fields.update(overrides)
    rtnval = post_form(
        wsgi_app=setup["wsgi_app"], path="/projects/create", cookies=setup["cookies"], fields=fields,
    )
    return rtnval


def test_create_project_with_an_invalid_name_is_shown_next_to_the_name_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a project named "not a valid name!" is refused (400)
    with the error next to the name input, which keeps what was typed,
    along with the typed description.**
    """
    setup = _setup()
    response = _create_project(setup, name="not a valid name!", description="typed description")

    testbase.assert_equal(
        (response.status_code, 'id="name-error"' in response.text,
         'aria-invalid="true"' in _input_tag(response.text, field_id="name"),
         'value="not a valid name!"' in _input_tag(response.text, field_id="name"),
         _textarea_text(response.text, field_id="description")),
        (400, True, True, True, "typed description"),
    )
    return


def test_create_project_with_bad_metadata_is_shown_next_to_the_metadata_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: project metadata that is not JSON is refused with the
    error on the metadata input and none on the name.**
    """
    setup = _setup()
    response = _create_project(setup, metadata="{oops")

    testbase.assert_equal(
        (response.status_code, 'id="metadata-error"' in response.text, 'id="name-error"' in response.text),
        (400, True, False),
    )
    return


def test_create_project_duplicate_name_is_shown_next_to_the_name_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a second project with an existing name is refused with
    the error next to the name input.**
    """
    setup = _setup()
    name = _unique("prjdup")
    _create_project(setup, name=name)
    response = _create_project(setup, name=name)

    testbase.assert_equal(
        (response.status_code, 'id="name-error"' in response.text), (400, True),
    )
    return


def test_edit_project_with_an_invalid_name_keeps_the_typed_name_and_marks_it():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: saving a project's edit form with an invalid name
    answers 400, marks the name input, and shows the typed name rather
    than the stored one.**
    """
    setup = _setup()
    project_id = create_project_via_ui(wsgi_app=setup["wsgi_app"], cookies=setup["cookies"], prefix="prjedit")
    response = post_form(
        wsgi_app=setup["wsgi_app"],
        path="/projects/{}/edit".format(project_id),
        cookies=setup["cookies"],
        fields={"name": "still not valid!", "description": "d", "metadata": ""},
    )

    testbase.assert_equal(
        (response.status_code, 'id="name-error"' in response.text,
         'value="still not valid!"' in _input_tag(response.text, field_id="name")),
        (400, True, True),
    )
    return


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------


def test_create_secret_in_a_missing_scope_is_shown_next_to_the_scope_field():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: a secret created in a scope that does not exist is
    refused (400) with the error on the scope select, and the typed name
    is kept.**
    """
    setup = _setup()
    name = _unique("sec").replace("-", "_")
    response = post_form(
        wsgi_app=setup["wsgi_app"], path="/admin/secrets/create", cookies=setup["cookies"],
        fields={
            "scope_id": "987654", "name": name, "secret_type": "generic",
            "value": "s3cret-value-that-must-not-come-back", "description": "",
        },
    )

    testbase.assert_equal(
        (response.status_code, 'id="scope_id-error"' in response.text,
         'value="{}"'.format(name) in _input_tag(response.text, field_id="name")),
        (400, True, True),
    )
    return


def test_a_refused_secret_never_echoes_the_value_back():
    """
    **Feature: admin form field errors (ADM-11)**
    **Property: the re-rendered create-secret page does not contain the
    secret value that was submitted.**
    """
    setup = _setup()
    response = post_form(
        wsgi_app=setup["wsgi_app"], path="/admin/secrets/create", cookies=setup["cookies"],
        fields={
            "scope_id": "987654", "name": _unique("sec2").replace("-", "_"), "secret_type": "generic",
            "value": "s3cret-value-that-must-not-come-back", "description": "",
        },
    )

    testbase.assert_equal("s3cret-value-that-must-not-come-back" in response.text, False)
    return
