"""
.. module:: webinterface.blueprints.config.routes_sessions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/sessions
               (D4 slice -- session admin).

.. moduleauthor:: Code Craft AI LLC

The session-admin routes served under the config blueprint:

* ``GET  /config/sessions``                                -- paginated list
                                                              of active
                                                              sessions with
                                                              optional
                                                              ?username=
                                                              filter.
* ``POST /config/sessions/{session_id}/terminate``         -- terminate a
                                                              specific
                                                              session.

The sessions surface reads the modern ``auth_sessions`` table (the same
table the login flow + ``PychestrateSessionMiddleware`` resolve against)
and terminates through :func:`session_service.close_session`. The legacy
``SecurityManager`` -- which read the separate, now-disused ``sessions``
table -- has been retired. The data-access work lives behind the local
seam functions :func:`_list_active_sessions` / :func:`_terminate_session`
so tests can patch them without colliding with the routes.py auth patch.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
    _require_admin_permission_for,
    _wrap_admin_handler_in_shell,
)


_module_logger = logging.getLogger(__name__)


_ROUTE_TABLE = (
    ("config.session_list", "/sessions", ("GET",)),
    (
        "config.session_terminate",
        "/sessions/{session_id}/terminate",
        ("POST",),
    ),
)

# Permission each route enforces server-side (see
# ``routes._require_admin_permission_for``). Sign-in sessions.
_ROUTE_PERMISSIONS = {
    "config.session_list": "system:auth.read",
    "config.session_terminate": "system:auth.admin",
}


@dataclass(frozen=True)
class _SessionRow:
    """
        Template view-model for one active session. Field names match
        what ``config/sessions/list.html`` reads, mapped from the modern
        :class:`AuthSession` row and its :class:`AuthSessionClient`.

        :param session_id: Session UUID as a string.
        :param username: Login name of the session's user (falls back to
                         the user id when the user row is absent).
        :param created_at: When the session was opened.
        :param last_activity: When the session was last seen.
        :param expires_at: When the session ends if nothing else
                           happens: the earlier of its absolute expiry
                           and its idle deadline.
        :param client_ip: The client address recorded at sign-in (""
                          when it was not recorded).
        :param user_agent: Readable browser / OS summary ("" when not
                           recorded).
        :param user_id: The session's user id.
        :param user_agent_full: The full User-Agent header, for a
                                tooltip.
        :param is_current: The session making this request.
        :param created_ago: ``created_at`` relative to now ("2 h ago").
        :param last_activity_ago: ``last_activity`` relative to now.
        :param expires_in: ``expires_at`` relative to now ("in 27 min").
    """
    session_id: str
    username: str
    created_at: Optional[datetime]
    last_activity: Optional[datetime]
    expires_at: Optional[datetime]
    client_ip: str
    user_agent: str
    user_id: str = ""
    user_agent_full: str = ""
    is_current: bool = False
    created_ago: str = ""
    last_activity_ago: str = ""
    expires_in: str = ""


@dataclass(frozen=True)
class _SessionPage:
    """
        One page of active sessions plus the pre-pagination total,
        so the list handler can render windowed pagination
        controls.

        :param rows: The page's session view-models, newest first.
        :param total: Total active sessions matching the filter.
    """
    rows: List[_SessionRow] = field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Data-access seams (modern auth_sessions stack)
# ---------------------------------------------------------------------------


def _normalize_to_utc(*, value: Optional[datetime], fallback: datetime) -> datetime:
    """
        Return a timezone-aware UTC datetime for safe comparison /
        sorting. Naive values (as SQLite returns) are assumed UTC; a
        ``None`` value resolves to ``fallback``.

        :param value: The datetime to normalize.
        :param fallback: Value to use when ``value`` is None.

        :returns: A timezone-aware datetime.
    """
    if value is None:
        return fallback
    if value.tzinfo is None:
        rtnval = value.replace(tzinfo=timezone.utc)
        return rtnval
    rtnval = value
    return rtnval


def describe_relative_time(*, value: Optional[datetime], now: datetime) -> str:
    """
        ``value`` relative to ``now`` in words short enough for a table
        cell: "just now", "4 min ago", "2 h 5 min ago", "in 27 min",
        "3 days ago".

        :param value: The moment to describe (naive values are UTC).
        :param now: The reference moment.

        :returns: The description ("" when ``value`` is None).
    """
    if value is None:
        return ""
    moment = _normalize_to_utc(value=value, fallback=now)
    seconds = int(round((moment - now).total_seconds()))
    future = seconds > 0
    remaining = abs(seconds)
    if remaining < 60:
        rtnval = "in under a minute" if future is True else "just now"
        return rtnval
    minutes = remaining // 60
    if minutes < 60:
        amount = "{} min".format(minutes)
    elif minutes < 48 * 60:
        hours, minutes_left = divmod(minutes, 60)
        amount = "{} h".format(hours)
        if minutes_left > 0:
            amount = "{} h {} min".format(hours, minutes_left)
    else:
        amount = "{} days".format(minutes // (24 * 60))
    rtnval = "in {}".format(amount) if future is True else "{} ago".format(amount)
    return rtnval


def session_idle_deadline(*, session_row: Any, fallback: datetime) -> Optional[datetime]:
    """
        When a session ends for inactivity: ``last_seen_at`` plus its
        idle timeout (None when either is missing).

        :param session_row: The :class:`AuthSession` row.
        :param fallback: Value used when ``last_seen_at`` is missing.

        :returns: Aware UTC datetime or None.
    """
    if session_row.idle_timeout_seconds is None or session_row.last_seen_at is None:
        return None
    last_seen = _normalize_to_utc(value=session_row.last_seen_at, fallback=fallback)
    rtnval = last_seen + timedelta(seconds=int(session_row.idle_timeout_seconds))
    return rtnval


def session_effective_expiry(*, session_row: Any, now: datetime) -> datetime:
    """
        The earlier of a session's absolute expiry and its idle deadline
        -- when it stops working if nothing else happens.

        :param session_row: The :class:`AuthSession` row.
        :param now: Evaluation time (fallback for missing values).

        :returns: Aware UTC datetime.
    """
    absolute = _normalize_to_utc(value=session_row.expires_at, fallback=now)
    idle = session_idle_deadline(session_row=session_row, fallback=now)
    if idle is not None and idle < absolute:
        return idle
    return absolute


def _list_active_sessions(
        *,
        db_session: Any,
        filter_username: Optional[str],
        offset: int = 0,
        limit: int = 20,
        current_session_id: Optional[str] = None,
        now: Optional[datetime] = None
    ) -> _SessionPage:
    """
        List one page of active sessions from the modern
        ``auth_sessions`` table, grouped by user (users sorted by login
        name, each user's sessions most recently active first),
        optionally filtered by the owning user's login name.

        A session is active only while both its absolute expiry and its
        idle deadline (``last_seen_at`` + ``idle_timeout_seconds``) are
        in the future -- the same rule ``session_service.resolve_session``
        applies. The page used to list idle-expired sessions as active.

        The username filter resolves against
        ``identity_users.login_name`` server-side. An unknown username
        yields an empty page rather than an error.

        Expiry filtering happens in Python (not SQL) because SQLite
        returns naive datetimes that cannot be compared to an aware
        "now" inside the query; :func:`_normalize_to_utc` handles
        that normalization per row. Pagination is applied after the
        filter so page boundaries stay stable.

        :param db_session: Open SQLAlchemy session.
        :param filter_username: Optional login name to filter by.
        :param offset: Rows to skip (post-filter).
        :param limit: Maximum rows to return.
        :param current_session_id: The viewer's own session, marked.
        :param now: Evaluation time (defaults to now).

        :returns: A :class:`_SessionPage` with the page's rows and
                  the filtered total.
    """
    from ccai.pychestrate.webservice.security.auth.client_address import (  # noqa: E402
        describe_user_agent,
    )
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthSession,
        AuthSessionClient,
    )
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityUser,
    )

    if now is None:
        now = datetime.now(timezone.utc)

    query = db_session.query(AuthSession)

    if filter_username is not None and len(filter_username) > 0:
        matched_user = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.login_name == filter_username)
            .first()
        )
        if matched_user is None:
            rtnval = _SessionPage(rows=[], total=0)
            return rtnval
        query = query.filter(
            AuthSession.user_id == matched_user.user_id
        )

    all_sessions = query.all()

    active_sessions = []
    for session_row in all_sessions:
        if session_effective_expiry(session_row=session_row, now=now) > now:
            active_sessions.append(session_row)

    usernames_by_user_id: Dict[str, str] = {}
    user_ids = list({session_row.user_id for session_row in active_sessions})
    if len(user_ids) > 0:
        user_rows = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.user_id.in_(user_ids))
            .all()
        )
        for user_row in user_rows:
            usernames_by_user_id[str(user_row.user_id)] = user_row.login_name

    def _group_order(candidate: Any) -> Any:
        user_id_text = str(candidate.user_id)
        username = usernames_by_user_id.get(user_id_text, user_id_text)
        last_seen = _normalize_to_utc(value=candidate.last_seen_at, fallback=now)
        return (username.lower(), -last_seen.timestamp())

    active_sessions.sort(key=_group_order)

    total = len(active_sessions)
    page_sessions = active_sessions[offset:offset + limit]

    clients_by_session_id: Dict[str, Any] = {}
    page_ids = [session_row.session_id for session_row in page_sessions]
    if len(page_ids) > 0:
        client_rows = (
            db_session.query(AuthSessionClient)
            .filter(AuthSessionClient.session_id.in_(page_ids))
            .all()
        )
        for client_row in client_rows:
            clients_by_session_id[str(client_row.session_id)] = client_row

    rows: List[_SessionRow] = []
    for session_row in page_sessions:
        user_id_str = str(session_row.user_id)
        session_id_str = str(session_row.session_id)
        username = usernames_by_user_id.get(user_id_str, user_id_str)
        client_row = clients_by_session_id.get(session_id_str, None)
        client_address = ""
        user_agent_full = ""
        if client_row is not None:
            client_address = client_row.client_address or ""
            user_agent_full = client_row.user_agent or ""
        expires_at = session_effective_expiry(session_row=session_row, now=now)
        row = _SessionRow(
            session_id=session_id_str,
            username=username,
            created_at=session_row.opened_at,
            last_activity=session_row.last_seen_at,
            expires_at=expires_at,
            client_ip=client_address,
            user_agent=describe_user_agent(user_agent=user_agent_full),
            user_id=user_id_str,
            user_agent_full=user_agent_full,
            is_current=(
                current_session_id is not None
                and session_id_str == str(current_session_id)
            ),
            created_ago=describe_relative_time(value=session_row.opened_at, now=now),
            last_activity_ago=describe_relative_time(value=session_row.last_seen_at, now=now),
            expires_in=describe_relative_time(value=expires_at, now=now),
        )
        rows.append(row)

    rtnval = _SessionPage(rows=rows, total=total)
    return rtnval


def _terminate_session(
        *,
        db_session: Any,
        session_id: str,
        actor_user_id: Optional[str] = None
    ) -> None:
    """
        Terminate a session by id through the modern session service
        (deletes the ``auth_sessions`` row and publishes
        ``entity.session.closed``, which the audit log records under
        the terminating administrator). A no-op when the session is
        already gone.

        :param db_session: Open SQLAlchemy session.
        :param session_id: Session UUID string to terminate.
        :param actor_user_id: The administrator ending the session.

        :returns: None.
    """
    from ccai.pychestrate.webservice.security.auth import (  # noqa: E402
        session_service,
    )

    session_service.close_session(
        db_session=db_session,
        session_id=session_id,
        reason="admin_terminated",
        actor_user_id=actor_user_id,
    )
    return


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _session_lifetimes() -> tuple:
    """
        The sign-in session idle timeout (minutes) and maximum lifetime
        (hours) the web sign-in uses, for the page's explanation.

        :returns: ``(idle_minutes, lifetime_hours)``.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        auth_adapter,
    )
    idle_minutes = int(auth_adapter._DEFAULT_SESSION_IDLE_TIMEOUT_SECONDS // 60)
    lifetime_hours = int(auth_adapter._DEFAULT_SESSION_MAX_LIFETIME_SECONDS // 3600)
    rtnval = (idle_minutes, lifetime_hours)
    return rtnval


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 20
    ) -> Dict[str, Any]:
    raw_page = request.query_params.get("page", "1") or "1"
    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = 1
    if page < 1:
        page = 1

    raw_per_page = (
        request.query_params.get("per_page", str(default_per_page))
        or str(default_per_page)
    )
    try:
        per_page = int(raw_per_page)
    except (TypeError, ValueError):
        per_page = default_per_page
    if per_page < 1:
        per_page = default_per_page

    rtnval = {"page": page, "per_page": per_page}
    return rtnval


def _describe_terminate_failure(*, exc: Exception) -> str:
    """
        Build the operator-facing flash message for a failed
        session termination. :class:`ValueError` messages are
        curated and surfaced verbatim; anything else is logged
        server-side (with traceback) and replaced by a generic
        message so raw internal exception text never reaches the
        browser.

        :param exc: The exception raised by the termination.

        :returns: Flash message string.
    """
    if isinstance(exc, ValueError) is True:
        rtnval = "Error terminating session: {}".format(str(exc))
        return rtnval

    _module_logger.exception(
        "Unexpected error while terminating session."
    )
    rtnval = (
        "Error terminating session: an unexpected internal error"
        " occurred. The details have been logged."
    )
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_session_list(request: Request) -> Response:
    """
        ``GET /config/sessions`` -- paginated list of active
        sessions, optional ``?username=`` filter (login name; the
        table shows usernames so the filter matches on them too).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        filter_username = (
            request.query_params.get("username", None) or None
        )

        # The cookie's session_token is the AuthSession.session_id
        # (see auth_adapter) -- the template uses it to mark "This
        # session" and warn before the operator terminates it.
        current_session_id = str(
            auth.session.get("session_token", "")
        )

        session_page = _list_active_sessions(
            db_session=db_session,
            filter_username=filter_username,
            offset=offset,
            limit=params["per_page"],
            current_session_id=current_session_id,
        )
        total = session_page.total
        total_pages = (total + params["per_page"] - 1) // params["per_page"]

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.session_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["sessions"] = session_page.rows
        context["idle_timeout_minutes"], context["max_lifetime_hours"] = _session_lifetimes()
        context["filter_username"] = filter_username
        context["current_session_id"] = current_session_id
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total"] = total
        context["total_pages"] = total_pages
        response = _render(
            template_name="config/sessions/list.html",
            context=context,
        )
        _attach_session_to_response(
            response=response, session=auth.session
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_session_terminate(request: Request) -> Response:
    """
        ``POST /config/sessions/{session_id}/terminate`` --
        terminate a session, redirect to the list.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        session_id = request.path_params.get("session_id", None)
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.session_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if session_id is None or len(session_id) == 0:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.session_list"),
                message="Session not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        try:
            _terminate_session(
                db_session=db_session,
                session_id=session_id,
                actor_user_id=auth.user_id,
            )
            current_session_id = str(auth.session.get("session_token", ""))
            if session_id == current_session_id:
                # The operator ended their own session: the next
                # request would bounce with "Session expired", so send
                # them to the sign-in page with the true story instead.
                fresh_session: Dict[str, Any] = {}
                response = _redirect_with_flash(
                    session=fresh_session,
                    url=_url_for_module.url_for("config.login"),
                    message="You signed out of this session.",
                    category=flash.CATEGORY_INFO,
                )
                return response
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.session_list"),
                message="Session terminated successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.session_list"),
                message=_describe_terminate_failure(exc=exc),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "config.session_list": handle_session_list,
    "config.session_terminate": handle_session_terminate,
}


def register_sessions_routes(*, app: Any) -> None:
    """
        Attach the session-admin routes to a webworks app and
        register their endpoint names with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _require_admin_permission_for(
            _wrap_admin_handler_in_shell(handler),
            permission=_ROUTE_PERMISSIONS[endpoint_name],
        )
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_sessions_routes",
    "handle_session_list",
    "handle_session_terminate",
]
