"""
.. module:: test_p31zzzb_display_name_limit_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A display name has a length limit everywhere it is entered (ADM-41).

.. moduleauthor:: Code Craft AI LLC

A 3,000-character display name broke the users table because nothing bounded
it. The create and edit forms, the REST create call and the setup wizard now
refuse a display name over 100 characters, saying so next to the field, and the
form inputs carry ``maxlength``. The forms and the REST API are driven in
process against the real app; the wizard's rule and the table's wrapping are
checked directly.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import re
import uuid

from typing import Any, Dict, List

from ccai import testbase

from ccai.pychestrate.webservice.identity.users.limits import MAX_DISPLAY_NAME_LENGTH
from ccai.pychestrate.webservice.webinterface.blueprints.setup import routes as setup_routes

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    drive_request,
    ensure_app,
    logged_in_cookies,
)
from ccai.tests.singlehost.pychestrate.webservice.phase10._projects_ui_helpers import post_form


GOOD_PASSWORD: str = "Correct-Horse-Battery-9"


def _setup() -> Dict[str, Any]:
    handle = ensure_app()
    return {"wsgi_app": handle.wsgi_app, "cookies": logged_in_cookies(wsgi_app=handle.wsgi_app)}


def _fields(display_name: str) -> Dict[str, str]:
    unique = uuid.uuid4().hex[:8]
    return {
        "username": "dn-" + unique, "email": "dn-{}@example.com".format(unique), "password_setup": "password",
        "password": GOOD_PASSWORD, "display_name": display_name, "firstname": "", "lastname": "",
    }


def test_the_limit_is_100_and_the_form_says_so_at_the_field():
    """
    **Feature: display name length (ADM-41)**
    **Property: creating a user with a 101-character display name is refused
    (400) with "at most 100 characters" as the display name's own error; a
    100-character name is accepted; the input carries ``maxlength="100"``.**
    """
    setup = _setup()
    too_long = post_form(wsgi_app=setup["wsgi_app"], path="/admin/users/create", cookies=setup["cookies"], fields=_fields("x" * 101))
    accepted = post_form(wsgi_app=setup["wsgi_app"], path="/admin/users/create", cookies=setup["cookies"], fields=_fields("y" * 100))
    form = drive_request(wsgi_app=setup["wsgi_app"], method="GET", path="/admin/users/create", cookies=setup["cookies"]).text

    testbase.assert_equal(
        (
            MAX_DISPLAY_NAME_LENGTH,
            too_long.status_code,
            "at most 100 characters" in too_long.text and 'id="display_name-error"' in too_long.text,
            accepted.status_code in (302, 303),
            'maxlength="100"' in re.search(r'<input[^>]*id="display_name"[^>]*>', form, re.S).group(0),
        ),
        (100, 400, True, True, True),
    )
    return


def test_editing_a_user_to_a_name_over_the_limit_is_refused():
    """
    **Feature: display name length (ADM-41)**
    **Property: the edit form refuses a 101-character display name (400) with
    the same message.**
    """
    setup = _setup()
    fields = _fields("Short Name")
    post_form(wsgi_app=setup["wsgi_app"], path="/admin/users/create", cookies=setup["cookies"], fields=fields)
    page = drive_request(wsgi_app=setup["wsgi_app"], method="GET", path="/admin/users", query_string="search=" + fields["username"], cookies=setup["cookies"]).text
    user_id = re.search(r'href="/admin/users/([0-9a-f-]{36})"', page).group(1)
    edit = post_form(
        wsgi_app=setup["wsgi_app"], path="/admin/users/{}/edit".format(user_id), cookies=setup["cookies"],
        fields={"email": fields["email"], "display_name": "z" * 101, "firstname": "", "lastname": ""},
    )

    testbase.assert_equal((edit.status_code, "at most 100 characters" in edit.text), (400, True))
    return


class _Request:
    """The parts of a request the create handler reads (the in-process app mounts no REST routes)."""

    def __init__(self, display_name: str) -> None:
        self.path = "/api/v1/identity/users"
        self.path_params: Dict[str, Any] = {}
        self.db_session = object()
        self.actor_user_id = "user-42"
        self._body = {"login_name": "alice", "primary_email": "alice@example.com", "display_name": display_name, "timezone": "UTC"}

    def json(self) -> Any:
        return self._body


def test_the_rest_create_call_refuses_a_long_display_name_with_a_problem_document():
    """
    **Feature: display name length (ADM-41)**
    **Property: ``POST /api/v1/identity/users`` with a 101-character display
    name answers 422 whose detail says the limit and never reaches the user
    service; a 100-character one is passed on to it.**
    """
    from ccai.pychestrate.webservice.identity.users.restapi.v1 import users_routes

    reached: List[str] = []

    class _Service:
        @staticmethod
        def create_user(**kwargs: Any) -> Any:
            reached.append(kwargs["display_name"])
            raise RuntimeError("stop after the check")

    original = users_routes.user_service
    users_routes.user_service = _Service
    try:
        refused = users_routes.handle_create_user(_Request("q" * 101))
        reached_before = list(reached)
        try:
            users_routes.handle_create_user(_Request("q" * 100))
        except RuntimeError:
            pass
    finally:
        users_routes.user_service = original

    body = json.loads(refused.body.decode("utf-8"))
    testbase.assert_equal(
        (refused.status_code, "at most 100 characters" in body["detail"], reached_before, [len(name) for name in reached]),
        (422, True, [], [100]),
    )
    return


def test_the_setup_wizard_refuses_a_long_display_name_too():
    """
    **Feature: display name length (ADM-41)**
    **Property: the first-administrator form's validation reports a
    101-character display name under its own field.**
    """
    errors = setup_routes._collect_admin_field_errors(
        login_name="first-admin", email="a@example.com", password=GOOD_PASSWORD, password_confirm=GOOD_PASSWORD, display_name="w" * 101,
    )

    testbase.assert_equal(("at most 100 characters" in errors.get("display_name", ""), list(errors.keys())), (True, ["display_name"]))
    return
