"""
.. module:: test_p31zh_variables_strict_and_kept_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Variables: booleans are strict, a deleted variable's history
               is kept and readable, and values are masked on every page
               (ADM-36).

.. moduleauthor:: Code Craft AI LLC

* "yes", "on" and "1" silently became true (and "no", "off", "0" false) in
  a boolean variable, though the form says to use true or false. Only
  true and false, in any case, are accepted now, and anything else is
  refused beside the value field.
* Deleting a variable made its history unreachable: the page redirected
  to "Variable not found", although the rows are kept (they are keyed by
  name). The history of a deleted variable is shown, marked as deleted,
  and the delete message says where to find it.
* The list masked values behind a Show button while the detail and history
  pages printed them. All three now hide values until asked.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import html
import re
import uuid

from typing import Dict

from ccai import testbase

from ccai.pychestrate.core.managers.global_variable_store import GlobalVariableStore, VariableType
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_variables import format_variable_value

from ccai.tests.singlehost.pychestrate.webservice.phase10._adm_helpers import (
    admin_cookies,
    get,
    merge_cookies,
    post_form,
)


def _name() -> str:
    return "ui.test.strict{}".format(uuid.uuid4().hex[:8])


def _create(cookies: Dict[str, str], name: str, var_type: str, value: str) -> object:
    return post_form(
        path="/admin/variables/create",
        fields={"name": name, "var_type": var_type, "value": value, "default_value": "", "description": ""}, cookies=cookies,
    )


def test_only_true_and_false_are_booleans():
    """
    **Feature: variables (ADM-36)**
    **Property: the form's parser accepts "true" and "false" in any case
    (and with spaces around), and refuses "yes", "no", "on", "off", "1",
    "0" and a typo, saying to use true or false.**
    """
    store = GlobalVariableStore(None)
    accepted = [store.parse_value_from_string(text, VariableType.BOOLEAN) for text in ("true", "FALSE", " True ")]
    refused = []
    for text in ("yes", "no", "on", "off", "1", "0", "ture", ""):
        try:
            store.parse_value_from_string(text, VariableType.BOOLEAN)
            refused.append((text, "accepted"))
        except ValueError as refusal:
            refused.append((text, "use 'true' or 'false'" in str(refusal)))

    testbase.assert_equal(
        (accepted, refused),
        ([True, False, True], [(text, True) for text in ("yes", "no", "on", "off", "1", "0", "ture", "")]),
    )
    return


def test_the_form_refuses_yes_beside_the_value_field_and_accepts_true():
    """
    **Feature: variables (ADM-36)**
    **Property: creating a boolean variable with the value "yes" answers
    400 with the message beside the value field and no variable made;
    "TRUE" creates it.**
    """
    admin = admin_cookies()
    refused_name, accepted_name = _name(), _name()
    refused = _create(admin, refused_name, "boolean", "yes")
    accepted = _create(admin, accepted_name, "boolean", "TRUE")
    listing = get(path="/admin/variables", cookies=admin, query={"search": "ui.test.strict"}).text

    testbase.assert_equal(
        (refused.status_code, 'id="value-error"' in refused.text, "use &#39;true&#39; or &#39;false&#39;" in refused.text
         or "use 'true' or 'false'" in html.unescape(refused.text), refused_name in listing,
         accepted.status_code, accepted_name in listing),
        (400, True, True, False, 303, True),
    )
    return


def test_the_history_of_a_deleted_variable_is_still_readable():
    """
    **Feature: variables (ADM-36)**
    **Property: after a variable is edited and deleted, its history page
    still answers 200, is marked as deleted, lists the changes, and the
    delete message says the history is kept and where it is.**
    """
    admin = admin_cookies()
    name = _name()
    _create(admin, name, "string", "first value")
    post_form(path="/admin/variables/{}/edit".format(name), fields={"value": "second value", "default_value": "", "description": ""}, cookies=admin)
    deleted = post_form(path="/admin/variables/{}/delete".format(name), fields={}, cookies=admin)
    message = html.unescape(get(path=deleted.header("Location") or "/", cookies=merge_cookies(cookies=admin, response=deleted)).text)
    history = html.unescape(get(path="/admin/variables/{}/history".format(name), cookies=admin).text)
    rows = re.findall(r"<tr>\s*<td>", history)

    testbase.assert_equal(
        ("Its history is kept" in message, "/admin/variables/{}/history".format(name) in message,
         'data-role="variable-deleted"' in history, len(rows) >= 3, "first value" in history and "second value" in history),
        (True, True, True, True, True),
    )
    return


def test_a_name_that_never_existed_still_redirects_away_from_history():
    """
    **Feature: variables (ADM-36)**
    **Property: the history of a name with no variable and no history
    redirects to the list, as before.**
    """
    admin = admin_cookies()
    response = get(path="/admin/variables/{}/history".format(_name()), cookies=admin)

    testbase.assert_equal(response.status_code in (302, 303), True)
    return


def test_values_are_hidden_until_asked_on_the_detail_and_history_pages():
    """
    **Feature: variables (ADM-36)**
    **Property: on the variable's page and its history the value sits in a
    hidden element behind a bullet mask, with a Show values button that
    the reveal script serves; nothing is shown in the open.**
    """
    admin = admin_cookies()
    name = _name()
    _create(admin, name, "string", "s3cret-value-9")
    detail = html.unescape(get(path="/admin/variables/{}".format(name), cookies=admin).text)
    post_form(path="/admin/variables/{}/edit".format(name), fields={"value": "changed-value-7", "default_value": "", "description": ""}, cookies=admin)
    history = html.unescape(get(path="/admin/variables/{}/history".format(name), cookies=admin).text)

    def hidden_only(page: str, value: str) -> bool:
        spans = re.findall(r'<(?:span|pre)[^>]*data-role="secret"([^>]*)>([^<]*)</(?:span|pre)>', page)
        holding = [attributes for attributes, text in spans if value in text]
        return len(holding) > 0 and all("hidden" in attributes for attributes in holding)

    testbase.assert_equal(
        (hidden_only(detail, "s3cret-value-9"), 'data-role="mask"' in detail, 'data-reveal-all="#variable-values"' in detail,
         hidden_only(history, "changed-value-7"), 'data-reveal-all="#history-values"' in history,
         "button[data-reveal-all]" in detail and "button[data-reveal-all]" in history),
        (True, True, True, True, True, True),
    )
    return


def test_a_deleted_variables_values_are_formatted_without_its_type():
    """
    **Feature: variables (ADM-36)**
    **Property: with no type to go by, a structure is shown as JSON, a
    boolean as true or false, and anything else as its text.**
    """
    testbase.assert_equal(
        (format_variable_value(value={"a": 1}, var_type=None), format_variable_value(value=True, var_type=None),
         format_variable_value(value="plain", var_type=None), format_variable_value(value=None, var_type=None)),
        ('{\n  "a": 1\n}', "true", "plain", ""),
    )
    return
