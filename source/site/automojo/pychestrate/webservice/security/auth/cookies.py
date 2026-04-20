"""
.. module:: security.auth.cookies
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Session-cookie builder with policy defaults.

.. moduleauthor:: Automation Mojo LLC
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass
from typing import Optional


SESSION_COOKIE_NAME = "pychestrate_session"


@dataclass(frozen=True)
class SessionCookieSpec:
    """
        Fully-materialized Set-Cookie payload.

        :param name: Cookie name.
        :param value: Cookie value (opaque session id).
        :param http_only: HttpOnly flag.
        :param secure: Secure flag.
        :param same_site: SameSite value (``Lax`` / ``Strict`` / ``None``).
        :param domain: Cookie Domain attribute; None to omit.
        :param path: Cookie Path attribute.
        :param max_age_seconds: Max-Age in seconds.
    """
    name: str
    value: str
    http_only: bool
    secure: bool
    same_site: str
    domain: Optional[str]
    path: str
    max_age_seconds: int


def build_session_cookie(
        *,
        session_id: str,
        max_age_seconds: int,
        domain: Optional[str],
        same_site: str,
        secure: bool,
        path: str
    ) -> SessionCookieSpec:
    """
        Construct a :class:`SessionCookieSpec` with the caller-supplied
        policy overrides. Every cookie attribute is passed explicitly — per
        AGENTS.md no mutable default is used.

        :param session_id: Opaque session identifier.
        :param max_age_seconds: Cookie lifetime in seconds.
        :param domain: Cookie Domain attribute; None omits the attribute.
        :param same_site: ``Lax`` | ``Strict`` | ``None``.
        :param secure: Whether to set the Secure flag.
        :param path: Cookie Path attribute.

        :returns: The populated cookie spec.
    """
    rtnval = SessionCookieSpec(
        name=SESSION_COOKIE_NAME,
        value=session_id,
        http_only=True,
        secure=secure,
        same_site=same_site,
        domain=domain,
        path=path,
        max_age_seconds=max_age_seconds,
    )
    return rtnval
