"""
.. module:: webinterface.blueprints.config.routes_sessions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/sessions
               (D4 slice -- session admin).

.. moduleauthor:: Code Craft AI LLC

The session-admin routes served under the config blueprint:

* ``GET  /config/sessions``                                -- list
                                                              active sessions
                                                              with optional
                                                              ?user_id=
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


from dataclasses import dataclass
from datetime import datetime, timezone
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
    _wrap_admin_handler_in_shell,
)


_ROUTE_TABLE = (
    ("config.session_list", "/sessions", ("GET",)),
    (
        "config.session_terminate",
        "/sessions/{session_id}/terminate",
        ("POST",),
    ),
)


@dataclass(frozen=True)
class _SessionRow:
    """
        Template view-model for one active session. Field names match
        what ``config/sessions/list.html`` reads, mapped from the modern
        :class:`AuthSession` columns.

        :param session_id: Session UUID as a string.
        :param username: Login name of the session's user (falls back to
                         the user id when the user row is absent).
        :param created_at: When the session was opened.
        :param last_activity: When the session was last seen.
        :param expires_at: Absolute expiry timestamp.
        :param client_ip: IP fingerprint recorded for the session.
        :param user_agent: User-agent fingerprint recorded for the
                           session.
    """
    session_id: str
    username: str
    created_at: Optional[datetime]
    last_activity: Optional[datetime]
    expires_at: Optional[datetime]
    client_ip: str
    user_agent: str


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


def _list_active_sessions(
        *, db_session: Any, filter_user_id: Optional[str]
    ) -> List[_SessionRow]:
    """
        List active (non-expired) sessions from the modern
        ``auth_sessions`` table, newest first, optionally filtered by
        user id, with the owning user's login name joined in.

        :param db_session: Open SQLAlchemy session.
        :param filter_user_id: Optional user-id string to filter by.

        :returns: A list of :class:`_SessionRow` view-models.
    """
    from ccai.pychestrate.webservice.security.auth.models import (  # noqa: E402
        AuthSession,
    )
    from ccai.pychestrate.webservice.identity.users.models import (  # noqa: E402
        IdentityUser,
    )

    now = datetime.now(timezone.utc)

    query = db_session.query(AuthSession)
    if filter_user_id is not None and len(filter_user_id) > 0:
        query = query.filter(AuthSession.user_id == filter_user_id)
    all_sessions = query.all()

    active_sessions = []
    for session_row in all_sessions:
        normalized_expiry = _normalize_to_utc(
            value=session_row.expires_at, fallback=now
        )
        if session_row.expires_at is None or normalized_expiry > now:
            active_sessions.append(session_row)

    usernames_by_user_id: Dict[str, str] = {}
    user_ids = [session_row.user_id for session_row in active_sessions]
    if len(user_ids) > 0:
        user_rows = (
            db_session.query(IdentityUser)
            .filter(IdentityUser.user_id.in_(user_ids))
            .all()
        )
        for user_row in user_rows:
            usernames_by_user_id[str(user_row.user_id)] = user_row.login_name

    rows: List[_SessionRow] = []
    for session_row in active_sessions:
        user_id_str = str(session_row.user_id)
        username = usernames_by_user_id.get(user_id_str, user_id_str)
        row = _SessionRow(
            session_id=str(session_row.session_id),
            username=username,
            created_at=session_row.opened_at,
            last_activity=session_row.last_seen_at,
            expires_at=session_row.expires_at,
            client_ip=session_row.ip_fingerprint,
            user_agent=session_row.user_agent_fingerprint,
        )
        rows.append(row)

    rows.sort(
        key=lambda candidate: _normalize_to_utc(
            value=candidate.created_at, fallback=now
        ),
        reverse=True,
    )

    rtnval = rows
    return rtnval


def _terminate_session(*, db_session: Any, session_id: str) -> None:
    """
        Terminate a session by id through the modern session service
        (deletes the ``auth_sessions`` row and publishes
        ``entity.session.closed``). A no-op when the session is already
        gone.

        :param db_session: Open SQLAlchemy session.
        :param session_id: Session UUID string to terminate.

        :returns: None.
    """
    from ccai.pychestrate.webservice.security.auth import (  # noqa: E402
        session_service,
    )

    session_service.close_session(
        db_session=db_session, session_id=session_id
    )
    return


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_session_list(request: Request) -> Response:
    """
        ``GET /config/sessions`` -- list active sessions, optional
        ``?user_id=`` filter.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        filter_user_id = request.query_params.get("user_id", None) or None

        sessions = _list_active_sessions(
            db_session=db_session, filter_user_id=filter_user_id
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.session_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["sessions"] = sessions
        context["filter_user_id"] = filter_user_id
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
                db_session=db_session, session_id=session_id
            )
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
                message="Error terminating session: {}".format(str(exc)),
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
        wrapped_handler = _wrap_admin_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_sessions_routes",
    "handle_session_list",
    "handle_session_terminate",
]
