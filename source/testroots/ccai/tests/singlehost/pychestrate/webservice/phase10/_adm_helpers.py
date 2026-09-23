"""
.. module:: tests.singlehost.pychestrate.webservice.phase10._adm_helpers
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Small request helpers for the admin & identity
               regression tests, layered on the phase-10 e2e harness.

.. moduleauthor:: Code Craft AI LLC

The admin & identity tests drive the real app through
:mod:`._e2e_harness`. These helpers cover the three things nearly every
one of them does: sign in, send a CSRF-bearing form POST, and open a
database session on the shared in-memory store.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import urllib.parse
import uuid

from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS

from ccai.tests.singlehost.pychestrate.webservice.phase10._e2e_harness import (
    WsgiResponse,
    drive_request,
    ensure_app,
    extract_csrf_token_from_cookies,
    logged_in_cookies,
)


FormFields = Union[Dict[str, Any], Sequence[Tuple[str, Any]]]


def app() -> Any:
    """
        The shared WSGI app under test.

        :returns: The WSGI callable.
    """
    handle = ensure_app()
    rtnval = handle.wsgi_app
    return rtnval


def admin_cookies() -> Dict[str, str]:
    """
        Sign in as the seeded system administrator.

        :returns: The cookie jar of the signed-in session.
    """
    rtnval = logged_in_cookies(wsgi_app=app())
    return rtnval


def unique_name(*, prefix: str) -> str:
    """
        A login / object name no other test in the shared database
        uses.

        :param prefix: Readable prefix.

        :returns: ``<prefix>-<8 hex chars>``.
    """
    rtnval = "{}-{}".format(prefix, uuid.uuid4().hex[:8])
    return rtnval


def get(
        *,
        path: str,
        cookies: Optional[Dict[str, str]] = None,
        query: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None
    ) -> WsgiResponse:
    """
        Send a GET.

        :param path: Request path.
        :param cookies: Cookie jar (optional).
        :param query: Query parameters (optional).
        :param headers: Extra request headers (optional).

        :returns: The captured response.
    """
    query_string = ""
    if query is not None:
        query_string = urllib.parse.urlencode(query)
    rtnval = drive_request(
        wsgi_app=app(),
        method="GET",
        path=path,
        query_string=query_string,
        cookies=cookies,
        headers=headers,
    )
    return rtnval


def post_form(
        *,
        path: str,
        fields: FormFields,
        cookies: Dict[str, str],
        query: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
        include_csrf: bool = True
    ) -> WsgiResponse:
    """
        Send a form POST carrying the session's CSRF token (the way
        the rendered forms do).

        :param path: Request path.
        :param fields: Form fields as a dict or a sequence of pairs
                       (pairs allow repeated keys).
        :param cookies: Cookie jar of the signed-in session.
        :param query: Query parameters (optional).
        :param headers: Extra request headers (optional).
        :param include_csrf: Add the session's CSRF token.

        :returns: The captured response.
    """
    pairs: List[Tuple[str, str]] = []
    if isinstance(fields, dict) is True:
        for key, value in fields.items():
            pairs.append((key, str(value)))
    else:
        for key, value in fields:
            pairs.append((key, str(value)))
    if include_csrf is True:
        token = extract_csrf_token_from_cookies(cookies=cookies)
        pairs.append(("csrf_token", token if token is not None else ""))
    body = urllib.parse.urlencode(pairs).encode("utf-8")

    request_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if headers is not None:
        request_headers.update(headers)

    query_string = ""
    if query is not None:
        query_string = urllib.parse.urlencode(query)

    rtnval = drive_request(
        wsgi_app=app(),
        method="POST",
        path=path,
        query_string=query_string,
        body=body,
        cookies=cookies,
        headers=request_headers,
    )
    return rtnval


def merge_cookies(
        *, cookies: Dict[str, str], response: WsgiResponse
    ) -> Dict[str, str]:
    """
        Apply a response's ``Set-Cookie`` headers to a cookie jar, the
        way a browser would.

        :param cookies: The current jar.
        :param response: The response carrying new cookies.

        :returns: The updated jar (a new dict).
    """
    rtnval = dict(cookies)
    rtnval.update(response.collect_set_cookies())
    return rtnval


def open_db_session() -> Any:
    """
        Open a session on the shared in-memory database. The caller
        closes it.

        :returns: A SQLAlchemy session.
    """
    ensure_app()
    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    rtnval = factory()
    return rtnval
