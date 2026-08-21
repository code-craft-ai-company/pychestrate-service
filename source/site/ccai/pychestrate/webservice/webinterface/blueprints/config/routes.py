"""
.. module:: webinterface.blueprints.config.routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config (D1
               slice — auth + dashboard).

.. moduleauthor:: Code Craft AI LLC

The config blueprint owns the consumer-facing ``/config``
surface. This module lands the auth + dashboard slice:

* ``GET /config/login`` -- render the login form.
* ``POST /config/login`` -- authenticate and redirect.
* ``POST /config/logout`` -- clear the session and redirect.
* ``GET /config/`` and ``GET /config/dashboard`` -- the
  authenticated dashboard.

The sibling ``routes_*.py`` modules carry the remaining 25
routes (users / roles / variables / scopes / secrets /
sessions / audit) on top of the same foundation pieces.

Foundation pieces consumed
--------------------------

* :mod:`webinterface.foundation.cookie_session` for the
  signed-cookie session that carries
  ``user_id`` / ``username`` / ``session_token`` / ``csrf_token``
  between requests.
* :mod:`webinterface.foundation.csrf` for the form-post
  protection.
* :mod:`webinterface.foundation.flash` for one-shot
  user-facing messages.
* :mod:`webinterface.foundation.auth_guard` for the per-handler
  ``require_login`` / ``enforce_csrf`` gating shape.
* :mod:`webinterface.foundation.templating` for the
  jinja2 render-to-HTMLResponse helper.
* :mod:`webinterface.foundation.url_for` for the template
  link-builder.

Auth backend
------------

The actual authentication is delegated to
:class:`ccai.pychestrate.core.managers.security_manager.SecurityManager`.
Webworks
handlers open a SQLAlchemy session per request via the bootstrap-
populated ``SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY`` and
hand it to :class:`SecurityManager`. The cookie session merely
carries the auth token between requests; the source of truth for
"is this token still valid" lives in the database.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    cookie_session,
    csrf,
    flash,
    templating,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.htmlui.next_validator import (
    NextValidator,
)


# ---------------------------------------------------------------------------
# URL constants
# ---------------------------------------------------------------------------
#
# Two URL surfaces live in this blueprint after the p17b unified-
# login refactor:
#
# * ``ADMIN_PATH`` (``/admin``) hosts the authenticated admin UI
#   (dashboard, users, roles, variables, scopes, secrets,
#   sessions, audit). Every ``routes_*.py`` sibling module mounts
#   under this prefix.
# * The login + logout HTML surface lives at unprefixed
#   ``/login`` and ``/logout`` per 1-authentication Requirement
#   5 -- the unified login page that every protected route
#   redirects unauthenticated browsers to.
#
# ``CONFIG_PATH`` is preserved as an alias of ``ADMIN_PATH`` so
# the per-feature sibling modules (which import ``CONFIG_PATH``
# at top level) keep working without a churn-PR touching every
# one of them. The variable name is wrong post-rename; the
# follow-on shell PR (p17c) renames the imports cluster-wide.

ADMIN_PATH = "/admin"
CONFIG_PATH = ADMIN_PATH

# Canonical browser-side URLs for the unified login flow.
LOGIN_PATH = "/login"
LOGOUT_PATH = "/logout"


# ---------------------------------------------------------------------------
# Endpoint registrations -- (endpoint_name, full_path, methods)
#
# Templates link via ``url_for('config.X')``; the endpoint name
# stays as ``config.<action>`` for back-compat with existing
# templates even though the dashboard now lives under
# ``/admin``. The per-PR sibling modules append handlers below
# via their own ``register_*_routes`` functions.
# ---------------------------------------------------------------------------


# Auth routes registered at unprefixed root paths (1-auth
# Requirement 5).
_AUTH_ROUTE_TABLE = (
    ("config.login", LOGIN_PATH, ("GET",)),
    ("config.login_submit", LOGIN_PATH, ("POST",)),
    # ``GET /logout`` is the convenience entrypoint sidebar
    # links bind to; ``POST /logout`` is the legacy form-post
    # the existing base template uses. Both share the same
    # session-clearing primitive.
    ("config.logout", LOGOUT_PATH, ("GET", "POST")),
)


# Authenticated dashboard pages under the ``/admin`` prefix.
#
# The ``config.admin_overview`` / ``config.feature_flags`` /
# ``config.extension_registry`` / ``config.system_health`` entries
# are shell-native Web Component views (PR p21f / audit items
# 9-admin-ui + E-extension-registry-ui). Their server handler is
# the shared :func:`handle_dashboard` flow -- it performs the auth
# check and renders the shell document -- and ``pyc-admin-bundle``
# replaces the shell ``<main>`` content with the route-appropriate
# Custom Element client-side. The bare ``/admin`` path (the
# ``config.dashboard_root`` entry) also mounts the shell-native
# ``<pyc-admin-overview>`` view: the WC overview wins for ``/admin``
# because the bundle replaces ``<main>`` for every route it owns.
_ADMIN_ROUTE_TABLE = (
    ("config.dashboard_root", "/", ("GET",)),
    ("config.dashboard", "/dashboard", ("GET",)),
    ("config.admin_overview", "/overview", ("GET",)),
    ("config.feature_flags", "/feature-flags", ("GET",)),
    ("config.extension_registry", "/extensions", ("GET",)),
    ("config.system_health", "/system-health", ("GET",)),
)


# Path-prefix → page-label table for the ``/admin`` surface. The
# shell wrapper resolves the ``<title>`` for every admin render
# from this table (longest matching prefix wins) so each admin
# page gets a distinguishable browser title instead of every tab
# reading "Pychestrate". The table covers this module's
# ``_ADMIN_ROUTE_TABLE`` entries plus the per-feature sibling
# modules' route prefixes; an unmatched path falls back to the
# bare product name.
_ADMIN_PAGE_TITLE_TABLE: Tuple[Tuple[str, str], ...] = (
    (ADMIN_PATH + "/dashboard", "Dashboard"),
    (ADMIN_PATH + "/overview", "Overview"),
    (ADMIN_PATH + "/feature-flags", "Feature Flags"),
    (ADMIN_PATH + "/extensions", "Extension Registry"),
    (ADMIN_PATH + "/system-health", "System Health"),
    (ADMIN_PATH + "/users", "Users"),
    (ADMIN_PATH + "/roles", "Roles"),
    (ADMIN_PATH + "/variables", "Variables"),
    (ADMIN_PATH + "/scopes", "Secret Scopes"),
    (ADMIN_PATH + "/secrets", "Secrets"),
    (ADMIN_PATH + "/sessions", "Sessions"),
    (ADMIN_PATH + "/audit-logs", "Audit Logs"),
    (ADMIN_PATH + "/enrollment-tokens", "Enrollment Tokens"),
)


_DEFAULT_PAGE_TITLE = "Pychestrate"







# ---------------------------------------------------------------------------
# Endpoint patterns the templates reference but that land in later
# PRs (D2/D3/D4). Pre-registering the URL patterns lets jinja templates
# resolve ``url_for('config.user_list')`` etc. without crashing on the
# D1 dashboard render. Each future PR moves the entry from this table
# into ``_ROUTE_TABLE`` and lands the handler at the same time.
# ---------------------------------------------------------------------------


# All previously-stubbed config endpoints have shipped. The tuple
# stays in the source as a hook for any post-D4 additions that
# need to be reachable by ``url_for`` before their handler lands.
_FUTURE_ENDPOINT_PATTERNS: Tuple[Tuple[str, str], ...] = ()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_db_session() -> Any:
    """
        Open a fresh SQLAlchemy session from the bootstrap-
        published factory.

        :returns: A new :class:`Session`.
        :raises: RuntimeError when the factory has not been
                 populated. The runtime bootstrap is expected to
                 have set this; if the handler reaches this code
                 path without it, the deployment is misconfigured.
    """
    factory = SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY
    if factory is None:
        raise RuntimeError(
            "DATABASE_SESSION_FACTORY not configured. The runtime"
            " bootstrap must run before web UI handlers serve."
        )
    rtnval = factory()
    return rtnval


def _resolve_ui_cookie_secret() -> bytes:
    """
        Return the bootstrap-published UI cookie signing secret.

        :returns: Bytes >= 32.
        :raises: RuntimeError when the secret has not been
                 published. The bootstrap loads it from the
                 ``PYCHESTRATE_UI_COOKIE_SECRET_*`` env vars; an
                 unconfigured deployment cannot run the consumer
                 web UI.
    """
    secret = SITE_SHARED_GLOBALS.UI_COOKIE_SECRET
    if secret is None or len(secret) < 32:
        raise RuntimeError(
            "UI_COOKIE_SECRET not configured. Set"
            " PYCHESTRATE_UI_COOKIE_SECRET_SOURCE +"
            " _FILE_PATH or _ENV_VAR before booting the web UI."
        )
    rtnval = secret
    return rtnval


def _read_session(*, request: Request) -> Dict[str, Any]:
    """
        Read + verify the UI session cookie from a webworks
        request. Returns an empty dict on no / invalid cookie.
    """
    secret = _resolve_ui_cookie_secret()
    rtnval = cookie_session.read_session_from_request(
        request=request, secret=secret
    )
    return rtnval


def _attach_session_to_response(
        *, response: Response, session: Dict[str, Any]
    ) -> Response:
    """
        Sign + attach the (possibly mutated) session dict to the
        outgoing response. Returns the response so handlers can
        chain.
    """
    secret = _resolve_ui_cookie_secret()
    cookie_session.write_session_to_response(
        response=response, payload=session, secret=secret
    )
    return response


def _clear_session_on_response(*, response: Response) -> Response:
    """
        Delete the UI session cookie on the response. Used by
        logout.
    """
    cookie_session.clear_session_cookie_on_response(response=response)
    return response


def _parse_form_or_empty(*, request: Request) -> Dict[str, Any]:
    """
        Decode the request's form-encoded body. Returns an empty
        dict on decode failure / non-form body so handler
        validation logic can branch on missing fields rather than
        catching exceptions.
    """
    try:
        rtnval = request.form()
    except Exception:
        rtnval = {}
    if not isinstance(rtnval, dict):
        return {}
    return rtnval


def _parse_form_multi(*, request: Request) -> Dict[str, List[str]]:
    """
        Parse the request body as form-encoded data and return
        every value for every key (preserving multi-checkbox
        submissions). The webworks ``request.form()`` collapses
        multi-value keys to the first value, which loses the
        ``role_ids[]`` / ``permission_ids[]`` shape the
        templates rely on.

        Returns an empty dict on any decode failure so handler
        callsites can branch on emptiness rather than catching.

        :param request: Webworks Request.

        :returns: Dict of field-name → list-of-values.
    """
    try:
        body_bytes = request.body
    except Exception:
        return {}
    if body_bytes is None or len(body_bytes) == 0:
        return {}
    try:
        body_str = body_bytes.decode("utf-8")
    except Exception:
        return {}
    try:
        parsed = parse_qs(body_str, keep_blank_values=True)
    except Exception:
        return {}
    rtnval: Dict[str, List[str]] = {}
    for key, values in parsed.items():
        cleaned: List[str] = []
        for v in values:
            cleaned.append(str(v))
        rtnval[key] = cleaned
    return rtnval


class MultiFormView:
    """
        Tiny wrapper exposing a ``getlist`` / ``get`` shape over a
        parsed multi-value form dict. Lets the existing templates
        -- which call ``form_data.getlist('role_ids')`` on
        form-redirect renders -- consume the form data unchanged.
        Built once per handler from :func:`_parse_form_multi`
        output.

        :param data: Dict of ``field_name → list-of-string-values``.
    """

    def __init__(self, *, data: Dict[str, List[str]]) -> None:
        self._data: Dict[str, List[str]] = data
        return

    def getlist(self, key: str) -> List[str]:
        """
            Return the list of values submitted for ``key``.
            Empty list when the field was absent.

            :param key: Form field name.
            :returns: List of submitted values.
        """
        rtnval = self._data.get(key, [])
        return rtnval

    def get(
            self, key: str, default: Optional[str] = None
        ) -> Optional[str]:
        """
            Return the first submitted value for ``key`` (matches
            the conventional MultiDict semantics).

            :param key: Form field name.
            :param default: Returned when the field is absent.
            :returns: The first value or ``default``.
        """
        values = self._data.get(key, None)
        if values is None or len(values) == 0:
            return default
        rtnval = values[0]
        return rtnval

    def __contains__(self, key: str) -> bool:
        rtnval = key in self._data
        return rtnval

    def __getitem__(self, key: str) -> str:
        """
            Dict-shaped subscript access. Used by jinja2 when a
            template writes ``form_data.var_type`` -- jinja first
            tries ``getattr`` (no ``var_type`` attribute) then
            falls back to ``__getitem__``.

            :param key: Form field name.

            :returns: First submitted value.
            :raises: KeyError when the field is absent.
        """
        values = self._data.get(key, None)
        if values is None or len(values) == 0:
            raise KeyError(key)
        rtnval = values[0]
        return rtnval


@dataclass
class _AuthResolution:
    """
        Result of :func:`_resolve_authenticated_request`. Either
        carries a redirect response (anonymous / expired session)
        OR the resolved authenticated context.

        :param redirect_response: Set when the request must bounce
                                  back to the login page.
        :param session: Mutable session dict (caller writes back
                        to the response cookie).
        :param db_session: Open SQLAlchemy session. Caller MUST
                           close in a finally block.
        :param user_id: Authenticated user's ID.
        :param username: Authenticated user's username.
        :param csrf_token: Server-of-record CSRF token (refreshed
                           on every authenticated render).
    """
    redirect_response: Optional[Response] = None
    session: Dict[str, Any] = field(default_factory=dict)
    db_session: Any = None
    user_id: str = ""
    username: str = ""
    csrf_token: str = ""


def _build_default_template_context(
        *,
        session: Dict[str, Any],
        request_endpoint: str,
        flashes: Optional[Any] = None,
        csrf_token: Optional[str] = None
    ) -> Dict[str, Any]:
    """
        Build the baseline jinja2 context every page render expects.
        ``base.html`` references ``username`` / ``request_endpoint``
        / ``flashes`` / ``csrf_token`` directly; pulling them out of
        the session here keeps every handler from re-doing the same
        five-line plumbing.

        :param session: Decoded session dict (may be empty for an
                        anonymous request).
        :param request_endpoint: Endpoint name of the current
                                 handler (e.g. ``"config.login"``);
                                 used by the sidebar to highlight
                                 the active page.
        :param flashes: Optional pre-drained flash list; ``None``
                        means "render with no flashes shown" (the
                        caller has not consumed the queue).
        :param csrf_token: Optional CSRF token for forms in the
                           rendered page.

        :returns: Dict ready to pass as ``context=`` to
                  :func:`render_template_response`.
    """
    raw_username = session.get("username", "")
    if not isinstance(raw_username, str):
        raw_username = ""

    if flashes is None:
        flashes_value: Any = []
    else:
        flashes_value = flashes

    if csrf_token is None:
        csrf_value = ""
    else:
        csrf_value = csrf_token

    rtnval = {
        "username": raw_username,
        "request_endpoint": request_endpoint,
        "flashes": flashes_value,
        "csrf_token": csrf_value,
    }
    return rtnval


# ---------------------------------------------------------------------------
# Security-manager + auth-request construction
#
# These two builders are pulled out of the handler bodies so unit
# tests can patch them at the module level (overriding the
# lazy-imported SecurityManager / AuthRequest with fakes) without
# having to import the source ``security_manager`` module --
# whose password-hashing helpers are not part of the test
# runtime's dep set.
# ---------------------------------------------------------------------------


def _build_security_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ConsumerUISecurityAdapter` -- the
        modern auth-stack-backed drop-in replacement for the
        legacy ``SecurityManager``. Same four-method interface
        the consumer-UI handlers already use; the adapter wires
        :meth:`authenticate` / :meth:`validate_token` /
        :meth:`logout` onto
        :mod:`security.auth.local_flow` +
        :mod:`security.auth.session_service` and keeps
        :meth:`check_permission` delegated to the legacy stack
        until RBAC migrates separately. See
        :mod:`webinterface.blueprints.config.auth_adapter` for
        the adapter contract.

        :param db_session: Open SQLAlchemy session.

        :returns: ConsumerUISecurityAdapter instance.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config.auth_adapter import (  # noqa: E402
        ConsumerUISecurityAdapter,
    )
    rtnval = ConsumerUISecurityAdapter(db_session)
    return rtnval


def _build_auth_request(
        *, username: str, password: str, client_ip: str, user_agent: str
    ) -> Any:
    """
        Construct an :class:`AuthRequest` carrying the
        login-form-submitted credentials + client metadata.

        :param username: Submitted username.
        :param password: Submitted password.
        :param client_ip: ``X-Forwarded-For`` header (or "").
        :param user_agent: ``User-Agent`` header (or "").

        :returns: AuthRequest instance.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config.auth_adapter import (  # noqa: E402
        AuthRequest,
    )
    rtnval = AuthRequest(
        username=username,
        password=password,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return rtnval


def _resolve_admin_page_title(*, path: str) -> str:
    """
        Resolve the shell document ``<title>`` for an admin page
        from the request path via :data:`_ADMIN_PAGE_TITLE_TABLE`.
        The longest matching prefix wins so detail pages (e.g.
        ``/admin/secrets/create``) inherit their section's title.
        Unmatched paths keep the bare product-name default.

        :param path: Request path (e.g. ``"/admin/users/u-1"``).

        :returns: Title string (e.g. ``"Users · Pychestrate"``).
    """
    if path is None or len(path) == 0:
        rtnval = _DEFAULT_PAGE_TITLE
        return rtnval

    best_label = None
    best_length = -1
    for prefix, label in _ADMIN_PAGE_TITLE_TABLE:
        if path == prefix or path.startswith(prefix + "/"):
            if len(prefix) > best_length:
                best_label = label
                best_length = len(prefix)

    if best_label is None:
        rtnval = _DEFAULT_PAGE_TITLE
        return rtnval

    rtnval = "{} · {}".format(best_label, _DEFAULT_PAGE_TITLE)
    return rtnval


def _wrap_admin_handler_in_shell(handler: Any) -> Any:
    """
        Wrap an admin-blueprint handler so its HTML response body
        renders as a content fragment inside the site shell's main
        slot.

        The blueprint handlers under ``/admin/*`` render templates
        that extend the fragment-style ``config/base.html`` -- a
        bare section, no ``<html>/<head>/<body>``, no header /
        sidebar, no Vue bootstrap chrome. This wrapper takes the
        rendered fragment and re-emits it inside the shell document
        (``site_shell/shell_document.html``) so the unified header +
        sidebar render around it.

        Non-HTML responses (e.g. ``RedirectResponse`` after a POST)
        pass through unchanged. The response status code is preserved.

        Per ``9-site-shell`` PR4 task F-1 / strategy A: the explicit
        blueprint route still owns ``/admin/*`` (so we can keep the
        existing webworks dispatch), but every authenticated render
        now boots inside the shell. The shell bundle plus the admin
        sidebar bundle (``pyc-admin-bundle``) are selected by
        :func:`bundles_for` against the request's path, so the
        admin sidebar group only loads on ``/admin/*`` paths.

        :param handler: The original handler taking a webworks
                        ``Request`` and returning a ``Response``.

        :returns: A new callable with the same signature that wraps
                  the response body in the shell document when the
                  response is an HTML render.
    """
    from ccai.pychestrate.webservice.webinterface.site_shell.shell_document import (  # noqa: E402
        render_shell_document,
    )

    def _wrapped(request: Request) -> Response:
        inner = handler(request)
        if isinstance(inner, HTMLResponse) is False:
            return inner

        try:
            inner_body_bytes = inner._body
        except AttributeError:
            return inner

        if inner_body_bytes is None:
            inner_html = ""
        else:
            try:
                inner_html = inner_body_bytes.decode("utf-8")
            except Exception:
                return inner

        request_path = getattr(request, "path", "")
        if isinstance(request_path, str) is False:
            request_path = ""
        page_title = _resolve_admin_page_title(path=request_path)
        rtnval = render_shell_document(
            request=request,
            page_title=page_title,
            content_html=inner_html,
        )
        try:
            rtnval._status_code = inner._status_code
        except AttributeError:
            pass

        # Carry the inner response's cookies across -- the session
        # cookie re-signed by the flash drain records that queued
        # flashes were consumed; dropping it would make every flash
        # reappear on the next admin page.
        try:
            inner_cookies = inner._cookies
        except AttributeError:
            inner_cookies = None
        if inner_cookies is not None:
            for cookie_name in inner_cookies:
                rtnval._cookies[cookie_name] = inner_cookies[cookie_name]

        # Carry any extra headers too, but keep the shell render's
        # own Content-Type.
        try:
            inner_headers = inner._headers
        except AttributeError:
            inner_headers = None
        if inner_headers is not None:
            for header_name, header_value in inner_headers.items():
                if header_name.lower() == "content-type":
                    continue
                rtnval._headers[header_name] = header_value

        return rtnval

    _wrapped.__name__ = "{}_in_shell".format(
        getattr(handler, "__name__", "admin_handler")
    )
    return _wrapped


def _render(
        *, template_name: str, context: Optional[Dict[str, Any]] = None,
        status_code: int = 200
    ) -> HTMLResponse:
    """
        Convenience wrapper for ``render_template_response`` with
        the module-default jinja2 environment.
    """
    rtnval = templating.render_template_response(
        template_name=template_name,
        context=context,
        status_code=status_code,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Login-failure messaging + ``next`` threading helpers
# ---------------------------------------------------------------------------


# Adapter failure messages that are safe to surface verbatim on the
# login form. Both originate in ``security.auth.local_flow`` and are
# re-raised message-intact by
# :class:`auth_adapter.ConsumerUISecurityAdapter`:
#
# * The backoff lockout is keyed by ``(login_name, source_ip)`` and
#   records failures for nonexistent usernames too
#   (``local_flow.verify_local_credentials`` marks a failure before
#   it knows whether the user exists), so surfacing it does not
#   reveal whether the username is real.
# * "Account is not active" is deliberately NOT surfaced: the check
#   fires in ``local_flow`` before password verification, so echoing
#   it would confirm account existence (and its disabled state) to
#   anyone submitting any password for that username. Disabled
#   accounts therefore see the generic message; operators learn the
#   real state from an administrator.
#
# Every other failure keeps the generic message so bad credentials
# stay indistinguishable from unknown usernames.
_SURFACEABLE_LOGIN_FAILURE_MESSAGES: Tuple[str, ...] = (
    "Too many recent failures; try again later",
)

_GENERIC_LOGIN_FAILURE_MESSAGE: str = "Invalid username or password."


def _resolve_login_failure_message(*, error: Exception) -> str:
    """
        Map an ``authenticate()`` failure onto the user-facing
        flash message. The adapter's :class:`AuthenticationError`
        carries the modern stack's message; the rate-limit lockout
        and inactive-account messages are surfaced verbatim (see
        :data:`_SURFACEABLE_LOGIN_FAILURE_MESSAGES`), every other
        failure flattens to the generic bad-credentials message.

        :param error: Exception raised by
                      ``security_manager.authenticate``.

        :returns: The flash message to render on the login form.
    """
    try:
        from ccai.pychestrate.webservice.webinterface.blueprints.config.auth_adapter import (  # noqa: E402
            AuthenticationError,
        )
    except Exception:
        # The adapter module (and its security-stack imports) may
        # be absent in stubbed test runtimes; the generic message
        # is always safe.
        rtnval = _GENERIC_LOGIN_FAILURE_MESSAGE
        return rtnval

    if isinstance(error, AuthenticationError) is True:
        message = getattr(error, "message", "")
        if isinstance(message, str) is True:
            if message in _SURFACEABLE_LOGIN_FAILURE_MESSAGES:
                rtnval = message
                return rtnval

    rtnval = _GENERIC_LOGIN_FAILURE_MESSAGE
    return rtnval


def _resolve_safe_login_next(*, candidate: Optional[str]) -> str:
    """
        Validate a raw ``next`` candidate for embedding in the
        login form's hidden field. Returns the candidate when it
        passes the same-origin check, or an empty string when the
        candidate is missing / rejected (the template omits the
        hidden field for an empty value).

        :param candidate: Raw ``next`` value from the query string
                          or form body.

        :returns: The safe candidate or ``""``.
    """
    validator = NextValidator(fallback_target="/")
    if validator.is_safe_same_origin_target(candidate=candidate) is True:
        rtnval = candidate
        return rtnval

    rtnval = ""
    return rtnval


def _read_login_next_candidate(*, request: Request) -> Optional[str]:
    """
        Lift the raw ``next`` candidate off a login request's
        query string. Returns ``None`` when absent or when the
        request object exposes no usable ``query_params``.

        :param request: Incoming webworks request.

        :returns: Raw candidate string or ``None``.
    """
    try:
        rtnval = request.query_params.get("next", None)
    except Exception:
        rtnval = None
    return rtnval


# ---------------------------------------------------------------------------
# Handlers — login (GET + POST)
# ---------------------------------------------------------------------------


def handle_login_form(request: Request) -> Response:
    """
        ``GET /login`` -- render the login form. Drains any
        pending flash messages so the form can render them.

        When the request carries a ``?next=<target>`` parameter
        (placed there by the auth guards when an anonymous browser
        hits a protected page), the validated target is threaded
        into the template context so the form can carry it in a
        hidden field -- the POST handler reads it back from the
        form body and redirects there after a successful sign-in.

        :param request: Incoming webworks request.

        :returns: HTMLResponse with the login template, cookie
                  re-signed (drained flashes need to be persisted
                  as "consumed").
    """
    session = _read_session(request=request)
    flashes = flash.consume_flashes(session=session)

    next_candidate = _read_login_next_candidate(request=request)
    next_target = _resolve_safe_login_next(candidate=next_candidate)

    context = _build_default_template_context(
        session=session,
        request_endpoint="config.login",
        flashes=flashes,
    )
    context["next_target"] = next_target
    response = _render(
        template_name="config/login.html",
        context=context,
    )
    _attach_session_to_response(response=response, session=session)
    return response


def handle_login_submit(request: Request) -> Response:
    """
        ``POST /login`` -- authenticate via SecurityManager and
        (on success) populate the session cookie + redirect to
        the validated ``next`` target or ``/``.

        The ``next`` target is read from the form body first (the
        login form carries it in a hidden field) with the query
        string as a fallback; either way it must pass
        :class:`NextValidator` before it is honored.

        :param request: Incoming webworks request.

        :returns: RedirectResponse on success, HTMLResponse
                  re-rendering the form on failure.
    """
    form = _parse_form_or_empty(request=request)
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

    # Resolve the post-login redirect candidate. The login form
    # carries ``next`` in a hidden field (form body); direct
    # POSTs to ``/login?next=...`` fall back to the query param.
    next_candidate = form.get("next", None)
    if next_candidate is None or len(str(next_candidate)) == 0:
        next_candidate = _read_login_next_candidate(request=request)

    session = _read_session(request=request)

    if len(username) == 0 or len(password) == 0:
        flash.add_flash(
            session=session,
            message="Username and password are required.",
            category=flash.CATEGORY_ERROR,
        )
        flashes = flash.consume_flashes(session=session)
        context = _build_default_template_context(
            session=session,
            request_endpoint="config.login",
            flashes=flashes,
        )
        context["next_target"] = _resolve_safe_login_next(
            candidate=next_candidate
        )
        response = _render(
            template_name="config/login.html",
            context=context,
            status_code=400,
        )
        _attach_session_to_response(response=response, session=session)
        return response

    db_session = _resolve_db_session()
    try:
        security_manager = _build_security_manager(db_session=db_session)
        client_ip = ""
        user_agent = ""
        try:
            client_ip = request.headers.get("X-Forwarded-For", "") or ""
            user_agent = request.headers.get("User-Agent", "") or ""
        except Exception:
            client_ip = ""
            user_agent = ""

        auth_request = _build_auth_request(
            username=username,
            password=password,
            client_ip=client_ip,
            user_agent=user_agent,
        )

        try:
            auth_response = security_manager.authenticate(auth_request)
        except Exception as auth_error:
            failure_message = _resolve_login_failure_message(
                error=auth_error
            )
            flash.add_flash(
                session=session,
                message=failure_message,
                category=flash.CATEGORY_ERROR,
            )
            flashes = flash.consume_flashes(session=session)
            context = _build_default_template_context(
                session=session,
                request_endpoint="config.login",
                flashes=flashes,
            )
            context["next_target"] = _resolve_safe_login_next(
                candidate=next_candidate
            )
            response = _render(
                template_name="config/login.html",
                context=context,
                status_code=401,
            )
            _attach_session_to_response(response=response, session=session)
            return response

        # Success -- populate the session.
        session[auth_guard.SESSION_USER_ID_KEY] = auth_response.user_id
        session["username"] = auth_response.username
        session[auth_guard.SESSION_TOKEN_KEY] = auth_response.token
        session[csrf.SESSION_KEY] = auth_response.csrf_token

        # No welcome flash: the shell document the browser lands
        # on after this redirect never drains the flash queue, so
        # a queued greeting would surface minutes later on the
        # next legacy-template page instead.

        # Honor the ``next`` candidate resolved above only after
        # it passes the same-origin validator (NFR-2 of
        # 1-authentication/requirements.md). Reject paths that are
        # absolute / protocol-relative / credentialed / cross-host
        # and fall back to ``/``.
        validator = NextValidator(fallback_target="/")
        next_url = validator.resolve_safe_target(
            candidate=next_candidate, fallback="/"
        )

        response = RedirectResponse(url=next_url, status_code=303)
        _attach_session_to_response(response=response, session=session)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Handler — logout
# ---------------------------------------------------------------------------


def handle_logout(request: Request) -> Response:
    """
        ``GET /logout`` and ``POST /logout`` -- invoke
        ``SecurityManager.logout`` if a token is present, clear
        the cookie session, redirect to the login page.

        The POST path is CSRF-gated like every other
        state-changing form post in the consumer UI; the legacy
        base templates carry the token in their logout forms. The
        GET path stays ungated -- it is the convenience
        entrypoint sidebar links bind to.

        :param request: Incoming webworks request.

        :returns: RedirectResponse to /login with a "logged out"
                  flash, or a redirect back to ``/`` when a POST
                  fails the CSRF check.
    """
    session = _read_session(request=request)

    request_method = getattr(request, "method", "")
    if isinstance(request_method, str) is True:
        request_method = request_method.upper()
    else:
        request_method = ""

    if request_method == "POST":
        form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=form,
            session=session,
            fallback_url="/",
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=session
            )
            return csrf_redirect

    session_token = session.get(auth_guard.SESSION_TOKEN_KEY, None)

    if session_token is not None and len(session_token) > 0:
        db_session = _resolve_db_session()
        try:
            security_manager = _build_security_manager(db_session=db_session)
            try:
                security_manager.logout(session_token)
            except Exception:
                # Best-effort logout; the cookie clear below
                # ensures the user is logged out from the
                # browser's perspective regardless.
                pass
        finally:
            try:
                db_session.close()
            except Exception:
                pass

    # Mint a fresh empty session so the flash message rides on
    # the redirect cookie -- but the auth keys are gone.
    fresh_session: Dict[str, Any] = {}
    flash.add_flash(
        session=fresh_session,
        message="You have been logged out.",
        category=flash.CATEGORY_INFO,
    )

    response = RedirectResponse(
        url=_url_for_module.url_for("config.login"),
        status_code=303,
    )
    _attach_session_to_response(
        response=response, session=fresh_session
    )
    return response


# ---------------------------------------------------------------------------
# Handler — dashboard
# ---------------------------------------------------------------------------


def _validate_session_via_security_manager(
        *, session: Dict[str, Any]
    ) -> Optional[Tuple[str, str, str]]:
    """
        Re-validate the cookie's session_token against the
        SecurityManager's view of the session. Returns
        ``(user_id, username, csrf_token)`` on success or
        ``None`` when the token is missing / expired / revoked.

        The cookie carries the token, but the source of truth
        for "is this token still valid" is the database.

        :param session: Session dict from the cookie.

        :returns: Tuple on valid session, None on expired /
                  revoked / missing.
    """
    if auth_guard.is_authenticated(session=session) is False:
        return None

    session_token = session.get(auth_guard.SESSION_TOKEN_KEY, "")
    db_session = _resolve_db_session()
    try:
        security_manager = _build_security_manager(db_session=db_session)
        try:
            session_info = security_manager.validate_token(session_token)
        except Exception:
            session_info = None

        if session_info is None:
            return None

        rtnval = (
            session_info.user_id,
            session_info.username,
            session_info.csrf_token,
        )
        return rtnval
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _redirect_with_flash(
        *,
        session: Dict[str, Any],
        url: str,
        message: str,
        category: str = flash.CATEGORY_INFO,
        status_code: int = 303
    ) -> RedirectResponse:
    """
        Build a redirect response, queue ``message`` on the session
        as a flash, and attach the (mutated) session cookie. Used
        by handlers after a successful POST or after looking up an
        entity that isn't found.

        :param session: Session dict.
        :param url: Redirect target URL.
        :param message: Flash message to render after redirect.
        :param category: Flash category.
        :param status_code: HTTP status code (default 303 -- see
                            other after a successful POST per
                            Post/Redirect/Get).

        :returns: :class:`RedirectResponse` with the cookie
                  re-signed.
    """
    flash.add_flash(
        session=session, message=message, category=category
    )
    response = RedirectResponse(url=url, status_code=status_code)
    _attach_session_to_response(response=response, session=session)
    return response


def _require_permission_or_redirect(
        *,
        auth: _AuthResolution,
        permission: str,
        deny_redirect_url: str,
        deny_message: str = (
            "You do not have permission to access this page."
        )
    ) -> Optional[Response]:
    """
        Admin-permission gate. Builds a SecurityManager against
        the auth-resolution's open db_session, calls
        ``check_permission(user_id, permission)``, and either
        returns ``None`` (allowed -- the handler proceeds) or a
        redirect response with an error flash queued on the
        session (denied).

        On the deny path the helper attaches the (mutated) session
        cookie to the redirect response.

        :param auth: Resolution from
                     :func:`_resolve_authenticated_request`. Must
                     carry an open db_session.
        :param permission: Permission string (e.g.
                           ``"resources.manage"``).
        :param deny_redirect_url: URL to redirect to on denial.
        :param deny_message: Optional flash message on denial.

        :returns: ``None`` when the user has the permission;
                  :class:`RedirectResponse` (302) on denial. On
                  any unexpected SecurityManager failure the
                  helper treats that as denial and returns the
                  redirect.
    """
    security_manager = _build_security_manager(db_session=auth.db_session)
    try:
        has_permission = security_manager.check_permission(
            auth.user_id, permission
        )
    except Exception:
        has_permission = False

    if has_permission is True:
        return None

    flash.add_flash(
        session=auth.session,
        message=deny_message,
        category=flash.CATEGORY_ERROR,
    )
    rtnval = RedirectResponse(url=deny_redirect_url, status_code=302)
    _attach_session_to_response(response=rtnval, session=auth.session)
    return rtnval


def _build_login_url_with_next(*, request: Request) -> str:
    """
        Build the login-page URL with a percent-encoded ``next``
        query parameter carrying the original request path (and
        query string when present). Used by the auth guard so an
        unauthenticated browser hitting a protected page bounces
        through ``/login?next=<original>`` and lands back on
        the originally-requested target after a successful
        sign-in per 1-authentication Requirement 5.

        :param request: Incoming webworks request.

        :returns: Login URL with ``?next=...`` appended.
    """
    login_path = _url_for_module.url_for("config.login")

    try:
        request_path = request.path
    except Exception:
        request_path = ""

    try:
        query_string = request.query_string
    except Exception:
        query_string = ""

    if request_path is None or len(request_path) == 0:
        rtnval = login_path
        return rtnval

    if isinstance(query_string, bytes):
        try:
            query_string = query_string.decode("utf-8")
        except Exception:
            query_string = ""

    if query_string is not None and len(query_string) > 0:
        next_target = "{}?{}".format(request_path, query_string)
    else:
        next_target = request_path

    encoded_next = quote(next_target, safe="")
    rtnval = "{}?next={}".format(login_path, encoded_next)
    return rtnval


def _resolve_authenticated_request(
        *, request: Request
    ) -> _AuthResolution:
    """
        Single-call auth resolver for handlers that need to:

        * read the cookie session
        * verify the user is logged in (else redirect to login)
        * open a SQLAlchemy session
        * validate the cookie's session_token against the DB
          (else clear the session + redirect)
        * return the resolved user_id / username / csrf_token + the
          OPEN db session for the handler to use

        On the redirect paths the helper attaches the (mutated)
        session cookie to the redirect response and closes any
        intermediate DB session it opened.

        On the success path the helper hands the open DB session
        to the caller -- the caller MUST close it in a finally
        block.

        :param request: Incoming webworks request.

        :returns: :class:`_AuthResolution`. When
                  ``redirect_response`` is non-None the caller
                  returns it immediately and does no further work.
    """
    session = _read_session(request=request)

    login_url_with_next = _build_login_url_with_next(request=request)
    redirect_response = auth_guard.require_login_or_redirect(
        session=session,
        login_url=login_url_with_next,
        flash_message="Please log in to access this page.",
    )
    if redirect_response is not None:
        _attach_session_to_response(
            response=redirect_response, session=session
        )
        rtnval = _AuthResolution(redirect_response=redirect_response)
        return rtnval

    session_token = session.get(auth_guard.SESSION_TOKEN_KEY, "")
    db_session = _resolve_db_session()
    try:
        security_manager = _build_security_manager(db_session=db_session)
        try:
            session_info = security_manager.validate_token(session_token)
        except Exception:
            session_info = None
    except Exception:
        # Validation infrastructure failure -- close the DB session
        # before re-raising so we don't leak it.
        try:
            db_session.close()
        except Exception:
            pass
        raise

    if session_info is None:
        try:
            db_session.close()
        except Exception:
            pass
        # Token expired or revoked -- clear the cookie keys, flash,
        # redirect to login.
        session.clear()
        flash.add_flash(
            session=session,
            message="Session expired. Please log in again.",
            category=flash.CATEGORY_WARNING,
        )
        redirect_response = RedirectResponse(
            url=login_url_with_next,
            status_code=303,
        )
        _attach_session_to_response(
            response=redirect_response, session=session
        )
        rtnval = _AuthResolution(redirect_response=redirect_response)
        return rtnval

    # Refresh server-of-record csrf_token onto the session so any
    # subsequent POST validates against the same value the renderer
    # passed to the template. The modern adapter returns an empty
    # csrf_token (cookie is the CSRF source of truth under the
    # modern stack -- see ``auth_adapter`` module docstring); skip
    # the refresh in that case so we don't clobber the cookie's
    # CSRF.
    if (
        session_info.csrf_token is not None
        and len(session_info.csrf_token) > 0
    ):
        session[csrf.SESSION_KEY] = session_info.csrf_token
    session["username"] = session_info.username

    # Use the CSRF token already stored in the session (set during
    # login at line 731 or refreshed above at line 1095 for the
    # legacy adapter).  The modern adapter leaves session_info.csrf_token
    # empty on purpose -- the cookie holds the real value -- so reading
    # session[csrf.SESSION_KEY] is always correct for both adapters.
    resolved_csrf_token = session.get(csrf.SESSION_KEY, "")

    rtnval = _AuthResolution(
        redirect_response=None,
        session=session,
        db_session=db_session,
        user_id=session_info.user_id,
        username=session_info.username,
        csrf_token=resolved_csrf_token,
    )
    return rtnval


def handle_dashboard(request: Request) -> Response:
    """
        ``GET /config/`` and ``GET /config/dashboard`` -- render
        the dashboard for an authenticated session. Anonymous /
        expired sessions redirect to the login page with a
        flash explaining why.

        :param request: Incoming webworks request.

        :returns: HTMLResponse on success, RedirectResponse on
                  unauthenticated / expired session.
    """
    session = _read_session(request=request)

    login_url_with_next = _build_login_url_with_next(request=request)
    redirect_response = auth_guard.require_login_or_redirect(
        session=session,
        login_url=login_url_with_next,
        flash_message="Please log in to access this page.",
    )
    if redirect_response is not None:
        _attach_session_to_response(
            response=redirect_response, session=session
        )
        return redirect_response

    validated = _validate_session_via_security_manager(session=session)
    if validated is None:
        # Token expired or revoked since the cookie was issued --
        # clear the cookie keys, flash, redirect to login.
        session.clear()
        flash.add_flash(
            session=session,
            message="Session expired. Please log in again.",
            category=flash.CATEGORY_WARNING,
        )
        response = RedirectResponse(
            url=login_url_with_next,
            status_code=303,
        )
        _attach_session_to_response(response=response, session=session)
        return response

    user_id, username, csrf_token = validated
    flashes = flash.consume_flashes(session=session)

    # Refresh the session's csrf_token with the server-of-record
    # value so subsequent POSTs validate against the current value.
    # The modern adapter returns an empty csrf_token (cookie is the
    # CSRF source of truth under the modern stack); skip the
    # refresh in that case so we don't clobber the cookie's CSRF.
    if csrf_token is not None and len(csrf_token) > 0:
        session[csrf.SESSION_KEY] = csrf_token
    # Refresh the username on the session so anonymous-rendered
    # frames immediately after login pick up the freshest username.
    session["username"] = username

    context = _build_default_template_context(
        session=session,
        request_endpoint="config.dashboard",
        flashes=flashes,
        csrf_token=csrf_token,
    )
    context["user_id"] = user_id
    response = _render(
        template_name="config/dashboard.html",
        context=context,
    )
    _attach_session_to_response(response=response, session=session)
    return response


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Any] = {
    "config.login": handle_login_form,
    "config.login_submit": handle_login_submit,
    "config.logout": handle_logout,
    "config.dashboard_root": handle_dashboard,
    "config.dashboard": handle_dashboard,
    "config.admin_overview": handle_dashboard,
    "config.feature_flags": handle_dashboard,
    "config.extension_registry": handle_dashboard,
    "config.system_health": handle_dashboard,
}


def register_config_routes(*, app: Any) -> None:
    """
        Attach the config web UI routes to a webworks application
        and register their endpoint names with the url_for shim
        so templates can build links via ``url_for('config.X')``.

        Also pre-registers the URL patterns for future-PR endpoints
        (D2/D3/D4) so the D1 dashboard render does not crash on
        ``url_for('config.user_list')`` etc. before those handlers
        ship.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
    # Auth surface (unprefixed): /login + /logout.
    for endpoint_name, full_path, methods in _AUTH_ROUTE_TABLE:
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(handler)

    # Admin dashboard surface (/admin/...). Each handler is wrapped
    # so its rendered fragment is injected into the site shell's main
    # slot (PR4 task F-1 -- strategy A).
    for endpoint_name, relative_path, methods in _ADMIN_ROUTE_TABLE:
        full_path = ADMIN_PATH + relative_path
        if full_path.endswith("/") and full_path != "/":
            # Drop trailing slash so /admin (no slash) maps to
            # the dashboard-root handler; the "/" relative_path
            # becomes ADMIN_PATH alone.
            full_path = ADMIN_PATH if relative_path == "/" else full_path

        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )

        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_admin_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)

    for endpoint_name, relative_path in _FUTURE_ENDPOINT_PATTERNS:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )

    # D2 features -- users + roles. Lazy import so the auth/dashboard
    # surface in this file remains importable even if a per-feature
    # module fails to load (e.g., during a partial port).
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_users import (  # noqa: E402
        register_users_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_roles import (  # noqa: E402
        register_roles_routes,
    )
    register_users_routes(app=app)
    register_roles_routes(app=app)

    # D3 features -- variables + scopes.
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_variables import (  # noqa: E402
        register_variables_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_scopes import (  # noqa: E402
        register_scopes_routes,
    )
    register_variables_routes(app=app)
    register_scopes_routes(app=app)

    # D4 features -- secrets + sessions + audit.
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_secrets import (  # noqa: E402
        register_secrets_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_sessions import (  # noqa: E402
        register_sessions_routes,
    )
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_audit import (  # noqa: E402
        register_audit_routes,
    )
    register_secrets_routes(app=app)
    register_sessions_routes(app=app)
    register_audit_routes(app=app)

    # p19o feature -- client enrollment-token admin page.
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_enrollment import (  # noqa: E402
        register_enrollment_admin_routes,
    )
    register_enrollment_admin_routes(app=app)

    return


__all__ = [
    "ADMIN_PATH",
    "CONFIG_PATH",
    "LOGIN_PATH",
    "LOGOUT_PATH",
    "register_config_routes",
    "handle_login_form",
    "handle_login_submit",
    "handle_logout",
    "handle_dashboard",
    "_wrap_admin_handler_in_shell",
]
