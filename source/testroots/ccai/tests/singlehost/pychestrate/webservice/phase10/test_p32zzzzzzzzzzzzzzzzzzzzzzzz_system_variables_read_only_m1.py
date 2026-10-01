"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzz_system_variables_read_only_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A variable the product owns cannot be edited or deleted on the Variables pages (ADM-08).

.. moduleauthor:: Code Craft AI LLC

``ui.profile.surfaces`` is the deployment-wide interface profile. The Variables pages offered Edit and Delete for it like any
other variable, so a typo or a delete there changed how the whole interface looks for everyone, bypassing the Interface profile
page that checks what it saves. It now stays visible (marked *system*) but read-only: no Edit and no Delete on the list or its
page, a note saying where to change it, and the handlers refuse an edit, a delete and the creation of a variable with that
name. Ordinary variables are unchanged. The handlers run here against the harness's real in-memory database.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re
import uuid

from typing import Dict

from ccai import testbase

from ccai.pychestrate.core.managers.global_variable_store import GlobalVariableStore
from ccai.pychestrate.webservice.webinterface.site_shell import ui_profile

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm


OWNED: str = ui_profile.DEPLOYMENT_VARIABLE_NAME


def _seed_profile() -> None:
    """Create the owned variable the way the Interface profile page does (after the app and its event wiring are up)."""
    session = adm.open_db_session()
    try:
        ui_profile.set_deployment_surfaces(db_session=session, surfaces=list(ui_profile.ALL_SURFACE_VALUES), actor_id=None)
        session.commit()
    finally:
        session.close()
    return


def _stored_value() -> object:
    session = adm.open_db_session()
    try:
        variable = GlobalVariableStore(session).get_variable(OWNED)
        return None if variable is None else variable.value
    finally:
        session.close()


def _own_row(html: str) -> str:
    """The list row (one ``<tr>``) that mentions the owned variable."""
    for row in re.findall(r"<tr>.*?</tr>", html, flags=re.S):
        if ">{}<".format(OWNED) in row:
            return row
    return ""


def _flash_after(cookies: Dict[str, str], response, path: str) -> str:
    merged = dict(cookies)
    merged.update(response.collect_set_cookies())
    return " ".join(re.sub(r"<[^>]+>", " ", adm.get(path=path, cookies=merged).text).split())


def test_the_list_and_the_page_mark_it_system_and_offer_no_edit_or_delete():
    """
    **Feature: variables (ADM-08)**
    **Property: the owned variable's list row carries a "system" mark and has History but no Edit and no Delete; its page
    says where to change it and offers no Edit or Delete; an ordinary variable keeps both.**
    """
    cookies = adm.admin_cookies()
    _seed_profile()
    ordinary = "ui.test.ordinary{}".format(uuid.uuid4().hex[:8])
    adm.post_form(path="/admin/variables/create", fields={"name": ordinary, "var_type": "string", "value": "x", "default_value": "", "description": ""}, cookies=cookies)

    listing = adm.get(path="/admin/variables", cookies=cookies, query={"search": "ui."}).text
    owned_row = _own_row(listing)
    ordinary_row = next((row for row in re.findall(r"<tr>.*?</tr>", listing, flags=re.S) if ">{}<".format(ordinary) in row), "")
    page = adm.get(path="/admin/variables/{}".format(OWNED), cookies=cookies).text

    testbase.assert_equal(
        (
            'data-role="system-owned"' in owned_row, "/edit" in owned_row, "/delete" in owned_row, "/history" in owned_row,
            "/edit" in ordinary_row, "/delete" in ordinary_row,
            'data-role="system-owned-note"' in page, "/ui-profile" in page, "/edit" in page, "/delete" in page,
        ),
        (True, False, False, True, True, True, True, True, False, False),
    )
    return


def test_an_edit_a_delete_and_a_new_variable_with_that_name_are_refused_and_nothing_changes():
    """
    **Feature: variables (ADM-08)**
    **Property: opening the edit page, posting an edit and posting a delete for the owned variable each redirect with a
    message that says to use the Interface profile page and leave its value as it was; creating a variable with that name
    is refused beside the name field.**
    """
    cookies = adm.admin_cookies()
    _seed_profile()
    before = _stored_value()
    testbase.assert_equal(before is not None, True)

    open_edit = adm.get(path="/admin/variables/{}/edit".format(OWNED), cookies=cookies)
    edit = adm.post_form(path="/admin/variables/{}/edit".format(OWNED), fields={"value": '["automation"]', "description": "changed"}, cookies=cookies)
    delete = adm.post_form(path="/admin/variables/{}/delete".format(OWNED), fields={}, cookies=cookies)
    create = adm.post_form(path="/admin/variables/create", fields={"name": OWNED, "var_type": "json", "value": "[]", "default_value": "", "description": ""}, cookies=cookies)
    message = _flash_after(cookies, delete, "/admin/variables/{}".format(OWNED))

    testbase.assert_equal(
        (
            open_edit.status_code in (302, 303), edit.status_code in (302, 303), delete.status_code in (302, 303),
            "managed by the product" in message and "Interface profile" in message,
            create.status_code, "managed by the product" in create.text,
            _stored_value() == before,
        ),
        (True, True, True, True, 400, True, True),
    )
    return
