"""
.. module:: ccai.testshared.login_form
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Read the CSRF token out of the ``/login`` form so the
               live-server suites can sign in the way a browser does.

.. moduleauthor:: Code Craft AI LLC

The sign-in form is CSRF-gated: ``GET /login`` mints a token into the
anonymous session cookie and echoes it in a hidden ``csrf_token``
field, and ``POST /login`` rejects a submission whose field does not
match the cookie (302 back to ``/login``). An ``httpx.Client`` keeps
the cookie from the GET in its jar; the test only has to copy the
hidden field into the POST body.

Usage::

    from ccai.testshared.login_form import extract_login_csrf_token

    form_response = client.get("/login")
    client.post(
        "/login",
        data={
            "username": login_name,
            "password": password,
            "csrf_token": extract_login_csrf_token(html=form_response.text),
        },
    )
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import re


#: The hidden input the login template renders; matches
#: ``phase10._e2e_harness._LOGIN_CSRF_PATTERN``.
_LOGIN_CSRF_PATTERN = re.compile(
    r'name="csrf_token"\s+value="([^"]*)"'
)


def extract_login_csrf_token(*, html: str) -> str:
    """
        Return the CSRF token echoed in the ``/login`` form.

        :param html: Body of the ``GET /login`` response.

        :returns: The token, or an empty string when the form carries
                  none (the POST is then rejected, as it would be for
                  a browser).
    """
    match = _LOGIN_CSRF_PATTERN.search(html)
    rtnval = match.group(1) if match is not None else ""
    return rtnval


__all__ = [
    "extract_login_csrf_token",
]
