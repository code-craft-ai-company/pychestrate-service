"""
.. module:: test_p31zzzq_user_picker_list_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: A picker can list users without typing an id (ADM-29, PRJ-16).

.. moduleauthor:: Code Craft AI LLC

A page that needs a user (a secret's owner, a member to add) could only ask for
the id typed in, because the REST API could create and read one user but not list
them. ``GET /api/v1/identity/users`` lists a page of users by login name, narrowed
by a literal substring of the login or display name, and returns only what a picker
needs (not the email address). The handler runs against a real in-memory database.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import uuid

from typing import Any, Dict, Optional

from ccai import testbase

from ccai.pychestrate.webservice.identity.users.models import IdentityUser
from ccai.pychestrate.webservice.identity.users.restapi.v1 import users_routes

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import build_in_memory_session


class _Query:
    def __init__(self, values: Dict[str, str]) -> None:
        self._values = values

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._values.get(key, default)


class _Request:
    def __init__(self, session: Any, query: Optional[Dict[str, str]] = None) -> None:
        self.path = "/api/v1/identity/users"
        self.path_params: Dict[str, Any] = {}
        self.query_params = _Query(query or {})
        self.db_session = session


def _add(session: Any, login: str, display: str) -> None:
    session.add(IdentityUser(user_id=uuid.uuid4(), login_name=login, primary_email=login + "@example.test", display_name=display))


def _users() -> Any:
    _engine, session = build_in_memory_session()
    for login, display in (("ada", "Ada Lovelace"), ("grace", "Grace Hopper"), ("ops_lead", "Olive Ops"), ("100%pure", "Percent Person"), ("zed", "Ada Zed")):
        _add(session, login, display)
    session.commit()
    return session


def _call(session: Any, **query: str) -> Any:
    response = users_routes.handle_list_users(_Request(session, query))
    return response.status_code, json.loads(response.body.decode("utf-8"))


def test_users_are_listed_by_login_name_with_only_what_a_picker_needs():
    """
    **Feature: user picker list (ADM-29)**
    **Property: the list is ordered by login name, each item has exactly the id,
    login name, display name and status (no email address), and the meta carries
    the page, page size and total.**
    """
    status, body = _call(_users())

    testbase.assert_equal(
        (status, [item["login_name"] for item in body["items"]], sorted(body["items"][0].keys()), body["meta"], "example.test" in json.dumps(body)),
        (200, ["100%pure", "ada", "grace", "ops_lead", "zed"], ["display_name", "login_name", "status", "user_id"], {"page": 1, "per_page": 50, "total": 5}, False),
    )
    return


def test_q_matches_a_substring_of_the_login_or_display_name_literally():
    """
    **Feature: user picker list (ADM-29)**
    **Property: ``q`` narrows to users whose login or display name contains it (any
    case); ``%`` and ``_`` are literal, not wildcards; nothing matching gives an
    empty page with total 0.**
    """
    session = _users()
    by_login = _call(session, q="OPS")[1]
    by_display = _call(session, q="ada")[1]
    percent = _call(session, q="%")[1]
    underscore = _call(session, q="_")[1]
    none = _call(session, q="nobody-like-this")[1]

    testbase.assert_equal(
        (
            [item["login_name"] for item in by_login["items"]], [item["login_name"] for item in by_display["items"]], by_display["meta"]["total"],
            [item["login_name"] for item in percent["items"]], [item["login_name"] for item in underscore["items"]], none["items"], none["meta"]["total"],
        ),
        (["ops_lead"], ["ada", "zed"], 2, ["100%pure"], ["ops_lead"], [], 0),
    )
    return


def test_paging_slices_the_ordered_list_and_bad_parameters_are_refused():
    """
    **Feature: user picker list (ADM-29)**
    **Property: ``per_page`` and ``page`` slice the ordered list while the total stays
    the number matching; a non-numeric, zero or over-limit value answers 400.**
    """
    session = _users()
    second = _call(session, per_page="2", page="2")[1]
    refused = [_call(session, per_page="abc")[0], _call(session, per_page="0")[0], _call(session, per_page=str(users_routes.MAX_USERS_PAGE_SIZE + 1))[0], _call(session, page="x")[0]]

    testbase.assert_equal(
        ([item["login_name"] for item in second["items"]], second["meta"], refused),
        (["grace", "ops_lead"], {"page": 2, "per_page": 2, "total": 5}, [400, 400, 400, 400]),
    )
    return
