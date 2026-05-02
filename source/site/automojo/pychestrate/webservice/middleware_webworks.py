"""
.. module:: webservice.middleware_webworks
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-side per-request session and actor-resolution
               middleware.

.. moduleauthor:: Automation Mojo LLC

The flask Phase-1 middleware at :mod:`webservice.middleware`
attaches a SQLAlchemy session and an :class:`AuthPrincipal` to
``flask.g`` via two hooks (``before_request`` for setup,
``teardown_request`` for cleanup). The production webservice now
runs on ``automojo.webworks``; this module is the equivalent for
the webworks pipeline.

WebWorks middleware is a single callable shaped as
``(request, call_next) -> response`` — no separate before/after
hooks. The pre-handler work and the cleanup are combined into one
``__call__`` that wraps ``call_next(request)`` in try / except /
finally. There is no ``flask.g`` analog; webworks routes read the
session and actor off the :class:`Request` object as attributes.
The handlers in :mod:`identity.flags.restapi.v1.flags_routes`
already follow that convention via
:func:`flags_routes._resolve_db_session` /
:func:`flags_routes._resolve_actor_user_id` (which read
``getattr(request, "db_session", None)`` and the actor id),
so installing this middleware turns those handlers' 503-fallback
behavior into a fully populated request-scoped session.

Behavior
--------

For every request whose path starts with one of ``path_prefixes``:

* Open a SQLAlchemy session via the injected ``open_session``
  callable. Attach as ``request.db_session``.
* Read the session cookie named ``cookie_name`` from
  ``request.cookies``. If present and non-empty, call
  ``resolve_actor(db_session, session_id, now)``; on success,
  attach the principal as ``request.auth_principal`` and the
  user_id as ``request.actor_user_id``. On
  :class:`SessionExpiredError` / :class:`SessionNotFoundError`,
  treat the request as unauthenticated (``actor_user_id=None``).
* Invoke ``call_next(request)``.
* If ``call_next`` raises, roll the session back; in all cases
  close the session. Rollback / close failures are logged and
  swallowed — teardown must not mask the original exception.
* Clear ``request.db_session`` / ``request.auth_principal`` /
  ``request.actor_user_id`` after cleanup so the request object
  cannot be inspected after the middleware returns and accidentally
  see a closed session.

Requests outside ``path_prefixes`` pass through unchanged. This
matches the flask middleware's ``PHASE1_URL_PREFIXES`` gating —
the / hello-world and any future non-API routes stay unaffected.

Test seams
----------

``open_session`` and ``resolve_actor`` are required keyword
arguments rather than module-level globals so the middleware is
exercisable in isolation. Production callers wire them to the real
session factory (``SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY``)
and :func:`session_service.resolve_session` via the helpers
:func:`default_open_session` and :func:`default_resolve_actor` in
this module.

``clock`` defaults to ``datetime.now(timezone.utc)``; tests pass a
fixed-time stub. ``ctx_logger`` defaults to a module logger;
tests can pass a stub to capture cleanup-phase log lines.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from datetime import datetime, timezone
from typing import Any, Callable, Optional, Tuple


_module_logger = logging.getLogger(__name__)


SESSION_MIDDLEWARE_NAME: str = "pychestrate-session"


class PychestrateSessionMiddleware:
    """
        WebWorks middleware that opens a request-scoped SQLAlchemy
        session and resolves the session cookie to an actor before
        the handler runs, then rolls back on failure and always
        closes the session afterward.

        :param open_session: Zero-arg callable that returns a fresh
                             SQLAlchemy session.
        :param resolve_actor: Callable
                              ``(db_session, session_id, now) ->
                              Optional[AuthPrincipal]`` that returns
                              ``None`` on
                              :class:`SessionExpiredError` /
                              :class:`SessionNotFoundError` (the
                              wrappers below do this conversion).
        :param cookie_name: Name of the session cookie to read from
                            ``request.cookies``.
        :param path_prefixes: Tuple of path prefixes the middleware
                              applies to. Requests whose
                              ``request.path`` does not start with
                              any of these pass through untouched.
        :param ctx_logger: Optional logger for cleanup-phase
                           failures. Defaults to a module-level
                           logger.
        :param clock: Optional zero-arg callable returning the
                      current UTC ``datetime`` for cookie
                      resolution. Defaults to
                      ``datetime.now(timezone.utc)``.
    """

    name: str = SESSION_MIDDLEWARE_NAME

    def __init__(
        self,
        *,
        open_session: Callable[[], Any],
        resolve_actor: Callable[[Any, str, datetime], Optional[Any]],
        cookie_name: str,
        path_prefixes: Tuple[str, ...],
        ctx_logger: Optional[logging.Logger] = None,
        clock: Optional[Callable[[], datetime]] = None
    ) -> None:
        """
            Construct the middleware.

            :param open_session: See class docstring.
            :param resolve_actor: See class docstring.
            :param cookie_name: See class docstring.
            :param path_prefixes: See class docstring.
            :param ctx_logger: See class docstring.
            :param clock: See class docstring.
        """
        self._open_session: Callable[[], Any] = open_session
        self._resolve_actor: Callable[[Any, str, datetime], Optional[Any]] = (
            resolve_actor
        )
        self._cookie_name: str = cookie_name
        self._path_prefixes: Tuple[str, ...] = path_prefixes
        self._logger: logging.Logger = (
            ctx_logger if ctx_logger is not None else _module_logger
        )
        self._clock: Callable[[], datetime] = (
            clock if clock is not None else _default_clock
        )
        return

    def _matches_prefix(self, *, path: str) -> bool:
        """
            Test whether a request path falls under any configured
            prefix.

            :param path: Request path.

            :returns: True when the path is in scope.
        """
        for prefix in self._path_prefixes:
            if path.startswith(prefix) is True:
                return True
        return False

    def _attach_actor(self, *, request: Any, db_session: Any) -> None:
        """
            Read the session cookie and attach the resolved principal
            to the request. Unauthenticated requests (no cookie, or
            an expired / unknown cookie) leave ``actor_user_id`` as
            ``None``.

            :param request: Webworks Request instance.
            :param db_session: Open SQLAlchemy session.

            :returns: None.
        """
        cookie_value = request.cookies.get(self._cookie_name, None)
        if cookie_value is None or len(cookie_value) == 0:
            request.auth_principal = None
            request.actor_user_id = None
            return

        principal = self._resolve_actor(
            db_session, cookie_value, self._clock()
        )
        if principal is not None:
            request.auth_principal = principal
            request.actor_user_id = principal.user_id
        else:
            request.auth_principal = None
            request.actor_user_id = None

        return

    def __call__(
        self,
        request: Any,
        call_next: Callable[[Any], Any]
    ) -> Any:
        """
            Wrap a request with session-open / actor-attach /
            session-cleanup. Out-of-scope paths pass through
            unchanged.

            :param request: Webworks Request.
            :param call_next: Next callable in the pipeline (handler
                              or another middleware).

            :returns: The downstream Response.
            :raises: Re-raises any exception raised by
                     ``call_next`` after rolling back the session.
        """
        if self._matches_prefix(path=request.path) is False:
            rtnval = call_next(request)
            return rtnval

        db_session = self._open_session()
        request.db_session = db_session
        self._attach_actor(request=request, db_session=db_session)

        request_failed = False
        try:
            response = call_next(request)
        except BaseException:
            request_failed = True
            raise
        finally:
            if request_failed is True:
                self._safe_rollback(db_session=db_session)
            self._safe_close(db_session=db_session)
            request.db_session = None
            request.auth_principal = None
            request.actor_user_id = None

        rtnval = response
        return rtnval

    def _safe_rollback(self, *, db_session: Any) -> None:
        """
            Roll the session back, swallowing and logging any
            exception. Teardown must not mask the original failure
            that triggered the rollback.

            :param db_session: SQLAlchemy session being rolled back.

            :returns: None.
        """
        try:
            db_session.rollback()
        except Exception as rollback_exc:
            self._logger.exception(
                "pychestrate.session.rollback_failed error=%s", rollback_exc
            )
        return

    def _safe_close(self, *, db_session: Any) -> None:
        """
            Close the session, swallowing and logging any exception.

            :param db_session: SQLAlchemy session being closed.

            :returns: None.
        """
        try:
            db_session.close()
        except Exception as close_exc:
            self._logger.exception(
                "pychestrate.session.close_failed error=%s", close_exc
            )
        return


def _default_clock() -> datetime:
    """
        Return the current UTC time. Pulled out so the module-level
        default is a real ``def`` (importable) rather than an inline
        lambda.

        :returns: Current UTC ``datetime``.
    """
    rtnval = datetime.now(timezone.utc)
    return rtnval


def default_open_session() -> Any:
    """
        Production default for the ``open_session`` constructor arg.

        Reads the database session factory from
        :attr:`SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY` at call
        time (not import time) so the order of bootstrap setup vs.
        middleware install does not matter. Raises
        :class:`ConfigurationError` when the factory has not been
        initialized.

        :returns: A fresh SQLAlchemy session.
        :raises: ConfigurationError when the factory is unset.
    """
    from automojo.errors.exceptions import ConfigurationError
    from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS

    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    if factory is None:
        raise ConfigurationError(
            "SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY has not been "
            "initialized; ensure the webworks bootstrap installs the "
            "factory before requests are served."
        )
    rtnval = factory()
    return rtnval


def default_resolve_actor(
        db_session: Any, session_id: str, now: datetime
    ) -> Optional[Any]:
    """
        Production default for the ``resolve_actor`` constructor arg.

        Wraps :func:`session_service.resolve_session` so the two
        documented exceptions
        (:class:`SessionExpiredError` / :class:`SessionNotFoundError`)
        become a return of ``None`` (the unauthenticated case) rather
        than escaping the middleware. Other exceptions propagate.

        :param db_session: Active SQLAlchemy session.
        :param session_id: Session id from the cookie.
        :param now: Evaluation timestamp.

        :returns: :class:`AuthPrincipal` on success, ``None`` on
                  expired / unknown cookie.
    """
    from automojo.pychestrate.webservice.security.auth.exceptions import (
        SessionExpiredError,
        SessionNotFoundError,
    )
    from automojo.pychestrate.webservice.security.auth.session_service import (
        resolve_session,
    )

    try:
        principal = resolve_session(
            db_session=db_session, session_id=session_id, now=now
        )
    except SessionExpiredError:
        _module_logger.info(
            "pychestrate.session.resolve.expired cookie_prefix=%s",
            session_id[:8],
        )
        return None
    except SessionNotFoundError:
        _module_logger.info(
            "pychestrate.session.resolve.not_found cookie_prefix=%s",
            session_id[:8],
        )
        return None

    rtnval = principal
    return rtnval


def install_pychestrate_session_middleware(
        *,
        app: Any,
        cookie_name: Optional[str] = None,
        path_prefixes: Optional[Tuple[str, ...]] = None,
        open_session: Optional[Callable[[], Any]] = None,
        resolve_actor: Optional[
            Callable[[Any, str, datetime], Optional[Any]]
        ] = None,
        ctx_logger: Optional[logging.Logger] = None,
        clock: Optional[Callable[[], datetime]] = None
    ) -> PychestrateSessionMiddleware:
    """
        Construct the middleware and add it to a webworks app's
        dispatcher pipeline.

        Must be called AFTER :func:`webworks.WebApplication.startup`
        because the dispatcher only exists past
        :data:`LifecyclePhase.INFRASTRUCTURE_READY`. The middleware
        is inserted at ``position="start"`` so it wraps every other
        middleware and runs first on the way in (last on the way
        out).

        :param app: WebWorks application built by
                    ``establish_webapp_persona``. Must have completed
                    ``app.startup()``.
        :param cookie_name: Session cookie name. Defaults to
                            :data:`SESSION_COOKIE_NAME` from
                            ``security.auth.cookies``.
        :param path_prefixes: Tuple of path prefixes the middleware
                              applies to. Defaults to
                              ``("/api/v1/",)`` — all webworks REST
                              routes registered by
                              :func:`register_service_extensions`.
        :param open_session: See
                             :class:`PychestrateSessionMiddleware`.
                             Defaults to :func:`default_open_session`.
        :param resolve_actor: See
                              :class:`PychestrateSessionMiddleware`.
                              Defaults to
                              :func:`default_resolve_actor`.
        :param ctx_logger: See
                           :class:`PychestrateSessionMiddleware`.
        :param clock: See :class:`PychestrateSessionMiddleware`.

        :returns: The installed middleware (useful in tests).
    """
    if cookie_name is None:
        from automojo.pychestrate.webservice.security.auth.cookies import (
            SESSION_COOKIE_NAME,
        )
        resolved_cookie_name = SESSION_COOKIE_NAME
    else:
        resolved_cookie_name = cookie_name

    if path_prefixes is None:
        resolved_path_prefixes = ("/api/v1/",)
    else:
        resolved_path_prefixes = path_prefixes

    if open_session is None:
        resolved_open_session = default_open_session
    else:
        resolved_open_session = open_session

    if resolve_actor is None:
        resolved_resolve_actor = default_resolve_actor
    else:
        resolved_resolve_actor = resolve_actor

    middleware = PychestrateSessionMiddleware(
        open_session=resolved_open_session,
        resolve_actor=resolved_resolve_actor,
        cookie_name=resolved_cookie_name,
        path_prefixes=resolved_path_prefixes,
        ctx_logger=ctx_logger,
        clock=clock,
    )

    app.dispatcher.pipeline.add(
        middleware, name=middleware.name, position="start"
    )

    return middleware


__all__ = [
    "SESSION_MIDDLEWARE_NAME",
    "PychestrateSessionMiddleware",
    "default_open_session",
    "default_resolve_actor",
    "install_pychestrate_session_middleware",
]
