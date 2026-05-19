"""
.. module:: webinterface.blueprints.config.routes_sessions
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /config/sessions
               (D4 slice -- session admin).

.. moduleauthor:: Automation Mojo LLC

The two session-admin routes ported from the legacy flask
``config_blueprint``:

* ``GET  /config/sessions``                                -- list
                                                              active sessions
                                                              with optional
                                                              ?user_id=
                                                              filter.
* ``POST /config/sessions/{session_id}/terminate``         -- terminate a
                                                              specific
                                                              session.

The sessions surface uses :class:`SecurityManager` -- the same
manager the auth + dashboard handlers route through. We expose
a separate ``_build_security_manager_for_sessions`` builder so
test patches don't accidentally collide with the routes.py auth
patch.
"""

__author__ = "Automation Mojo LLC"
__copyright__ = "Copyright 2026, Automation Mojo LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from automojo.webworks.routing.request import Request
from automojo.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from automojo.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    csrf,
    flash,
    url_for as _url_for_module,
)
from automojo.pychestrate.webservice.webinterface.blueprints.config.routes import (
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


# ---------------------------------------------------------------------------
# Lazy-import builder seam
# ---------------------------------------------------------------------------


def _build_security_manager_for_sessions(*, db_session: Any) -> Any:
    """
        Construct a :class:`SecurityManager` for the session-admin
        handlers. Pulled into its own builder (separate from the
        routes.py one) so test patches do not accidentally collide.

        :param db_session: Open SQLAlchemy session.

        :returns: SecurityManager instance.
    """
    from automojo.pychestrate.core.managers.security_manager import (  # noqa: E402
        SecurityManager,
    )
    rtnval = SecurityManager(db_session)
    return rtnval


# ---------------------------------------------------------------------------
# Helpers local to this module
# ---------------------------------------------------------------------------


def _coerce_optional_int(*, raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        return None
    return rtnval


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

        security_manager = _build_security_manager_for_sessions(
            db_session=db_session
        )
        sessions = security_manager.list_active_sessions(
            user_id=filter_user_id
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
        session_id = _coerce_optional_int(
            raw=request.path_params.get("session_id", None)
        )
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

        if session_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.session_list"),
                message="Session not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        security_manager = _build_security_manager_for_sessions(
            db_session=db_session
        )
        try:
            security_manager.terminate_session(session_id)
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
