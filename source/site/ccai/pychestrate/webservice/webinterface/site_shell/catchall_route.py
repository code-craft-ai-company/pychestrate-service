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
+ :func:`auth_guard.is_authenticated`), validates the cookie's
session token against the database (one indexed lookup -- the
same deep check the blueprint guards run, so a stale logged-out
cookie bounces too), and 303-redirects anonymous browsers. The
``next`` target is run through :class:`NextValidator` so it is
same-origin-safe.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any, Dict
from urllib.parse import quote

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.site_shell.chromeless_routes import (
    is_chromeless,
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


def _is_session_row_alive(*, session: Dict[str, Any]) -> bool:
    """
        Validate the cookie's ``session_token`` against the
        database -- the same deep check the ``/admin`` dashboard
        performs via
        :func:`blueprints.config.routes._validate_session_via_security_manager`.
        A signed cookie whose session row has been closed (logout)
        or has expired is stale and must not receive the shell.

        Imported lazily so this module keeps its startup
        independence from the config blueprint (which imports the
        shell-document renderer -- a module-level import here
        would cycle).

        On any infrastructure failure (unconfigured session
        factory, DB error) the check fails closed.

        :param session: Decoded session dict from the cookie.

        :returns: True when the token names a live session row.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (  # noqa: E402
        _validate_session_via_security_manager,
    )

    try:
        validated = _validate_session_via_security_manager(
            session=session
        )
    except Exception:
        validated = None

    rtnval = validated is not None
    return rtnval


def _is_request_authenticated(*, request: Request) -> bool:
    """
        Resolve whether the incoming request carries a live UI
        session.

        Two layers run in order:

        * The cheap cookie predicate
          (:func:`cookie_session.read_session_from_request` +
          :func:`auth_guard.is_authenticated`) -- a request with
          no / invalid / unsigned cookie is unambiguously
          anonymous and bounces without touching the database.
        * The DB token check (:func:`_is_session_row_alive`) --
          the same single session-token lookup the legacy
          blueprint guards perform. Without it a logged-out
          (stale) cookie still passes the cookie predicate and
          receives the full shell document. One indexed lookup
          per shell GET is the cost of not serving the shell to
          dead sessions; the per-route handlers + REST surface
          still perform their own authoritative checks.

        On any failure to resolve the cookie secret, decode the
        cookie, or reach the session store the request is treated
        as unauthenticated -- a misconfigured deployment fails
        closed (bounce to login) rather than leaking the shell.

        :param request: Incoming webworks request.

        :returns: True when the request carries a valid signed
                  session cookie naming a live session.
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

    if auth_guard.is_authenticated(session=session) is False:
        rtnval = False
        return rtnval

    rtnval = _is_session_row_alive(session=session)
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
        ``/login``, ``/api/...``) match first. Ordering is a
        readability convention, not a correctness requirement:
        the webworks router is a specificity-ordered trie that
        tries static path segments before parameterized ones, so
        explicit routes win over the ``{shell_path:path}``
        catch-all regardless of registration order.

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


def _build_not_found_response(*, path: str, request: Any = None) -> Response:
    """
        Build the 404 for a path the catch-all does not own.

        Browser-facing paths (anything that is not an API / static /
        webhook path) get the shared error page from
        :mod:`site_shell.error_pages` -- inside the shell for a
        signed-in browser, chromeless otherwise. API-ish paths keep a
        terse plain-text body so clients never receive HTML.

        :param path: The request path that missed.
        :param request: The incoming request (drives the
                        authenticated / anonymous rendering choice).

        :returns: :class:`Response` with status 404.
    """
    api_like = False
    for prefix in ("/api/", "/static/", "/webhooks/", "/mj/"):
        if path.startswith(prefix):
            api_like = True
            break
    if api_like is False and request is not None:
        try:
            from ccai.pychestrate.webservice.webinterface.site_shell.error_pages import (  # noqa: E402
                render_error_response,
            )
            rtnval = render_error_response(request=request, status_code=404)
            return rtnval
        except Exception:
            pass
    if api_like is False:
        # Templating unavailable (early boot, stubbed environment):
        # a minimal but complete document rather than plain text.
        page_html = (
            "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
            "<title>Page not found · Pychestrate</title></head><body>"
            "<main><h1>Page not found</h1>"
            "<p>The address may be mistyped, or the page may have moved.</p>"
            "<p><a href=\"/\">Go to the home page</a> or <a href=\"/login\">sign in</a>.</p>"
            "</main></body></html>"
        )
        rtnval = HTMLResponse(content=page_html, status_code=404)
        return rtnval
    rtnval = Response(
        status_code=404,
        body=b"Not Found",
        headers={"Content-Type": "text/plain; charset=utf-8"},
    )
    return rtnval
def _serve_shell_or_pass(*, request: Request) -> Response:
    """
        Decide whether the request path should render the shell.

        For non-shell candidates return a 404 -- a friendly HTML
        page for chromeless-prefix paths, a plain-text body for
        API-ish paths, both with an explicit ``Content-Type``
        (see :func:`_build_not_found_response`).

        For shell candidates the request must be authenticated:
        per ``specs/1-authentication`` Requirement 5 an anonymous
        browser hitting a protected shell route (``/runs``,
        ``/admin/*``, ``/`` ...) is server-side 303-redirected to
        ``/login?next=<original-path>`` rather than being served
        an empty shell document. A syntactically valid cookie
        whose session row is dead (logout / expiry) is treated
        the same way. Chromeless surfaces (``/login``,
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
        rtnval = _build_not_found_response(path=path, request=request)
        return rtnval

    if _is_request_authenticated(request=request) is False:
        # Only paths the shell actually owns earn a login redirect;
        # a mistyped URL is a 404 whether or not the browser is
        # signed in, so anonymous visitors are not asked to sign in
        # just to be told the page does not exist.
        if _is_known_shell_route(path=path) is False:
            rtnval = _build_not_found_response(path=path, request=request)
            return rtnval
        rtnval = _build_login_redirect(request=request)
        return rtnval

    if _is_known_shell_route(path=path) is False:
        # Signed in, but the path belongs to nothing: a real 404 inside
        # the shell rather than a 200 whose body says "not found".
        rtnval = _build_not_found_response(path=path, request=request)
        return rtnval

    rtnval = render_shell_document(request=request)
    return rtnval
def _is_known_shell_route(*, path: str) -> bool:
    """
        True when ``path`` is the shell root or lies under a prefix a
        registered web-component bundle owns (``/admin``, ``/runs``,
        ``/pods`` ...). Blueprint routes never reach the catch-all,
        so bundle prefixes are the only other legitimate shell paths.

        :param path: Request path.

        :returns: Whether the shell owns the path.
    """
    if path in ("", "/"):
        return True
    from ccai.pychestrate.webservice.webinterface.site_shell.bundle_registry import (  # noqa: E402
        install_default_bundles,
        registered_route_prefixes,
    )
    prefixes = [prefix for prefix in registered_route_prefixes() if len(prefix) > 0]
    if len(prefixes) == 0:
        # The registry is populated at bootstrap; a bare process
        # (unit tests, tooling) still knows the default bundle set.
        install_default_bundles()
        prefixes = [prefix for prefix in registered_route_prefixes() if len(prefix) > 0]
    for prefix in prefixes:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False
__all__ = [
    "register_shell_catchall",
    "CATCHALL_ROOT_PATTERN",
    "CATCHALL_PATH_PATTERN",
]
