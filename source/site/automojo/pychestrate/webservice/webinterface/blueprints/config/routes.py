"""
.. module:: webinterface.blueprints.config.routes
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config (D1
               slice — auth + dashboard).

.. moduleauthor:: Automation Mojo LLC

The flask config blueprint at
``webinterface/blueprints/config/endpoints.py`` (1,355 LOC) is
being ported to webworks across multiple PRs. This first slice
(D1) lands the auth + dashboard surface end-to-end:

* ``GET /config/login`` -- render the login form.
* ``POST /config/login`` -- authenticate and redirect.
* ``POST /config/logout`` -- clear the session and redirect.
* ``GET /config/`` and ``GET /config/dashboard`` -- the
  authenticated dashboard.

The remaining 25 routes (users / roles / variables / scopes /
secrets / sessions / audit) land in PR D2/D3/D4 against the
same foundation pieces this module exercises.

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
  ``require_login`` / ``enforce_csrf`` shape that mirrors the
  flask ``@login_required`` / ``@validate_csrf`` decorators.
* :mod:`webinterface.foundation.templating` for the
  jinja2 render-to-HTMLResponse helper.
* :mod:`webinterface.foundation.url_for` for the template
  link-builder.

Auth backend
------------

The actual authentication is delegated to
:class:`automojo.pychestrate.core.managers.security_manager.SecurityManager`
-- the same auth engine the flask blueprint used. Webworks
handlers open a SQLAlchemy session per request via the bootstrap-
populated ``SITE_SHARED_GLOBALS.DATABASE_SESSION_FACTORY`` and
hand it to :class:`SecurityManager`. The cookie session merely
carries the auth token between requests; the source of truth for
"is this token still valid" lives in the database.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from automojo.pychestrate.webservice.metadata import SITE_SHARED_GLOBALS
from automojo.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    cookie_session,
    csrf,
    flash,
    templating,
    url_for as _url_for_module,
)


CONFIG_PATH = "/config"


# ---------------------------------------------------------------------------
# Endpoint registrations -- (endpoint_name, pattern_relative_to_base, methods)
#
# The blueprint owns this list so the per-PR additions are
# discoverable in one place. Each new route in D2/D3/D4 appends
# its tuple here AND its handler below.
# ---------------------------------------------------------------------------


_ROUTE_TABLE = (
    ("config.login", "/login", ("GET",)),
    ("config.login_submit", "/login", ("POST",)),
    ("config.logout", "/logout", ("POST",)),
    ("config.dashboard_root", "/", ("GET",)),
    ("config.dashboard", "/dashboard", ("GET",)),
)


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
        ``role_ids[]`` / ``permission_ids[]`` shape the legacy
        flask templates rely on.

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
        parsed multi-value form dict. Lets the existing flask-era
        templates -- which call ``form_data.getlist('role_ids')``
        on form-redirect renders -- port unchanged. Built once per
        handler from :func:`_parse_form_multi` output.

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
            flask MultiDict semantics).

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
# whose werkzeug-derived password helpers are not part of the
# test runtime's dep set.
# ---------------------------------------------------------------------------


def _build_security_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`SecurityManager` against the supplied
        SQLAlchemy session. Lazy-imports the class so this module
        does not pull the manager (and its werkzeug dep) at import
        time.

        :param db_session: Open SQLAlchemy session.

        :returns: SecurityManager instance.
    """
    from automojo.pychestrate.core.managers.security_manager import (  # noqa: E402
        SecurityManager,
    )
    rtnval = SecurityManager(db_session)
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
    from automojo.pychestrate.core.managers.security_manager import (  # noqa: E402
        AuthRequest,
    )
    rtnval = AuthRequest(
        username=username,
        password=password,
        client_ip=client_ip,
        user_agent=user_agent,
    )
    return rtnval


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
# Handlers — login (GET + POST)
# ---------------------------------------------------------------------------


def handle_login_form(request: Request) -> Response:
    """
        ``GET /config/login`` -- render the login form. Drains
        any pending flash messages so the form can render them.

        :param request: Incoming webworks request.

        :returns: HTMLResponse with the login template, cookie
                  re-signed (drained flashes need to be persisted
                  as "consumed").
    """
    session = _read_session(request=request)
    flashes = flash.consume_flashes(session=session)

    context = _build_default_template_context(
        session=session,
        request_endpoint="config.login",
        flashes=flashes,
    )
    response = _render(
        template_name="config/login.html",
        context=context,
    )
    _attach_session_to_response(response=response, session=session)
    return response


def handle_login_submit(request: Request) -> Response:
    """
        ``POST /config/login`` -- authenticate via SecurityManager
        and (on success) populate the session cookie + redirect to
        either the ``next`` query param or the dashboard.

        :param request: Incoming webworks request.

        :returns: RedirectResponse on success, HTMLResponse
                  re-rendering the form on failure.
    """
    form = _parse_form_or_empty(request=request)
    username = str(form.get("username", "")).strip()
    password = str(form.get("password", ""))

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
        except Exception:
            flash.add_flash(
                session=session,
                message="Invalid username or password.",
                category=flash.CATEGORY_ERROR,
            )
            flashes = flash.consume_flashes(session=session)
            context = _build_default_template_context(
                session=session,
                request_endpoint="config.login",
                flashes=flashes,
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

        flash.add_flash(
            session=session,
            message="Welcome, {}!".format(auth_response.username),
            category=flash.CATEGORY_SUCCESS,
        )

        next_url = request.query_params.get("next", None)
        if next_url is None or len(next_url) == 0:
            next_url = _url_for_module.url_for("config.dashboard")

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
        ``POST /config/logout`` -- invoke
        ``SecurityManager.logout`` if a token is present, clear
        the cookie session, redirect to the login page.

        :param request: Incoming webworks request.

        :returns: RedirectResponse to /config/login with a
                  "logged out" flash.
    """
    session = _read_session(request=request)
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

        Mirrors the flask ``@login_required`` decorator's flow:
        the cookie carries the token, but the source of truth
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
        Mirror the legacy flask ``@admin_required`` decorator's
        check: build a SecurityManager against the auth-resolution's
        open db_session, call ``check_permission(user_id,
        permission)``, and either return ``None`` (allowed -- the
        handler proceeds) or a redirect response with an error
        flash queued on the session (denied).

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

    redirect_response = auth_guard.require_login_or_redirect(
        session=session,
        login_url=_url_for_module.url_for("config.login"),
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
            url=_url_for_module.url_for("config.login"),
            status_code=303,
        )
        _attach_session_to_response(
            response=redirect_response, session=session
        )
        rtnval = _AuthResolution(redirect_response=redirect_response)
        return rtnval

    # Refresh server-of-record csrf_token onto the session so any
    # subsequent POST validates against the same value the renderer
    # passed to the template.
    session[csrf.SESSION_KEY] = session_info.csrf_token
    session["username"] = session_info.username

    rtnval = _AuthResolution(
        redirect_response=None,
        session=session,
        db_session=db_session,
        user_id=session_info.user_id,
        username=session_info.username,
        csrf_token=session_info.csrf_token,
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

    redirect_response = auth_guard.require_login_or_redirect(
        session=session,
        login_url=_url_for_module.url_for("config.login"),
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
            url=_url_for_module.url_for("config.login"),
            status_code=303,
        )
        _attach_session_to_response(response=response, session=session)
        return response

    user_id, username, csrf_token = validated
    flashes = flash.consume_flashes(session=session)

    # Refresh the session's csrf_token with the server-of-record
    # value so subsequent POSTs validate against the current value.
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
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = CONFIG_PATH + relative_path
        if full_path.endswith("/") and full_path != "/":
            # Drop trailing slash to keep the / and /dashboard
            # routes distinct after CONFIG_PATH concatenation.
            # The "/" relative_path becomes CONFIG_PATH alone.
            full_path = CONFIG_PATH if relative_path == "/" else full_path

        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )

        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(handler)

    for endpoint_name, relative_path in _FUTURE_ENDPOINT_PATTERNS:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )

    # D2 features -- users + roles. Lazy import so the auth/dashboard
    # surface in this file remains importable even if a per-feature
    # module fails to load (e.g., during a partial port).
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes_users import (  # noqa: E402
        register_users_routes,
    )
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes_roles import (  # noqa: E402
        register_roles_routes,
    )
    register_users_routes(app=app)
    register_roles_routes(app=app)

    # D3 features -- variables + scopes.
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes_variables import (  # noqa: E402
        register_variables_routes,
    )
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes_scopes import (  # noqa: E402
        register_scopes_routes,
    )
    register_variables_routes(app=app)
    register_scopes_routes(app=app)

    # D4 features -- secrets + sessions + audit.
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes_secrets import (  # noqa: E402
        register_secrets_routes,
    )
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes_sessions import (  # noqa: E402
        register_sessions_routes,
    )
    from automojo.pychestrate.webservice.webinterface.blueprints.config.routes_audit import (  # noqa: E402
        register_audit_routes,
    )
    register_secrets_routes(app=app)
    register_sessions_routes(app=app)
    register_audit_routes(app=app)

    return


__all__ = [
    "CONFIG_PATH",
    "register_config_routes",
    "handle_login_form",
    "handle_login_submit",
    "handle_logout",
    "handle_dashboard",
]
