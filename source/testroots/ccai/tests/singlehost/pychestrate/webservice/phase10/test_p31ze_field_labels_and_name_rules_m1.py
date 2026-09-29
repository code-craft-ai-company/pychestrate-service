"""
.. module:: test_p31ze_field_labels_and_name_rules_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Search boxes have labels, name fields say what they accept,
               and variable names may contain periods (XC-27, XC-22).

.. moduleauthor:: Code Craft AI LLC

* **XC-27**: the users and variables search boxes had only a placeholder
  for a name, which vanishes as soon as a person types and is not a label.
  A crawl of every reachable server-rendered page found no other input
  without an accessible name.
* **XC-22**: name fields blocked what they did not accept with the
  browser's "Please match the requested format", and the variable form
  refused the periods the system's own variable names use
  (``ui.profile.surfaces``). Every patterned input now carries a title that
  states its rule, which the browser adds to its message, the variable
  form allows periods and states its rule, and the server refuses a bad
  variable name beside the name field.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import os
import re
import uuid

from typing import List

from ccai import testbase

import ccai.pychestrate.webservice.webinterface as webinterface_package

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    get,
    post_form,
)


def _suffix() -> str:
    return uuid.uuid4().hex[:8]


def _input_tag(page: str, field_id: str) -> str:
    match = re.search(r'<input[^>]*\bid="' + re.escape(field_id) + r'"[^>]*>', page, re.S)
    return match.group(0) if match is not None else ""


def test_the_users_and_variables_search_boxes_have_a_label():
    """
    **Feature: accessible names (XC-27)**
    **Property: the search input on the users list and on the variables
    list has an aria-label, so it is named once the placeholder is gone.**
    """
    admin = admin_cookies()
    tags = []
    for path in ("/admin/users", "/admin/variables"):
        page = get(path=path, cookies=admin).text
        tags.append(re.search(r'<input[^>]*name="search"[^>]*>', page).group(0))

    testbase.assert_equal(
        ('aria-label="Search users"' in tags[0], 'aria-label="Search variables"' in tags[1]),
        (True, True),
    )
    return


def _template_files() -> List[str]:
    root = os.path.dirname(os.path.abspath(webinterface_package.__file__))
    found = []
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if name.endswith(".html"):
                found.append(os.path.join(folder, name))
    return sorted(found)


def _input_tags(source: str) -> List[str]:
    """Every <input ...> tag in a template, whole, skipping over {{ }} and {% %} that may hold a '>'."""
    tags = []
    position = 0
    while True:
        start = source.find("<input", position)
        if start == -1:
            return tags
        index = start
        while index < len(source):
            if source.startswith("{{", index) or source.startswith("{%", index):
                closer = "}}" if source.startswith("{{", index) else "%}"
                end = source.find(closer, index)
                index = len(source) if end == -1 else end + 2
                continue
            if source[index] == ">":
                break
            index += 1
        tags.append(source[start:index + 1])
        position = index + 1


def test_every_input_with_a_pattern_says_what_it_accepts():
    """
    **Feature: name rules (XC-22)**
    **Property: no template has an input with a pattern attribute and no
    title, so the browser's refusal always names the rule; this scans every
    template of the web interface.**
    """
    without_title = []
    checked = 0
    for path in _template_files():
        with open(path, encoding="utf-8") as handle:
            source = handle.read()
        for tag in _input_tags(source):
            if re.search(r"\spattern=", tag) is None:
                continue
            checked += 1
            if re.search(r"\stitle=", tag) is None:
                without_title.append(os.path.relpath(path, os.path.dirname(os.path.dirname(webinterface_package.__file__))))

    testbase.assert_equal((checked >= 15, without_title), (True, []))
    return


def test_the_variable_form_allows_periods_and_states_its_rule():
    """
    **Feature: name rules (XC-22)**
    **Property: the variable form's name input accepts periods, has a title
    with the rule, and the help text under it gives the rule with the
    system's own name as an example.**
    """
    admin = admin_cookies()
    page = html.unescape(get(path="/admin/variables/create", cookies=admin).text)
    tag = _input_tag(page, "name")

    testbase.assert_equal(
        ('pattern="[a-zA-Z][a-zA-Z0-9_.]{0,127}"' in tag, 'title="Letters, digits, underscores and periods' in tag,
         "ui.profile.surfaces" in page),
        (True, True, True),
    )
    return


def test_a_variable_name_with_periods_can_be_created():
    """
    **Feature: name rules (XC-22)**
    **Property: a variable named like the system's own (ui.test.<id>) is
    created, and appears on the variables list.**
    """
    admin = admin_cookies()
    name = "ui.test.v{}".format(_suffix())
    response = post_form(
        path="/admin/variables/create",
        fields={"name": name, "var_type": "string", "value": "on", "default_value": "", "description": ""}, cookies=admin,
    )
    listing = get(path="/admin/variables", cookies=admin, query={"search": name}).text

    testbase.assert_equal((response.status_code, name in listing), (303, True))
    return


def test_a_bad_variable_name_is_refused_beside_the_name_field_with_the_rule():
    """
    **Feature: name rules (XC-22)**
    **Property: a name with a space, or one that starts with a digit, is
    refused (400) with the rule beside the name input, which keeps what was
    typed; no variable is made.**
    """
    admin = admin_cookies()
    results = []
    for bad in ("my var!", "1starts_with_a_digit"):
        response = post_form(
            path="/admin/variables/create",
            fields={"name": bad, "var_type": "string", "value": "x", "default_value": "", "description": ""}, cookies=admin,
        )
        page = html.unescape(response.text)
        message = re.search(r'id="name-error"[^>]*>(.*?)</div>', page, re.S)
        results.append((
            response.status_code,
            message is not None and "letters, digits, underscores and periods" in message.group(1).lower(),
            'aria-invalid="true"' in _input_tag(page, "name"),
            'value="{}"'.format(bad) in _input_tag(page, "name"),
        ))

    testbase.assert_equal(results, [(400, True, True, True), (400, True, True, True)])
    return


def test_the_project_name_field_says_spaces_are_not_allowed():
    """
    **Feature: name rules (XC-22)**
    **Property: the project create form's name input has a title that says
    spaces are not allowed, and a name with a space posted anyway is
    refused (400) beside the name field.**
    """
    admin = admin_cookies()
    page = html.unescape(get(path="/projects/create", cookies=admin).text)
    response = post_form(path="/projects/create", fields={"name": "Checkout Service", "description": "", "metadata": ""}, cookies=admin)

    testbase.assert_equal(
        ("Spaces are not allowed" in _input_tag(page, "name"), response.status_code, 'id="name-error"' in response.text),
        (True, 400, True),
    )
    return
