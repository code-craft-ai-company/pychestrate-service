"""
.. module:: webinterface.foundation.csrf
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: CSRF token primitives for the consumer web UI.

.. moduleauthor:: Code Craft AI LLC

The consumer web UI stores a CSRF token in the cookie-backed
UI session at login time and validates form-submitted tokens
against it on every POST. This module owns the primitives:

* :func:`generate_csrf_token` -- produce 32 bytes of urlsafe
  base64 random material; intended to be stored in the UI
  session dict under the documented key.

* :func:`extract_token_from_form` -- pull the ``csrf_token``
  field from a parsed form-data dict.

* :func:`is_token_valid` -- constant-time compare a submitted
  token against the expected token from the session.

* :func:`get_or_create_token_in_session` -- convenience for
  handlers that read the session, mint a token if absent, and
  return it for template rendering. Tracks whether the session
  needs to be re-written so the handler can decide whether to
  refresh the cookie on response.

Validation contract
-------------------

CSRF validation is deliberately scoped narrowly: this module
performs constant-time string compare. The wider checks --
"only POST requires CSRF", "GET is exempt", "AJAX may pass token
in header X-CSRF-Token" -- are policy decisions left to the
handler-level CSRF guard in :mod:`auth_guard`.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import hmac
import secrets

from typing import Any, Dict, Optional, Tuple


SESSION_KEY: str = "csrf_token"
FORM_FIELD_NAME: str = "csrf_token"
TOKEN_BYTE_LENGTH: int = 32


def generate_csrf_token() -> str:
    """
        Produce a fresh CSRF token.

        :returns: URL-safe base64 string of
                  :data:`TOKEN_BYTE_LENGTH` random bytes.
    """
    rtnval = secrets.token_urlsafe(TOKEN_BYTE_LENGTH)
    return rtnval


def extract_token_from_form(*, form: Dict[str, Any]) -> Optional[str]:
    """
        Pull the CSRF token out of a parsed form payload.
        Returns ``None`` when the field is missing or non-string.

        :param form: Dict of form-encoded request fields.

        :returns: Token string or ``None``.
    """
    if form is None:
        return None
    raw = form.get(FORM_FIELD_NAME, None)
    if raw is None:
        return None
    if not isinstance(raw, str):
        return None
    if len(raw) == 0:
        return None
    rtnval = raw
    return rtnval


def is_token_valid(
        *,
        submitted: Optional[str],
        expected: Optional[str]
    ) -> bool:
    """
        Constant-time compare a submitted token against the
        session's expected token.

        :param submitted: Token from the form / header.
        :param expected: Token previously stored in the session.

        :returns: True iff both are non-empty and match.
    """
    if submitted is None or expected is None:
        return False
    if len(submitted) == 0 or len(expected) == 0:
        return False
    rtnval = hmac.compare_digest(submitted, expected)
    return rtnval


def get_or_create_token_in_session(
        *, session: Dict[str, Any]
    ) -> Tuple[str, bool]:
    """
        Read the CSRF token from the session dict, minting a fresh
        one when absent. Returns the token plus a flag indicating
        whether the session was mutated (the handler then knows to
        re-write the session cookie on the response).

        :param session: Session dict (e.g. from
                        :func:`cookie_session.read_session_from_request`).

        :returns: ``(token, session_mutated)``.
    """
    existing = session.get(SESSION_KEY, None)
    if isinstance(existing, str) and len(existing) > 0:
        rtnval = (existing, False)
        return rtnval

    token = generate_csrf_token()
    session[SESSION_KEY] = token
    rtnval = (token, True)
    return rtnval


def store_token_in_session(
        *, session: Dict[str, Any], token: str
    ) -> None:
    """
        Set the CSRF token on the session dict. Used at login
        time when the auth flow wants to rotate the token (best
        practice on privilege change).

        :param session: Session dict.
        :param token: Token to store.

        :returns: None.
    """
    session[SESSION_KEY] = token
    return


def rotate_csrf_token(*, session: Dict[str, Any]) -> str:
    """
        Mint a new CSRF token and overwrite whatever was in the
        session. Returns the new token. Use after privilege
        change (login, logout, role escalation) so the new
        session can't reuse the pre-change token.

        :param session: Session dict.

        :returns: The new token.
    """
    token = generate_csrf_token()
    session[SESSION_KEY] = token
    rtnval = token
    return rtnval


__all__ = [
    "SESSION_KEY",
    "FORM_FIELD_NAME",
    "TOKEN_BYTE_LENGTH",
    "generate_csrf_token",
    "extract_token_from_form",
    "is_token_valid",
    "get_or_create_token_in_session",
    "store_token_in_session",
    "rotate_csrf_token",
]
