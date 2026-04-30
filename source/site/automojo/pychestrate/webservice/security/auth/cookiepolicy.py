"""
.. module:: security.auth.cookiepolicy
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Configurable Set-Cookie policy for session cookies.

.. moduleauthor:: Automation Mojo LLC

The login endpoint builds a session cookie using
:func:`automojo.pychestrate.webservice.security.auth.cookies.build_session_cookie`,
which takes every cookie attribute as an explicit argument. This
module sources those attributes from the environment so operators
can tune cookie behavior between dev and production deployments
without code changes.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import os

from dataclasses import dataclass
from typing import Optional


COOKIE_SECURE_ENV_VAR = "PYCHESTRATE_COOKIE_SECURE"
COOKIE_SAMESITE_ENV_VAR = "PYCHESTRATE_COOKIE_SAMESITE"
COOKIE_DOMAIN_ENV_VAR = "PYCHESTRATE_COOKIE_DOMAIN"
COOKIE_PATH_ENV_VAR = "PYCHESTRATE_COOKIE_PATH"
COOKIE_MAX_AGE_ENV_VAR = "PYCHESTRATE_COOKIE_MAX_AGE_SECONDS"

DEFAULT_SECURE = True
DEFAULT_SAMESITE = "Lax"
DEFAULT_DOMAIN: Optional[str] = None
DEFAULT_PATH = "/"
DEFAULT_MAX_AGE_SECONDS = 8 * 60 * 60


def _read_bool(*, name: str, default: bool) -> bool:
    """
        Coerce an environment variable to bool.
    """
    raw = os.environ.get(name, None)
    if raw is None:
        return default
    if str(raw).strip().lower() in ("1", "true", "yes", "on"):
        return True
    if str(raw).strip().lower() in ("0", "false", "no", "off"):
        return False
    return default


def _read_int(*, name: str, default: int) -> int:
    """
        Coerce an environment variable to int, with a default fallback.
    """
    raw = os.environ.get(name, None)
    if raw is None:
        return default
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        return default
    return rtnval


def _read_str(*, name: str, default: Optional[str]) -> Optional[str]:
    """
        Read a string environment variable, treating empty as unset.
    """
    raw = os.environ.get(name, None)
    if raw is None:
        return default
    if len(raw.strip()) == 0:
        return default
    rtnval = raw
    return rtnval


@dataclass(frozen=True)
class CookiePolicy:
    """
        Frozen view of the cookie policy fed to
        :func:`build_session_cookie`. Built once per request via
        :func:`load_cookie_policy_from_env` so repeated env reads
        don't surprise the handler.

        :param secure: Whether the ``Secure`` flag is emitted.
        :param same_site: ``Lax`` / ``Strict`` / ``None``.
        :param domain: ``Domain`` attribute, or ``None`` to omit.
        :param path: ``Path`` attribute.
        :param max_age_seconds: ``Max-Age`` value.
    """
    secure: bool
    same_site: str
    domain: Optional[str]
    path: str
    max_age_seconds: int


def load_cookie_policy_from_env() -> CookiePolicy:
    """
        Build a :class:`CookiePolicy` from the
        ``PYCHESTRATE_COOKIE_*`` environment variables, falling back
        to the production-friendly defaults documented in
        ``usersguide/configuration.md``.

        :returns: A populated :class:`CookiePolicy`.
    """
    secure = _read_bool(name=COOKIE_SECURE_ENV_VAR, default=DEFAULT_SECURE)
    same_site = _read_str(
        name=COOKIE_SAMESITE_ENV_VAR, default=DEFAULT_SAMESITE,
    )
    if same_site is None:
        same_site = DEFAULT_SAMESITE
    domain = _read_str(name=COOKIE_DOMAIN_ENV_VAR, default=DEFAULT_DOMAIN)
    path = _read_str(name=COOKIE_PATH_ENV_VAR, default=DEFAULT_PATH)
    if path is None:
        path = DEFAULT_PATH
    max_age_seconds = _read_int(
        name=COOKIE_MAX_AGE_ENV_VAR, default=DEFAULT_MAX_AGE_SECONDS,
    )
    rtnval = CookiePolicy(
        secure=secure,
        same_site=same_site,
        domain=domain,
        path=path,
        max_age_seconds=max_age_seconds,
    )
    return rtnval


def render_set_cookie_header(*, spec) -> str:
    """
        Render a :class:`SessionCookieSpec` as a ``Set-Cookie`` header
        value. Kept here (rather than alongside ``SessionCookieSpec``
        itself) so callers can swap renderers without touching the
        canonical spec definition.

        :param spec: A :class:`SessionCookieSpec`.

        :returns: The header value, e.g.
                  ``pychestrate_session=<id>; HttpOnly; Secure;
                  SameSite=Lax; Path=/; Max-Age=28800``.
    """
    parts = []
    parts.append("{0}={1}".format(spec.name, spec.value))
    if spec.http_only is True:
        parts.append("HttpOnly")
    if spec.secure is True:
        parts.append("Secure")
    if spec.same_site is not None:
        if len(spec.same_site) > 0:
            parts.append("SameSite={0}".format(spec.same_site))
    if spec.domain is not None:
        if len(spec.domain) > 0:
            parts.append("Domain={0}".format(spec.domain))
    if spec.path is not None:
        if len(spec.path) > 0:
            parts.append("Path={0}".format(spec.path))
    if spec.max_age_seconds is not None:
        if spec.max_age_seconds > 0:
            parts.append("Max-Age={0}".format(int(spec.max_age_seconds)))
    rtnval = "; ".join(parts)
    return rtnval
