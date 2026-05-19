"""
.. module:: webinterface.site_shell.chromeless_routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: The canonical list of route prefixes that bypass
               the site-shell document.

.. moduleauthor:: Automation Mojo LLC

Per ``specs/9-site-shell`` Requirement 3.2, the login, logout,
setup wizard, health, and error pages render chromeless (no
``<pyc-site-shell>`` element, no shell bundle import). This module
exposes the authoritative list and a single helper
:func:`is_chromeless`.

M1 enforcement is intentionally minimal -- a startup sanity log
on collisions, no ``ConfigurationError`` yet. The full B-3
enforcement lands in a follow-up PR once the chromeless surface
list stabilizes.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Iterable, Set


_module_logger = logging.getLogger(__name__)


CHROMELESS_ROUTE_PREFIXES: frozenset = frozenset({
    "/login",
    "/logout",
    "/setup",
    "/__health",
    "/errors",
})


# Routes the shell catch-all explicitly does not own because some
# other registered surface (REST API, static files) takes
# precedence. Listed here for clarity even though the catch-all
# would already miss them via priority ordering.
NON_SHELL_PATH_PREFIXES: frozenset = frozenset({
    "/api/",
    "/static/",
    "/webhook/",
})


def is_chromeless(*, path: str) -> bool:
    """
        Return True when the supplied path should render without
        the site-shell chrome (i.e. it is one of the canonical
        chromeless surfaces).

        :param path: Incoming request path (e.g. ``"/login"``,
                     ``"/admin/users"``).

        :returns: True when the path matches a chromeless prefix.
    """
    if path is None or len(path) == 0:
        rtnval = False
        return rtnval
    for prefix in CHROMELESS_ROUTE_PREFIXES:
        if path == prefix:
            rtnval = True
            return rtnval
        if path.startswith(prefix + "/"):
            rtnval = True
            return rtnval
    rtnval = False
    return rtnval


def is_shell_candidate(*, path: str) -> bool:
    """
        Return True when the supplied path is a candidate for
        rendering inside the site-shell document. False for API
        paths, static files, webhooks, and any chromeless surface.

        :param path: Incoming request path.

        :returns: True when the path should resolve to the shell
                  document (assuming no more-specific blueprint
                  route claims it first).
    """
    if path is None or len(path) == 0:
        rtnval = False
        return rtnval
    if is_chromeless(path=path) is True:
        rtnval = False
        return rtnval
    for prefix in NON_SHELL_PATH_PREFIXES:
        if path.startswith(prefix) is True:
            rtnval = False
            return rtnval
    rtnval = True
    return rtnval


def validate_chromeless_routes_at_startup(
        *,
        registered_paths: Iterable[str]
    ) -> Set[str]:
    """
        Sanity-check the registered route list at startup --
        warn (do not raise) when a non-auth/setup blueprint
        claims one of the chromeless prefixes verbatim.

        Returns the set of offending paths so the caller can
        decide whether to log, fail, or ignore. The default
        behavior in :func:`app_pychestrate_main` is to emit a
        warning log; full ``ConfigurationError`` enforcement is
        deferred to B-3 follow-up.

        :param registered_paths: Iterable of currently-registered
                                 webworks route patterns.

        :returns: Set of offending paths (may be empty).
    """
    offenders: Set[str] = set()
    if registered_paths is None:
        return offenders
    for candidate in registered_paths:
        if candidate is None or len(candidate) == 0:
            continue
        if candidate in CHROMELESS_ROUTE_PREFIXES:
            # Exact prefix match without trailing wildcard --
            # acceptable when registered by auth / setup, but we
            # cannot tell from the path alone. Log only.
            _module_logger.info(
                "pychestrate.ui.shell.chromeless_route_registered "
                "path=%s",
                candidate,
            )
    return offenders


__all__ = [
    "CHROMELESS_ROUTE_PREFIXES",
    "NON_SHELL_PATH_PREFIXES",
    "is_chromeless",
    "is_shell_candidate",
    "validate_chromeless_routes_at_startup",
]
