"""
.. module:: webinterface.foundation.cookie_session
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: HMAC-signed cookie-backed session for the
               consumer web UI.

.. moduleauthor:: Automation Mojo LLC

The consumer web UI uses an HMAC-signed cookie to carry the
user_id, session token, CSRF token, and one-time flash messages
between requests. This module owns that cookie format for the
webworks routes:

* :func:`sign_session_payload` -- serialize a dict to a
  base64url-encoded ``payload.signature`` cookie value, signed
  with HMAC-SHA256 using the operator-supplied secret.

* :func:`verify_session_payload` -- read a cookie value, verify
  the signature, and return the decoded dict; returns
  ``None`` on tamper / missing signature / invalid base64 /
  malformed shape.

The cookie is **signed but not encrypted**. CSRF tokens, flash
messages, and the resolved user_id all sit safely in the clear
because the threat model is "no tampering" not "no readable
contents". Anything sensitive (passwords, raw secrets) does NOT
go in the session cookie.

Cookie hygiene
--------------

The session cookie is intended to be set with ``Secure``,
``HttpOnly``, ``SameSite=Lax`` flags by the registering
middleware -- this module produces the cookie *value* and lets
the caller decide attributes per response.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import base64
import hashlib
import hmac
import json

from typing import Any, Dict, Optional


COOKIE_NAME: str = "pychestrate_ui_session"

_SIGNATURE_SEPARATOR: str = "."


def sign_session_payload(
        *,
        payload: Dict[str, Any],
        secret: bytes
    ) -> str:
    """
        Serialize a dict to a signed cookie value.

        The wire format is ``<b64-payload>.<b64-signature>`` where
        the signature is HMAC-SHA256 over the b64-encoded payload.
        Encoding before signing means the verifier doesn't need
        to re-canonicalize the dict to check the signature.

        :param payload: JSON-serializable dict.
        :param secret: HMAC secret bytes (>=16 bytes recommended).

        :returns: Cookie value string.
        :raises: ValueError on empty / too-short secret.
    """
    if secret is None or len(secret) < 16:
        raise ValueError(
            "sign_session_payload requires secret >= 16 bytes"
        )

    payload_json = json.dumps(
        payload, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    payload_b64 = base64.urlsafe_b64encode(payload_json).decode("ascii")

    signature = hmac.new(
        secret, payload_b64.encode("ascii"), hashlib.sha256
    ).digest()
    signature_b64 = base64.urlsafe_b64encode(signature).decode("ascii")

    rtnval = payload_b64 + _SIGNATURE_SEPARATOR + signature_b64
    return rtnval


def verify_session_payload(
        *,
        cookie_value: Optional[str],
        secret: bytes
    ) -> Optional[Dict[str, Any]]:
    """
        Verify a cookie value's signature and return the decoded
        payload dict. Returns ``None`` on any failure -- callers
        treat that as "no session" (anonymous request).

        :param cookie_value: The raw cookie value from
                             ``request.cookies.get(COOKIE_NAME)``.
                             ``None`` returns ``None``.
        :param secret: HMAC secret bytes.

        :returns: Decoded dict on valid signature, ``None`` otherwise.
        :raises: ValueError on empty / too-short secret. Verification
                 failures (tamper, bad b64, bad shape) return ``None``
                 rather than raising so handlers stay simple.
    """
    if secret is None or len(secret) < 16:
        raise ValueError(
            "verify_session_payload requires secret >= 16 bytes"
        )

    if cookie_value is None or len(cookie_value) == 0:
        return None

    if _SIGNATURE_SEPARATOR not in cookie_value:
        return None

    payload_b64, signature_b64 = cookie_value.rsplit(
        _SIGNATURE_SEPARATOR, 1
    )
    if len(payload_b64) == 0 or len(signature_b64) == 0:
        return None

    expected_signature = hmac.new(
        secret, payload_b64.encode("ascii"), hashlib.sha256
    ).digest()

    try:
        actual_signature = base64.urlsafe_b64decode(
            signature_b64.encode("ascii")
        )
    except (ValueError, TypeError):
        return None

    if not hmac.compare_digest(expected_signature, actual_signature):
        return None

    try:
        payload_json = base64.urlsafe_b64decode(
            payload_b64.encode("ascii")
        )
    except (ValueError, TypeError):
        return None

    try:
        payload = json.loads(payload_json.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None

    if not isinstance(payload, dict):
        return None

    rtnval = payload
    return rtnval


def read_session_from_request(
        *,
        request: Any,
        secret: bytes,
        cookie_name: str = COOKIE_NAME
    ) -> Dict[str, Any]:
    """
        Extract and verify the UI session cookie from a webworks
        request. Returns an empty dict for missing / tampered /
        malformed cookies so handlers can write
        ``session = read_session_from_request(...)`` and treat the
        result as a regular dict.

        :param request: Webworks Request.
        :param secret: HMAC secret bytes.
        :param cookie_name: Cookie name (defaults to
                            :data:`COOKIE_NAME`).

        :returns: Dict (empty on no / invalid session).
    """
    raw = request.cookies.get(cookie_name, None)
    decoded = verify_session_payload(cookie_value=raw, secret=secret)
    if decoded is None:
        return {}
    rtnval = decoded
    return rtnval


def write_session_to_response(
        *,
        response: Any,
        payload: Dict[str, Any],
        secret: bytes,
        cookie_name: str = COOKIE_NAME,
        max_age_seconds: Optional[int] = None,
        secure: bool = True,
        http_only: bool = True,
        same_site: str = "Lax",
        path: str = "/"
    ) -> None:
    """
        Sign and attach the session cookie to a webworks response.
        Defaults to ``Secure`` + ``HttpOnly`` + ``SameSite=Lax``
        per OWASP guidance.

        :param response: Webworks Response.
        :param payload: Dict to sign + store.
        :param secret: HMAC secret bytes.
        :param cookie_name: Cookie name.
        :param max_age_seconds: Cookie ``Max-Age`` (None = session
                                cookie that dies with the browser).
        :param secure: Set the ``Secure`` flag.
        :param http_only: Set the ``HttpOnly`` flag.
        :param same_site: ``Strict`` | ``Lax`` | ``None``.
        :param path: Cookie scope path.

        :returns: None.
    """
    cookie_value = sign_session_payload(payload=payload, secret=secret)
    response.set_cookie(
        name=cookie_name,
        value=cookie_value,
        max_age=max_age_seconds,
        path=path,
        secure=secure,
        httponly=http_only,
        samesite=same_site,
    )
    return


def clear_session_cookie_on_response(
        *,
        response: Any,
        cookie_name: str = COOKIE_NAME,
        path: str = "/"
    ) -> None:
    """
        Delete the UI session cookie on a webworks response.
        Used by logout flows.

        :param response: Webworks Response.
        :param cookie_name: Cookie name.
        :param path: Cookie scope path (must match the path the
                     cookie was set with for the delete to take).

        :returns: None.
    """
    response.delete_cookie(name=cookie_name, path=path)
    return


__all__ = [
    "COOKIE_NAME",
    "sign_session_payload",
    "verify_session_payload",
    "read_session_from_request",
    "write_session_to_response",
    "clear_session_cookie_on_response",
]
