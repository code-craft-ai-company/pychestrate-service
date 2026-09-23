"""
.. module:: test_p40l_shell_display_name_m1
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Tests that the shell header names the user by display name.

.. moduleauthor:: Code Craft AI LLC

Audit finding XC-09: the header showed the login name ("admin") while
project pages showed the display name ("Ada Admin"). The shell document
now looks the signed-in user's display name up in the identity store and
passes both names to the header's account menu.

**Feature: site shell (XC-09 account menu)**
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import uuid

from typing import Any, Optional, Tuple

from ccai import testbase

from ccai.pychestrate.webservice.identity.users.models import IdentityUser
from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.webinterface.site_shell import shell_document

from ccai.tests.singlehost.pychestrate.webservice.phase1.fixtures import (
    build_in_memory_session,
    session_for,
)


def _with_user(display_name: str) -> Tuple[Any, str]:
    """
        An in-memory identity store holding one user, published as the
        service's session factory; returns the previous factory and the
        user's id.
    """
    engine, session = build_in_memory_session()
    user_id = str(uuid.uuid4())
    session.add(IdentityUser(
        user_id=user_id, login_name="admin", primary_email="admin@example.com", display_name=display_name,
    ))
    session.commit()
    previous = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = lambda: session_for(engine=engine)
    rtnval = (previous, user_id)
    return rtnval


def _lookup(display_name: str, user_id: Optional[str] = None) -> Optional[str]:
    previous, stored_id = _with_user(display_name)
    try:
        rtnval = shell_document._lookup_display_name(user_id=user_id if user_id is not None else stored_id)
    finally:
        SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY = previous
    return rtnval


def test_the_header_uses_the_users_display_name():
    """
    **Feature: site shell (XC-09 account menu)**
    **Property: the signed-in user's display name is read from the
    identity store.**
    """
    testbase.assert_equal(_lookup("Ada Admin"), "Ada Admin")
    return


def test_an_empty_display_name_falls_back_to_the_login_name():
    """
    **Feature: site shell (XC-09 account menu)**
    **Property: a user without a display name yields no display name, so
    the header shows the login name instead.**
    """
    testbase.assert_equal(_lookup("   "), None)
    return


def test_an_unknown_user_yields_no_display_name():
    """
    **Feature: site shell (XC-09 account menu)**
    **Property: a session user id that is not in the identity store (or
    is not a UUID) yields no display name rather than an error.**
    """
    testbase.assert_equal(
        (_lookup("Ada Admin", user_id=str(uuid.uuid4())), _lookup("Ada Admin", user_id="not-a-uuid")),
        (None, None),
    )
    return
