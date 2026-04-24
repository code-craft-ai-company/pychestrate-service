"""
.. module:: webservice.middleware
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Phase-1 request-scoped session and actor-resolution middleware.

.. moduleauthor:: Automation Mojo LLC

This module wires two Flask request hooks that every Phase-1 REST
controller relies on:

1. A ``before_request`` hook that opens a SQLAlchemy session from
   :attr:`SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY` and attaches it
   to :data:`flask.g` as ``db_session``, scoped to the Phase-1 URL
   prefixes declared in :data:`PHASE1_URL_PREFIXES`.
2. The same hook resolves the session cookie via
   :func:`session_service.resolve_session`; on success, it stores an
   :class:`AuthPrincipal` as ``g.auth_principal`` and copies the
   ``user_id`` to ``g.actor_user_id`` so controllers and service calls
   have ready access for audit attribution.
3. A ``teardown_request`` hook commits a clean exit, rolls back on
   exception, and always closes the session.

The middleware is **installed** via :func:`install_phase1_middleware`.
The caller passes in the Flask app instance that hosts the v1 REST
namespaces. Installation is idempotent.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2025, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Optional, Tuple

from flask import Flask, Request, g, request
from sqlalchemy.orm import Session as DbSession

from automojo.errors.exceptions import ConfigurationError

from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from automojo.pychestrate.webservice.security.auth.cookies import SESSION_COOKIE_NAME
from automojo.pychestrate.webservice.security.auth.exceptions import (
    SessionExpiredError,
    SessionNotFoundError,
)
from automojo.pychestrate.webservice.security.auth.session_service import (
    AuthPrincipal,
    resolve_session,
)


logger = logging.getLogger(__name__)


PHASE1_URL_PREFIXES: Tuple[str, ...] = (
    "/1/identity/",
    "/1/auth/",
    "/1/rbac/",
    "/1/secrets",
    "/1/audit",
    "/1/flags",
    "/1/clients",
    "/1/enrollment-tokens",
    "/1/projects",
)


_INSTALLED_ATTR = "_pychestrate_phase1_middleware_installed"


def install_phase1_middleware(*, app: Flask) -> None:
    """
        Install Phase-1 request hooks on the given Flask application.

        :param app: The Flask application hosting the v1 REST namespaces.

        :returns: None.
    """
    if getattr(app, _INSTALLED_ATTR, False) is True:
        return

    app.before_request(_phase1_before_request)
    app.teardown_request(_phase1_teardown_request)
    setattr(app, _INSTALLED_ATTR, True)

    return


def _request_is_phase1_scoped(*, flask_request: Request) -> bool:
    """
        Return True when the inbound request path targets one of the
        Phase-1 URL prefixes.

        :param flask_request: The current Flask request object.

        :returns: Whether the middleware should attach a session.
    """
    path = flask_request.path if flask_request.path is not None else ""
    for prefix in PHASE1_URL_PREFIXES:
        if path.startswith(prefix) is True:
            return True
    return False


def _open_session() -> DbSession:
    """
        Open a new SQLAlchemy session using the shared factory.

        :returns: A fresh :class:`DbSession`.
        :raises: ConfigurationError when the factory has not been initialized.
    """
    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    if factory is None:
        raise ConfigurationError(
            "SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY has not been initialized; "
            "call the Phase-1 bootstrap before serving requests."
        )
    rtnval = factory()
    return rtnval


def _resolve_actor_from_cookie(*, db_session: DbSession) -> Optional[AuthPrincipal]:
    """
        Read the Phase-1 session cookie from the current request and resolve
        it through :func:`session_service.resolve_session`. Returns None on
        any failure — unauthenticated requests are legal on public routes.

        :param db_session: Active SQLAlchemy session.

        :returns: The :class:`AuthPrincipal` on success, otherwise None.
    """
    cookie_value = request.cookies.get(SESSION_COOKIE_NAME, None)
    if cookie_value is None or len(cookie_value) == 0:
        return None

    try:
        principal = resolve_session(
            db_session=db_session,
            session_id=cookie_value,
            now=datetime.now(timezone.utc),
        )
    except SessionExpiredError:
        logger.info(
            "phase1.session_resolve.expired cookie_prefix=%s", cookie_value[:8]
        )
        return None
    except SessionNotFoundError:
        logger.info(
            "phase1.session_resolve.not_found cookie_prefix=%s", cookie_value[:8]
        )
        return None

    return principal


def _phase1_before_request() -> None:
    """
        Per-request hook: open a session and resolve the actor when the
        inbound path is Phase-1 scoped. Sets ``g.db_session`` always,
        and ``g.auth_principal`` / ``g.actor_user_id`` on cookie match.

        :returns: None.
    """
    if _request_is_phase1_scoped(flask_request=request) is False:
        return

    db_session = _open_session()
    g.db_session = db_session

    principal = _resolve_actor_from_cookie(db_session=db_session)
    if principal is not None:
        g.auth_principal = principal
        g.actor_user_id = principal.user_id
    else:
        g.auth_principal = None
        g.actor_user_id = None

    return


def _phase1_teardown_request(exception_or_none) -> None:
    """
        Per-request teardown: roll back on exception and always close the
        session. Phase-1 service functions manage their own ``commit()``
        so success is already persisted by the time teardown runs — the
        teardown hook must NOT double-commit, otherwise events buffered
        by the outbox after the service commit would publish on cleanup.

        :param exception_or_none: The exception raised during the request,
                                  or None on success.

        :returns: None.
    """
    db_session: Optional[DbSession] = getattr(g, "db_session", None)
    if db_session is None:
        return

    try:
        if exception_or_none is not None:
            db_session.rollback()
    except Exception as xcpt:  # noqa: BLE001 — teardown must not raise
        logger.exception(
            "phase1.teardown.rollback_failed error=%s", xcpt
        )
    finally:
        try:
            db_session.close()
        except Exception as xcpt:  # noqa: BLE001
            logger.exception(
                "phase1.teardown.session_close_failed error=%s", xcpt
            )
        g.db_session = None
        g.auth_principal = None
        g.actor_user_id = None

    return
