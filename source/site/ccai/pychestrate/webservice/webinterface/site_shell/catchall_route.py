"""
.. module:: webinterface.site_shell.catchall_route
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Attaches the catch-all webworks handler that serves
               the shell document for every non-chromeless,
               non-API, non-static GET.

.. moduleauthor:: Code Craft AI LLC

The catch-all is registered LAST so explicit blueprint routes
(e.g. ``/admin/users`` from PR #200) win the dispatcher match.
For any path that no other handler claims, this module's handler
renders :func:`render_shell_document`.

Why not register a catch-all at ``/{path:path}`` and let webworks
priority-match? Because webworks' router uses
explicit-route-wins semantics, but our concern in M1 is to not
shadow the existing config / projects / resources blueprints
that already render their own templates. We accomplish this by
registering only after every other blueprint -- webworks
considers earlier registrations first.

Per ``specs/1-authentication`` Requirement 5, an unauthenticated
request to a protected shell route must server-side redirect to
``/login?next=<original-path>`` rather than serving the empty
shell document and leaving the client-side JS to discover the
401. The catch-all enforces this: before serving the shell
document it resolves the cookie session the same way the rest of
the consumer UI does (:func:`cookie_session.read_session_from_request`
+ :func:`auth_guard.is_authenticated`) and 303-redirects anonymous
browsers. The ``next`` target is run through
:class:`NextValidator` so it is same-origin-safe.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any
from urllib.parse import quote

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import RedirectResponse, Response

from ccai.pychestrate.webservice.webinterface.site_shell.chromeless_routes import (
    is_shell_candidate,
)
from ccai.pychestrate.webservice.webinterface.site_shell.shell_document import (
    render_shell_document,
)


_module_logger = logging.getLogger(__name__)


CATCHALL_ROOT_PATTERN: str = "/"
CATCHALL_PATH_PATTERN: str = "/{shell_path:path}"


# Canonical browser-side login URL. Mirrors
# ``blueprints.config.routes.LOGIN_PATH``; duplicated here as a
# bare constant so this module does not import the config
# blueprint (which would create an import cycle at startup --
# the config blueprint imports the shell document renderer).
LOGIN_PATH: str = "/login"


def _is_request_authenticated(*, request: Request) -> bool:
    """
        Resolve whether the incoming request carries a valid UI
        session cookie.

        This reuses the canonical consumer-UI session resolution
        (:func:`cookie_session.read_session_from_request` +
        :func:`auth_guard.is_authenticated`) -- the same cookie
        predicate the ``/admin`` dashboard's
        ``require_login_or_redirect`` guard runs before its
        deeper DB token validation. The catch-all only needs the
        cheap cookie-level predicate: a request with no / invalid
        cookie is unambiguously anonymous and must bounce to
        login; a request with a cookie is allowed to reach the
        shell document, whose per-route handlers + the REST
        surface perform the authoritative DB token check.

        On any failure to resolve the cookie secret or decode the
        cookie the request is treated as unauthenticated -- a
        misconfigured deployment fails closed (bounce to login)
        rather than leaking the shell.

        :param request: Incoming webworks request.

        :returns: True when the request carries a valid signed
                  session cookie naming an authenticated user.
    """
    from ccai.pychestrate.webservice.metadata import (  # noqa: E402
        SITE_SHARED_GLOBALS,
    )
    from ccai.pychestrate.webservice.webinterface.foundation import (  # noqa: E402
        auth_guard,
        cookie_session,
    )

    secret = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
    if secret is None or len(secret) < 32:
        rtnval = False
        return rtnval

    try:
        session = cookie_session.read_session_from_request(
            request=request, secret=secret
        )
    except Exception:
        rtnval = False
        return rtnval

    if not isinstance(session, dict):
        rtnval = False
        return rtnval

    rtnval = auth_guard.is_authenticated(session=session)
    return rtnval


def _build_login_redirect(*, request: Request) -> RedirectResponse:
    """
        Build the 303 redirect to ``/login?next=<original>`` for an
        unauthenticated shell request.

        The ``next`` value carries the original request path (plus
        query string when present) and is run through
        :class:`NextValidator` so a malformed / cross-origin path
        cannot turn the post-login redirect into an open redirect.
        A rejected candidate falls back to ``/``.

        :param request: Incoming webworks request.

        :returns: :class:`RedirectResponse` (303) to the login
                  page.
    """
    from ccai.pychestrate.webservice.webinterface.htmlui.next_validator import (  # noqa: E402
        NextValidator,
    )

    try:
        request_path = request.path
    except Exception:
        request_path = ""
    if request_path is None or len(request_path) == 0:
        request_path = "/"

    try:
        query_string = request.query_string
    except Exception:
        query_string = ""
    if isinstance(query_string, bytes):
        try:
            query_string = query_string.decode("utf-8")
        except Exception:
            query_string = ""

    if query_string is not None and len(query_string) > 0:
        next_target = "{}?{}".format(request_path, query_string)
    else:
        next_target = request_path

    validator = NextValidator(fallback_target="/")
    safe_target = validator.resolve_safe_target(
        candidate=next_target, fallback="/"
    )

    encoded_next = quote(safe_target, safe="")
    login_url = "{}?next={}".format(LOGIN_PATH, encoded_next)
    rtnval = RedirectResponse(url=login_url, status_code=303)
    return rtnval


def register_shell_catchall(*, app: Any) -> None:
    """
        Attach the catch-all shell-document handler to the
        supplied webworks application.

        Call this AFTER every other route registration so explicit
        blueprint routes (``/admin/users``, ``/projects/...``,
        ``/login``, ``/api/...``) match first. Webworks gives the
        first-registered route priority on collision; the catch-
        all is a fallback.

        Two handlers register:

        * ``GET /`` -- the root document.
        * ``GET /{shell_path:path}`` -- everything else not
          claimed by a more specific route.

        Both return the same shell document; the JS-side router
        decides what to render once the shell mounts.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
    def _shell_root_handler(request: Request) -> Response:
        rtnval = _serve_shell_or_pass(request=request)
        return rtnval

    def _shell_catchall_handler(request: Request) -> Response:
        rtnval = _serve_shell_or_pass(request=request)
        return rtnval

    app.attach_route(CATCHALL_ROOT_PATTERN, methods=["GET"])(
        _shell_root_handler,
    )
    app.attach_route(CATCHALL_PATH_PATTERN, methods=["GET"])(
        _shell_catchall_handler,
    )
    return


def _serve_shell_or_pass(*, request: Request) -> Response:
    """
        Decide whether the request path should render the shell.

        For non-shell candidates return a 404 so the dispatcher
        does not surface a half-rendered shell on API / static /
        chromeless paths. (In practice, those paths are claimed by
        their own handlers and never reach the catch-all.)

        For shell candidates the request must be authenticated:
        per ``specs/1-authentication`` Requirement 5 an anonymous
        browser hitting a protected shell route (``/runs``,
        ``/admin/*``, ``/`` ...) is server-side 303-redirected to
        ``/login?next=<original-path>`` rather than being served
        an empty shell document. Chromeless surfaces (``/login``,
        ``/logout``, ``/setup/*``, error pages) are already
        excluded by :func:`is_shell_candidate`, so the redirect
        cannot loop.

        :param request: Incoming webworks request.

        :returns: :class:`Response` -- a 404 for non-shell paths,
                  a 303 redirect for an unauthenticated shell
                  path, or the rendered shell document for an
                  authenticated shell path.
    """
    path = getattr(request, "path", "")
    if isinstance(path, str) is False:
        path = ""
    if is_shell_candidate(path=path) is False:
        rtnval = Response(status_code=404, body=b"")
        return rtnval

    if _is_request_authenticated(request=request) is False:
        rtnval = _build_login_redirect(request=request)
        return rtnval

    rtnval = render_shell_document(request=request)
    return rtnval


__all__ = [
    "register_shell_catchall",
    "CATCHALL_ROOT_PATTERN",
    "CATCHALL_PATH_PATTERN",
]
