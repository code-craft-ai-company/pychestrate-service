"""
.. module:: webinterface.blueprints.config.routes_account
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Per-user account preferences (9-ui-profiles M2).

.. moduleauthor:: Code Craft AI LLC

* ``GET  /account/preferences``        -- the surfaces the deployment
                                          allows, pre-checked from the
                                          user's effective set.
* ``POST /account/preferences``        -- save the override.
* ``POST /account/preferences/reset``  -- delete the override ("Use
                                          deployment default").
* ``GET  /account/password``           -- the change-password form.
* ``POST /account/password``           -- change the signed-in user's
                                          own password (audit ADM-04):
                                          the current password is
                                          checked, the shared password
                                          policy applies, and the
                                          user's other sessions end.

Any authenticated user may edit their own preferences and change their
own password; there is no admin permission gate.
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
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
    _wrap_admin_handler_in_shell,
)
from ccai.pychestrate.webservice.security.auth.password_policy import (
    PasswordPolicyError,
    password_policy_template_context,
)
from ccai.pychestrate.webservice.webinterface.site_shell import ui_profile as _ui_profile


ACCOUNT_PATH: str = "/account"

_ROUTE_TABLE = (
    ("config.account_preferences", "/preferences", ("GET", "POST")),
    ("config.account_preferences_reset", "/preferences/reset", ("POST",)),
    ("config.account_password", "/password", ("GET", "POST")),
)


def _surface_rows(profile: Any) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for surface in _ui_profile.SURFACE_ORDER:
        if surface not in profile.deployment_surfaces:
            continue
        rows.append({
            "surface": surface.value,
            "label": _ui_profile.SURFACE_DISPLAY[surface],
            "description": _ui_profile.SURFACE_DESCRIPTIONS[surface],
            "enabled": surface in profile.effective_surfaces,
        })
    return rows


def _render_page(*, auth: Any, status_code: int = 200) -> Response:
    profile = _ui_profile.resolve_profile(db_session=auth.db_session, user_id=auth.user_id)
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="config.account_preferences",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["surfaces"] = _surface_rows(profile)
    context["has_override"] = profile.override_surfaces is not None
    context["override_reset"] = profile.override_reset
    context["hidden_labels"] = [
        _ui_profile.SURFACE_DISPLAY[s] for s in _ui_profile.SURFACE_ORDER
        if s not in profile.deployment_surfaces
    ]
    response = _render(
        template_name="config/account_preferences.html", context=context, status_code=status_code,
    )
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_account_preferences(request: Request) -> Response:
    """
        ``GET|POST /account/preferences``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        if request.method.upper() == "GET":
            return _render_page(auth=auth)

        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.account_preferences"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        selected = list(multi_form.get("surfaces", []) or [])
        if len(selected) == 0 and "surfaces" in single_form:
            selected = [single_form["surfaces"]]
        try:
            saved = _ui_profile.set_user_override(
                db_session=db_session, user_id=auth.user_id, surfaces=selected,
            )
        except ValueError as exc:
            flash.add_flash(session=auth.session, message=str(exc), category=flash.CATEGORY_ERROR)
            return _render_page(auth=auth, status_code=400)
        labels = [_ui_profile.SURFACE_DISPLAY[s] for s in _ui_profile.SURFACE_ORDER if s in saved]
        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.account_preferences"),
            message="Preferences saved. You will see: {}.".format(", ".join(labels)),
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_account_preferences_reset(request: Request) -> Response:
    """
        ``POST /account/preferences/reset``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.account_preferences"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect
        _ui_profile.clear_user_override(db_session=db_session, user_id=auth.user_id)
        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.account_preferences"),
            message="Preferences reset to the deployment default.",
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _password_lifecycle() -> Any:
    """
        The password lifecycle service module. Lazy-import seam.
    """
    from ccai.pychestrate.webservice.security.auth import (  # noqa: E402
        password_lifecycle,
    )
    return password_lifecycle


def _render_password_page(
        *,
        auth: Any,
        problems: List[str],
        status_code: int = 200
    ) -> Response:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="config.account_password",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context.update(password_policy_template_context())
    context["problems"] = problems
    context["login_name"] = auth.username
    response = _render(
        template_name="config/account_password.html", context=context, status_code=status_code,
    )
    response._headers["Cache-Control"] = "no-store"
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_account_password(request: Request) -> Response:
    """
        ``GET|POST /account/password`` -- change the signed-in user's
        own password.

        :param request: Incoming webworks request.

        :returns: The form (re-rendered with the problems on failure) or
                  a redirect back to it with a success message.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        if request.method.upper() == "GET":
            return _render_password_page(auth=auth, problems=[])

        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.account_password"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        current_password = str(single_form.get("current_password", ""))
        new_password = str(single_form.get("password", ""))
        confirm = str(single_form.get("password_confirm", ""))
        if new_password != confirm:
            return _render_password_page(
                auth=auth, problems=["The new passwords do not match."], status_code=400,
            )

        lifecycle = _password_lifecycle()
        from ccai.pychestrate.webservice.security.auth.client_address import (  # noqa: E402
            resolve_client_address,
        )
        client_ip = resolve_client_address(request=request)
        try:
            lifecycle.change_own_password(
                db_session=db_session,
                user_id=auth.user_id,
                current_password=current_password,
                new_password=new_password,
                keep_session_id=str(auth.session.get(auth_guard.SESSION_TOKEN_KEY, "")),
                source_ip=client_ip,
            )
            db_session.commit()
        except PasswordPolicyError as exc:
            db_session.rollback()
            return _render_password_page(auth=auth, problems=list(exc.problems), status_code=400)
        except lifecycle.PasswordLifecycleError as exc:
            db_session.rollback()
            return _render_password_page(auth=auth, problems=[exc.message], status_code=400)

        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.account_password"),
            message="Your password was changed. Your other sessions were signed out.",
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "config.account_preferences": handle_account_preferences,
    "config.account_preferences_reset": handle_account_preferences_reset,
    "config.account_password": handle_account_password,
}


def register_account_routes(*, app: Any) -> None:
    """
        Attach the account preference routes to a webworks app.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = ACCOUNT_PATH + relative_path
        _url_for_module.register_endpoint(endpoint=endpoint_name, pattern=full_path)
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_admin_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_account_routes",
    "handle_account_preferences",
    "handle_account_preferences_reset",
    "handle_account_password",
    "ACCOUNT_PATH",
]
