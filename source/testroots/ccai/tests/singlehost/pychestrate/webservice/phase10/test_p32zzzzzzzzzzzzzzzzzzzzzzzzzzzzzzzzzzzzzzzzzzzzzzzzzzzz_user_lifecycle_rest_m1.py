"""
.. module:: test_user_lifecycle_rest_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Deactivate, reactivate and anonymise a user through the REST API (audit ADM-41).

.. moduleauthor:: Code Craft AI LLC

A data-protection request had to be carried out on the Users pages: the anonymise action existed only there. The REST API now has the same three actions
(``specs/1-user-management`` T2.11), calling the same functions as the pages, so the rules cannot differ: deactivate first (that ends access and can be undone),
then anonymise (a deliberate second act that cannot be undone); never your own account; not an account that owns a project.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re
import uuid

from types import SimpleNamespace
from typing import Any, Dict, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.identity.users.models import IdentityUser
from ccai.pychestrate.webservice.identity.users.restapi.v1 import users_routes
from ccai.tests.singlehost.pychestrate.webservice.phase10 import _adm_helpers as adm
from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import ensure_seeded_admin


GOOD_PASSWORD: str = "Correct-Horse-Battery-9"


def _make_user(cookies: Dict[str, str], prefix: str) -> Tuple[str, str]:
    username = "{}-{}".format(prefix, uuid.uuid4().hex[:8])
    adm.post_form(path="/admin/users/create", cookies=cookies, fields={
        "username": username, "email": "{}@example.com".format(username), "password_setup": "password", "password": GOOD_PASSWORD,
        "display_name": "Erase Me", "firstname": "Ada", "lastname": "Lovelace",
    })
    page = adm.get(path="/admin/users", cookies=cookies, query={"search": username}).text
    return re.search(r'href="/admin/users/([0-9a-f-]{36})"[^>]*>\s*' + re.escape(username), page).group(1), username


def _call(handler: Any, user_id: str, actor: str) -> Tuple[int, Dict[str, Any]]:
    session = adm.open_db_session()
    try:
        request = SimpleNamespace(path="/api/v1/identity/users/{}".format(user_id), path_params={"user_id": user_id}, db_session=session, actor_user_id=actor, query_params={})
        response = handler(request)
    finally:
        session.close()
    return response.status_code, json.loads(response.body.decode("utf-8"))


def _row(user_id: str) -> Any:
    session = adm.open_db_session()
    try:
        row = session.query(IdentityUser).filter(IdentityUser.user_id == uuid.UUID(user_id)).first()
        return SimpleNamespace(status=row.status.value, login=row.login_name, anonymised=row.anonymised_at is not None, email=row.primary_email)
    finally:
        session.close()


def test_a_user_is_deactivated_reactivated_and_anonymised_through_the_api():
    """
    **Feature: user lifecycle API (ADM-41)**
    **Property: anonymising an active account is a 409 that says to deactivate first; deactivate answers 200 and ends access, reactivate answers 200 and
    restores it, and after deactivating again anonymise answers 200 and the account's login and email are the values derived from its id; a second anonymise
    and a reactivate of the anonymised account are 409 and change nothing.**
    """
    cookies = adm.admin_cookies()
    actor = ensure_seeded_admin().user_id
    user_id, username = _make_user(cookies, "rest-erase")

    early = _call(users_routes.handle_anonymise_user, user_id, actor)
    off = _call(users_routes.handle_deactivate_user, user_id, actor)
    on = _call(users_routes.handle_reactivate_user, user_id, actor)
    off_again = _call(users_routes.handle_deactivate_user, user_id, actor)
    erased = _call(users_routes.handle_anonymise_user, user_id, actor)
    after = _row(user_id)
    twice = _call(users_routes.handle_anonymise_user, user_id, actor)
    revive = _call(users_routes.handle_reactivate_user, user_id, actor)

    testbase.assert_equal(
        (
            early[0], "Deactivate the account first" in early[1]["detail"], off, on[0], on[1]["status"], off_again[0], erased,
            after.anonymised, after.status, username in after.login or username in after.email, after.login.startswith("anonymised-"),
            twice[0], "already anonymised" in twice[1]["detail"], revive[0], _row(user_id).anonymised,
        ),
        (
            409, True, (200, {"user_id": user_id, "status": "deactivated"}), 200, "active", 200, (200, {"user_id": user_id, "status": "anonymised", "anonymised": True}),
            True, "DEACTIVATED", False, True, 409, True, 409, True,
        ),
    )
    return


def test_the_api_refuses_your_own_account_an_unknown_user_and_a_malformed_id():
    """
    **Feature: user lifecycle API (ADM-41)**
    **Property: deactivating or anonymising your own account is a 409, an unknown user and an id that is not a UUID are 404, and the refused calls change
    nothing.**
    """
    actor = ensure_seeded_admin().user_id
    before = _row(actor)
    own_off = _call(users_routes.handle_deactivate_user, actor, actor)
    own_erase = _call(users_routes.handle_anonymise_user, actor, actor)
    unknown = _call(users_routes.handle_deactivate_user, str(uuid.uuid4()), actor)
    malformed = _call(users_routes.handle_anonymise_user, "not-a-uuid", actor)

    testbase.assert_equal(
        (own_off[0], "your own account" in own_off[1]["detail"], own_erase[0], unknown[0], malformed[0], _row(actor).status == before.status, _row(actor).anonymised),
        (409, True, 409, 404, 404, True, False),
    )
    return
