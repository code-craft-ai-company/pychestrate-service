"""
.. module:: test_p32zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz_permanent_deletes_ask_for_the_name_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Permanent deletions on the server-rendered pages ask for the name to be typed (XC-15).

.. moduleauthor:: Code Craft AI LLC

Deleting a project, a pool or a secret in the bundle views asks for the name to be typed; the same deletions on the server-rendered pages used the
ordinary confirm. The rule, recorded here: a deletion asks for the name when it is permanent and removes something that other records depend on or
that holds history, and it is rare enough that typing a name costs nothing: a role (its holders lose it), a device (its allocation, reservation and
health history goes with it), a resource pool, an IP pool, retiring an RPA job type, and deleting a user (in the list and on the user's page; the login name is typed) (a secret, every version, asks too, in the vault's bundle view; the server-rendered legacy secret page is gone). Reversible or small actions keep the
ordinary confirm: removing a member, revoking a token, cancelling a reservation, deleting a tag. This lint reads every server-rendered template, so a new
page with one of these forms cannot forget it.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import os
import re
import uuid

from typing import Dict, List

from ccai import testbase

from ccai.pychestrate.core.orm import Resource

from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm


#: The endpoints whose forms must ask for a name to be typed.
TYPE_TO_CONFIRM = ("config.role_delete", "resources.resource_delete", "resources.pool_delete", "resources.ip_pool_delete", "config.rpa_type_retire", "config.user_delete")

#: Endpoints that stay with the ordinary confirm (reversible or small), pinned so the decision is deliberate.
ORDINARY_CONFIRM = ("projects.member_remove", "resources.tag_delete", "resources.reservation_cancel", "config.variable_delete", "config.user_deactivate")


def _templates() -> Dict[str, str]:
    root = os.path.dirname(os.path.abspath(__file__))
    while not os.path.isdir(os.path.join(root, "source", "site")) and root != os.path.dirname(root):
        root = os.path.dirname(root)
    base = os.path.join(root, "source", "site", "ccai", "pychestrate", "webservice", "webinterface", "blueprints")
    found: Dict[str, str] = {}
    for current, _dirs, files in os.walk(base):
        for name in files:
            if name.endswith(".html"):
                path = os.path.join(current, name)
                with open(path, encoding="utf-8") as handle:
                    found[os.path.relpath(path, base)] = handle.read()
    return found


def _forms(endpoint: str) -> List[str]:
    """Every ``<form>`` block, in every template, that posts to ``endpoint``."""
    blocks: List[str] = []
    for text in _templates().values():
        for match in re.finditer(r"<form\b[^>]*url_for\('" + re.escape(endpoint) + r"'.*?</form>", text, re.S):
            blocks.append(match.group(0))
    return blocks


def test_every_form_that_makes_a_permanent_deletion_asks_for_the_name():
    """
    **Feature: type to confirm on server-rendered pages (XC-15)**
    **Property: every ``<form>`` posting to the role, device, resource pool, IP pool, job-type-retire and user-delete endpoints carries a
    ``data-confirm-type`` that is the entity's name (the form or its button), and there are at least eleven such forms.**
    """
    missing: List[str] = []
    count = 0
    for endpoint in TYPE_TO_CONFIRM:
        for block in _forms(endpoint):
            count += 1
            if re.search(r'data-confirm-type="\{\{\s*[a-z_]+\.(?:name|type_id|username)\s*\}\}"', block) is None:
                missing.append(endpoint)

    testbase.assert_equal((missing, count >= 11), ([], True))
    return


def test_the_reversible_and_small_actions_keep_the_ordinary_confirm():
    """
    **Feature: type to confirm on server-rendered pages (XC-15)**
    **Property: removing a member, deleting a tag, cancelling a reservation, deleting a variable (its history is kept) and deactivating a user
    (reversible) do not ask for a name; each still has its ordinary ``data-confirm``.**
    """
    typed: List[str] = []
    unconfirmed: List[str] = []
    for endpoint in ORDINARY_CONFIRM:
        blocks = _forms(endpoint)
        if len(blocks) == 0:
            unconfirmed.append(endpoint + " (no form found)")
        for block in blocks:
            if "data-confirm-type" in block:
                typed.append(endpoint)
            if "data-confirm" not in block:
                unconfirmed.append(endpoint)

    testbase.assert_equal((typed, unconfirmed), ([], []))
    return


def test_the_real_pages_carry_the_name_to_type():
    """
    **Feature: type to confirm on server-rendered pages (XC-15)**
    **Property: on the Roles page a custom role's Delete button carries its name as ``data-confirm-type``; on the Resources page a device's
    Delete form carries the device's name and its message names it and says it cannot be undone.**
    """
    cookies = adm.admin_cookies()
    role = "typerole-" + uuid.uuid4().hex[:8]
    created = adm.post_form(
        path="/admin/roles/create", cookies=cookies, fields=[("name", role), ("description", "x"), ("permission_keys", "system:runs.read")],
    )
    session = adm.open_db_session()
    try:
        device = "typebench-" + uuid.uuid4().hex[:8]
        session.add(Resource(name=device, resource_type="device", description="d", metadata_json={}, sensitive_fields=[]))
        session.commit()
    finally:
        session.close()

    roles_page = adm.get(path="/admin/roles", cookies=cookies).text
    resources_page = adm.get(path="/resources/list", cookies=cookies, query={"search": device}).text
    role_button = re.search(r'<button[^>]*data-confirm-type="' + re.escape(role) + r'"[^>]*>', roles_page)
    device_form = re.search(r'<form[^>]*data-confirm-type="' + re.escape(device) + r'"[^>]*>', resources_page)

    testbase.assert_equal(
        (
            created.status_code in (302, 303), role_button is not None, device_form is not None,
            device_form is not None and "Delete the resource &quot;{}&quot;".format(device) in device_form.group(0) and "This cannot be undone." in device_form.group(0),
        ),
        (True, True, True, True),
    )
    return
