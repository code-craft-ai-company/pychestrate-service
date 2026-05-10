"""
.. module:: webservice.middleware_setup_gate
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Gate middleware that enforces the first-run setup
               wizard.

.. moduleauthor:: Automation Mojo LLC

While the initial-setup wizard is pending (i.e.
``InitialSetup.completed_at IS NULL``), this middleware redirects
every request whose path is not on a small allowlist to
``/setup/unlock``. Once the wizard is complete the middleware is a
constant-time pass-through.

Allowlist
---------

* Anything under ``/setup/`` -- the unlock + admin-creation pages
  themselves; redirecting setup pages to setup pages would loop.
* Anything under ``/static/`` -- CSS, fonts, etc. for the setup
  pages.
* ``/healthz`` and ``/health`` -- monitoring probes must not flap
  during the (rare, brief) period between first boot and the
  operator finishing the wizard.
* ``/favicon.ico`` -- browsers fetch this aggressively; redirecting
  the favicon to an HTML page is just noise.

Test seams
----------

The completion predicate is injected as ``is_complete`` so unit
tests don't need a real database. The redirect builder is injected
as ``build_redirect`` so tests can assert against a marker rather
than a real ``RedirectResponse``.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any, Callable, Optional, Tuple


_module_logger = logging.getLogger(__name__)


SETUP_GATE_MIDDLEWARE_NAME: str = "pychestrate-setup-gate"


# Path prefixes that bypass the gate. Tuple is matched with
# ``str.startswith`` so the trailing slash is significant.
DEFAULT_ALLOWLIST_PREFIXES: Tuple[str, ...] = (
    "/setup/",
    "/static/",
)


# Exact-match path allowlist for endpoints that don't share a
# prefix with the wizard but must remain reachable while setup is
# pending.
DEFAULT_ALLOWLIST_EXACT: Tuple[str, ...] = (
    "/health",
    "/healthz",
    "/favicon.ico",
)


# Where requests that hit the gate get redirected. Configurable for
# test isolation.
DEFAULT_UNLOCK_PATH: str = "/setup/unlock"


def _default_build_redirect(*, target: str) -> Any:
    """
        Build a 302 redirect ``Response`` to ``target`` using
        webworks' :class:`RedirectResponse`. Imported lazily so this
        module is importable in environments where webworks is not
        installed (unit tests).

        :param target: Path or URL to redirect to.

        :returns: Webworks Response.
    """
    from automojo.webworks.routing.response import RedirectResponse

    rtnval = RedirectResponse(url=target, status_code=302)
    return rtnval


class PychestrateSetupGateMiddleware:
    """
        Per-request gate that diverts traffic to the setup wizard
        until completion.

        :param is_complete: Zero-arg callable that returns ``True``
                            iff setup has finished. The runtime
                            wires this to
                            :func:`setup_service.is_setup_complete`
                            with the active session factory bound
                            in.
        :param allowlist_prefixes: Path prefixes that pass through
                                   even while setup is pending.
                                   Defaults to
                                   :data:`DEFAULT_ALLOWLIST_PREFIXES`.
        :param allowlist_exact: Exact paths that pass through even
                                while setup is pending. Defaults to
                                :data:`DEFAULT_ALLOWLIST_EXACT`.
        :param unlock_path: Redirect target while setup is pending.
                            Defaults to :data:`DEFAULT_UNLOCK_PATH`.
        :param build_redirect: Callable used to build the redirect
                               response. Tests inject a marker;
                               production uses the webworks
                               :class:`RedirectResponse` builder.
        :param ctx_logger: Optional logger. Defaults to a module
                           logger.
    """

    name: str = SETUP_GATE_MIDDLEWARE_NAME

    def __init__(
        self,
        *,
        is_complete: Callable[[], bool],
        allowlist_prefixes: Optional[Tuple[str, ...]] = None,
        allowlist_exact: Optional[Tuple[str, ...]] = None,
        unlock_path: Optional[str] = None,
        build_redirect: Optional[Callable[..., Any]] = None,
        ctx_logger: Optional[logging.Logger] = None,
    ) -> None:
        """
            Construct the middleware.

            :param is_complete: See class docstring.
            :param allowlist_prefixes: See class docstring.
            :param allowlist_exact: See class docstring.
            :param unlock_path: See class docstring.
            :param build_redirect: See class docstring.
            :param ctx_logger: See class docstring.
        """
        if is_complete is None:
            from automojo.errors.exceptions import ConfigurationError
            raise ConfigurationError(
                "PychestrateSetupGateMiddleware requires is_complete"
            )

        if allowlist_prefixes is None:
            resolved_prefixes = DEFAULT_ALLOWLIST_PREFIXES
        else:
            resolved_prefixes = allowlist_prefixes

        if allowlist_exact is None:
            resolved_exact = DEFAULT_ALLOWLIST_EXACT
        else:
            resolved_exact = allowlist_exact

        if unlock_path is None:
            resolved_unlock_path = DEFAULT_UNLOCK_PATH
        else:
            resolved_unlock_path = unlock_path

        if build_redirect is None:
            resolved_build_redirect: Callable[..., Any] = (
                _default_build_redirect
            )
        else:
            resolved_build_redirect = build_redirect

        if ctx_logger is None:
            resolved_logger = _module_logger
        else:
            resolved_logger = ctx_logger

        self._is_complete: Callable[[], bool] = is_complete
        self._allowlist_prefixes: Tuple[str, ...] = resolved_prefixes
        self._allowlist_exact: Tuple[str, ...] = resolved_exact
        self._unlock_path: str = resolved_unlock_path
        self._build_redirect: Callable[..., Any] = resolved_build_redirect
        self._logger: logging.Logger = resolved_logger
        return

    def _is_path_allowlisted(self, *, path: str) -> bool:
        """
            Check whether a request path bypasses the gate. Hits
            either an exact match or a prefix match.

            :param path: Request path.

            :returns: True when the path bypasses.
        """
        for exact in self._allowlist_exact:
            if path == exact:
                return True
        for prefix in self._allowlist_prefixes:
            if path.startswith(prefix) is True:
                return True
        return False

    def __call__(
        self,
        request: Any,
        call_next: Callable[[Any], Any],
    ) -> Any:
        """
            Run the gate.

            * If setup is complete, the request passes through to
              ``call_next`` unchanged.
            * If the path is allowlisted, the request passes through
              unchanged so the operator can reach the unlock pages.
            * Otherwise, return a 302 redirect to ``unlock_path``.

            :param request: Webworks Request.
            :param call_next: Next callable in the pipeline.

            :returns: Response from ``call_next`` or a 302 redirect.
        """
        if self._is_complete() is True:
            rtnval = call_next(request)
            return rtnval

        if self._is_path_allowlisted(path=request.path) is True:
            rtnval = call_next(request)
            return rtnval

        self._logger.info(
            "pychestrate.setup.gate.redirect path=%s -> %s",
            request.path,
            self._unlock_path,
        )
        rtnval = self._build_redirect(target=self._unlock_path)
        return rtnval


def install_pychestrate_setup_gate_middleware(
        *,
        app: Any,
        is_complete: Callable[[], bool],
        allowlist_prefixes: Optional[Tuple[str, ...]] = None,
        allowlist_exact: Optional[Tuple[str, ...]] = None,
        unlock_path: Optional[str] = None,
        build_redirect: Optional[Callable[..., Any]] = None,
        ctx_logger: Optional[logging.Logger] = None,
    ) -> PychestrateSetupGateMiddleware:
    """
        Construct the gate and add it to a webworks app's dispatcher
        pipeline.

        Inserted at ``position="start"`` so it wraps every other
        middleware -- the redirect must land before the session
        middleware spins up a DB session, before the auth middleware
        rejects an unauthenticated request, etc.

        Must be called AFTER :func:`webworks.WebApplication.startup`
        so the dispatcher exists.

        :param app: WebWorks application.
        :param is_complete: See
                            :class:`PychestrateSetupGateMiddleware`.
        :param allowlist_prefixes: See class.
        :param allowlist_exact: See class.
        :param unlock_path: See class.
        :param build_redirect: See class.
        :param ctx_logger: See class.

        :returns: The installed middleware (useful in tests).
    """
    middleware = PychestrateSetupGateMiddleware(
        is_complete=is_complete,
        allowlist_prefixes=allowlist_prefixes,
        allowlist_exact=allowlist_exact,
        unlock_path=unlock_path,
        build_redirect=build_redirect,
        ctx_logger=ctx_logger,
    )
    app.dispatcher.pipeline.add(
        middleware, name=middleware.name, position="start"
    )
    rtnval = middleware
    return rtnval


__all__ = [
    "DEFAULT_ALLOWLIST_EXACT",
    "DEFAULT_ALLOWLIST_PREFIXES",
    "DEFAULT_UNLOCK_PATH",
    "PychestrateSetupGateMiddleware",
    "SETUP_GATE_MIDDLEWARE_NAME",
    "install_pychestrate_setup_gate_middleware",
]
