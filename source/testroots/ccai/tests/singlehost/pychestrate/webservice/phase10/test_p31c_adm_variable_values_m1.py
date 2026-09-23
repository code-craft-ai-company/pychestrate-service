"""
.. module:: test_p31c_adm_variable_values_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: JSON and boolean variables render as JSON / true-false,
               so an untouched edit form saves (audit ADM-09).

.. moduleauthor:: Code Craft AI LLC

The variable pages printed the deserialized Python object: a JSON
variable showed ``{'a': 1}`` and a boolean ``True``. The edit form's
textarea carried the same text, so saving it untouched failed with
"Invalid JSON". These tests pin the formatter and drive the real
routes end to end.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from ccai import testbase

from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_variables import (
    format_variable_value,
)

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    get,
    post_form,
)


_TEXTAREA_PATTERN = re.compile(
    r'<textarea id="value" name="value"[^>]*>(.*?)</textarea>', re.DOTALL
)


def _create_variable(*, cookies, var_type: str, value: str) -> str:
    name = "adm09_{}_{}".format(var_type, uuid.uuid4().hex[:8])
    response = post_form(
        path="/admin/variables/create",
        fields={
            "name": name,
            "var_type": var_type,
            "value": value,
            "description": "ADM-09 probe",
            "default_value": "",
        },
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 303)
    return name


def _edit_form_value(*, cookies, name: str) -> str:
    response = get(path="/admin/variables/{}/edit".format(name), cookies=cookies)
    testbase.assert_equal(response.status_code, 200)
    match = _TEXTAREA_PATTERN.search(response.text)
    testbase.assert_true(match is not None, "no value textarea")
    rtnval = html.unescape(match.group(1))
    return rtnval


def test_json_value_is_formatted_as_json():
    """
    **Feature: variable value rendering (ADM-09)**
    **Property: format_variable_value renders a JSON value with JSON
    syntax (double quotes), not Python repr.**
    """
    rendered = format_variable_value(value={"a": 1}, var_type="json")
    testbase.assert_equal(rendered, '{\n  "a": 1\n}')
    return


def test_boolean_value_is_formatted_lowercase():
    """
    **Feature: variable value rendering (ADM-09)**
    **Property: a boolean renders as "true" / "false".**
    """
    testbase.assert_equal(
        format_variable_value(value=True, var_type="boolean"), "true"
    )
    return


def test_missing_value_is_formatted_empty():
    """
    **Feature: variable value rendering (ADM-09)**
    **Property: None renders as an empty string, not "None".**
    """
    testbase.assert_equal(format_variable_value(value=None, var_type="string"), "")
    return


def test_json_detail_page_shows_json_not_python_repr():
    """
    **Feature: variable value rendering (ADM-09)**
    **Property: the detail page of a JSON variable shows "a": 1 and
    never {'a': 1}.**
    """
    cookies = admin_cookies()
    name = _create_variable(cookies=cookies, var_type="json", value='{"a": 1}')
    response = get(path="/admin/variables/{}".format(name), cookies=cookies)
    text = html.unescape(response.text)
    testbase.assert_equal("{'a': 1}" in text, False)
    testbase.assert_true('"a": 1' in text, "JSON value not shown")
    return


def test_untouched_json_edit_form_saves():
    """
    **Feature: variable value rendering (ADM-09)**
    **Property: submitting the JSON variable's edit form with the value
    it rendered succeeds (redirect to the detail page).**
    """
    cookies = admin_cookies()
    name = _create_variable(cookies=cookies, var_type="json", value='{"a": 1, "b": [true, null]}')
    rendered_value = _edit_form_value(cookies=cookies, name=name)
    response = post_form(
        path="/admin/variables/{}/edit".format(name),
        fields={"value": rendered_value, "description": "ADM-09 probe"},
        cookies=cookies,
    )
    testbase.assert_equal(response.status_code, 303)
    testbase.assert_equal(
        response.header("Location"), "/admin/variables/{}".format(name)
    )
    return


def test_boolean_edit_form_shows_lowercase_value():
    """
    **Feature: variable value rendering (ADM-09)**
    **Property: a boolean variable's edit form carries "true", the
    value the form's own help text asks for.**
    """
    cookies = admin_cookies()
    name = _create_variable(cookies=cookies, var_type="boolean", value="true")
    testbase.assert_equal(_edit_form_value(cookies=cookies, name=name), "true")
    return
