"""
.. module:: webinterface.blueprints.config.routes_ui_profile
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native admin page for the deployment UI profile
               (9-ui-profiles -- which automation surfaces the shell
               presents by default).

.. moduleauthor:: Code Craft AI LLC

* ``GET  /admin/ui-profile``  -- one checkbox per surface, pre-checked
                                 from the deployment setting, with the
                                 count of navigation entries each
                                 surface governs.
* ``POST /admin/ui-profile``  -- save the selection
                                 (``system:ui.profile.manage``).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import Response

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
    _wrap_admin_handler_in_shell,
)
from ccai.pychestrate.webservice.webinterface.site_shell import ui_profile as _ui_profile


UI_PROFILE_MANAGE_PERMISSION: str = "system:ui.profile.manage"

_ROUTE_TABLE = (
    ("config.ui_profile", "/ui-profile", ("GET", "POST")),
)


def _governed_entry_counts() -> Dict[str, int]:
    """
        How many navigation entries each surface governs.
    """
    from ccai.pychestrate.webservice.webinterface.site_shell.nav_manifest import (  # noqa: E402
        governed_entry_counts,
    )
    rtnval = governed_entry_counts()
    return rtnval


def _surface_rows(*, deployment: Any, counts: Dict[str, int]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for surface in _ui_profile.SURFACE_ORDER:
        rows.append({
            "surface": surface.value,
            "label": _ui_profile.SURFACE_DISPLAY[surface],
            "description": _ui_profile.SURFACE_DESCRIPTIONS[surface],
            "enabled": surface in deployment,
            "entry_count": int(counts.get(surface.value, 0)),
        })
    return rows


def _render_page(*, auth: Any, deployment: Any, status_code: int = 200) -> Response:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="config.ui_profile",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["surfaces"] = _surface_rows(deployment=deployment, counts=_governed_entry_counts())
    context["variable_name"] = _ui_profile.DEPLOYMENT_VARIABLE_NAME
    context["enabled_count"] = len(deployment)
    context["surface_total"] = len(_ui_profile.SURFACE_ORDER)
    response = _render(template_name="config/ui_profile.html", context=context, status_code=status_code)
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_ui_profile(request: Request) -> Response:
    """
        ``GET|POST /admin/ui-profile``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny_response = _require_permission_or_redirect(
            auth=auth,
            permission=UI_PROFILE_MANAGE_PERMISSION,
            deny_redirect_url=_url_for_module.url_for("config.dashboard"),
            deny_message="You do not have permission to change the UI profile.",
        )
        if deny_response is not None:
            return deny_response

        if request.method.upper() == "GET":
            deployment = _ui_profile.resolve_deployment_surfaces(db_session=db_session, use_cache=False)
            return _render_page(auth=auth, deployment=deployment)

        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.ui_profile"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        selected = list(multi_form.get("surfaces", []) or [])
        if len(selected) == 0 and "surfaces" in single_form:
            selected = [single_form["surfaces"]]
        try:
            saved = _ui_profile.set_deployment_surfaces(
                db_session=db_session, surfaces=selected, actor_id=auth.user_id,
            )
        except ValueError as exc:
            flash.add_flash(session=auth.session, message=str(exc), category=flash.CATEGORY_ERROR)
            deployment = _ui_profile.resolve_deployment_surfaces(db_session=db_session, use_cache=False)
            return _render_page(auth=auth, deployment=deployment, status_code=400)
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message="Error saving the UI profile: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            deployment = _ui_profile.resolve_deployment_surfaces(db_session=db_session, use_cache=False)
            return _render_page(auth=auth, deployment=deployment, status_code=500)

        labels = [_ui_profile.SURFACE_DISPLAY[s] for s in _ui_profile.SURFACE_ORDER if s in saved]
        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.ui_profile"),
            message="UI profile saved. Visible surfaces: {}.".format(", ".join(labels)),
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "config.ui_profile": handle_ui_profile,
}


def register_ui_profile_routes(*, app: Any) -> None:
    """
        Attach the UI-profile admin route to a webworks app.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(endpoint=endpoint_name, pattern=full_path)
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_admin_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_ui_profile_routes",
    "handle_ui_profile",
    "UI_PROFILE_MANAGE_PERMISSION",
]
