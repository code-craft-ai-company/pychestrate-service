"""
.. module:: webinterface.blueprints.resources.routes_tags
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /resources/tags
               (E4 slice -- tag list).

.. moduleauthor:: Code Craft AI LLC

The tag routes served under the resources blueprint:

* ``GET  /resources/tags``                  -- list every tag known to
                                               the ResourceManager.
* ``POST /resources/tags/create``           -- make a tag (manager).
* ``GET|POST /resources/tags/{id}/edit``    -- rename a tag or change
                                               its description (manager).
* ``POST /resources/tags/{id}/delete``      -- delete a tag; resources
                                               that carried it stay
                                               (manager).

Tags used to exist only once something had been tagged with them, so
the page and the resource forms could not make one.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import logging

from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    flash,
    form_errors,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.resources.routes import (
    RESOURCES_MAX_PER_PAGE,
    RESOURCES_PATH,
    _ADMIN_PERMISSION,
    _denial_message,
    _resources_permission_flags,
    _wrap_resources_handler_in_shell,
    _build_page_window,
    _calculate_total_pages,
)


_LOGGER = logging.getLogger(__name__)

_ROUTE_TABLE = (
    ("resources.tag_list", "/tags", ("GET",)),
    ("resources.tag_create", "/tags/create", ("POST",)),
    ("resources.tag_edit", "/tags/{tag_id}/edit", ("GET", "POST")),
    ("resources.tag_delete", "/tags/{tag_id}/delete", ("POST",)),
)

#: Visible labels of the tag form fields, for the error summary.
TAG_FIELD_LABELS: Dict[str, str] = {
    "name": "Name",
    "description": "Description",
}


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _coerce_int(*, raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        return None
    return rtnval


def _coerce_int_with_default(*, raw: Any, default: int) -> int:
    parsed = _coerce_int(raw=raw)
    if parsed is None:
        return default
    return parsed


def _parse_pagination_params(
        *, request: Request,
        default_per_page: int = 20
    ) -> Dict[str, Any]:
    page = _coerce_int_with_default(
        raw=request.query_params.get("page", None), default=1
    )
    if page < 1:
        page = 1
    per_page = _coerce_int_with_default(
        raw=request.query_params.get("per_page", None),
        default=default_per_page,
    )
    if per_page < 1:
        per_page = default_per_page
    if per_page > RESOURCES_MAX_PER_PAGE:
        per_page = RESOURCES_MAX_PER_PAGE
    rtnval = {"page": page, "per_page": per_page}
    return rtnval


# ---------------------------------------------------------------------------
# Lazy-import builder seam
# ---------------------------------------------------------------------------


def _build_resource_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ResourceManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.resource_manager import (  # noqa: E402
        ResourceManager,
    )
    rtnval = ResourceManager(db_session)
    return rtnval


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------


def _render_tag_list(
        *,
        request: Request,
        auth: Any,
        errors: Optional[Dict[str, str]] = None,
        form_data: Optional[Dict[str, str]] = None,
        status_code: int = 200
    ) -> Response:
    """
        Render the tag list, with the create form's errors and typed
        values when a create was refused.
    """
    params = _parse_pagination_params(request=request)
    offset = (params["page"] - 1) * params["per_page"]
    search = (request.query_params.get("search", "") or "").strip()

    list_kwargs: Dict[str, Any] = {
        "offset": offset,
        "limit": params["per_page"],
    }
    if len(search) > 0:
        list_kwargs["search"] = search

    resource_manager = _build_resource_manager(db_session=auth.db_session)
    tags_response = resource_manager.list_tags(**list_kwargs)
    tags = tags_response.tags

    total_pages = _calculate_total_pages(
        total=tags_response.total,
        per_page=params["per_page"],
    )
    page_window = _build_page_window(
        page=params["page"], total_pages=total_pages
    )

    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="resources.tag_list",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context.update(_resources_permission_flags(auth=auth))
    context["tags"] = tags
    context["search"] = search
    context["page"] = params["page"]
    context["per_page"] = params["per_page"]
    context["total_pages"] = total_pages
    context["page_window"] = page_window
    context["errors"] = errors if errors is not None else {}
    context["error_labels"] = TAG_FIELD_LABELS
    context["form_data"] = form_data if form_data is not None else {}
    response = _render(
        template_name="resources/tags/list.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def handle_tag_list(request: Request) -> Response:
    """
        ``GET /resources/tags`` -- paginated tag list with an
        optional ``?search=`` name filter.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        rtnval = _render_tag_list(request=request, auth=auth)
        return rtnval
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _tag_gate(*, auth: Any, action: str) -> Optional[Response]:
    """
        The redirect for someone who may not manage tags, naming the
        action, or ``None`` for a manager.
    """
    rtnval = _require_permission_or_redirect(
        auth=auth,
        permission=_ADMIN_PERMISSION,
        deny_redirect_url=_url_for_module.url_for("resources.tag_list"),
        deny_message=_denial_message(action=action),
    )
    return rtnval


def _csrf_or_none(*, auth: Any, form: Dict[str, Any], fallback: str) -> Optional[Response]:
    redirect = auth_guard.enforce_csrf_or_redirect(
        form=form, session=auth.session, fallback_url=fallback,
    )
    if redirect is not None:
        _attach_session_to_response(response=redirect, session=auth.session)
    return redirect


def _tag_error_message(*, exc: Exception, verb: str) -> str:
    """
        The sentence for a refusal that names no input: the manager's own
        text when it wrote one for people, else a generic one (logged).
    """
    if getattr(exc, "error_code", "") == "TAG_NOT_FOUND":
        return "That tag no longer exists."
    message = getattr(exc, "message", None)
    if isinstance(message, str) is True and len(message) > 0 and getattr(exc, "error_code", None) is not None:
        return message
    _LOGGER.exception("Unexpected error %s a tag", verb)
    return "An unexpected error occurred while {} the tag. The problem has been logged.".format(verb)


def handle_tag_create(request: Request) -> Response:
    """
        ``POST /resources/tags/create`` -- make a tag (manager only).
        A refused name or description re-renders the list with the error
        beside the input.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny = _tag_gate(auth=auth, action="create a tag")
        if deny is not None:
            return deny
        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = _csrf_or_none(
            auth=auth, form=single_form, fallback=_url_for_module.url_for("resources.tag_list"),
        )
        if csrf_redirect is not None:
            return csrf_redirect

        name = str(single_form.get("name", "") or "").strip()
        description = str(single_form.get("description", "") or "").strip()
        resource_manager = _build_resource_manager(db_session=db_session)
        try:
            resource_manager.create_tag(name, description, auth.user_id)
        except Exception as exc:
            errors = form_errors.field_errors_from(exc)
            if len(errors) > 0:
                return _render_tag_list(
                    request=request, auth=auth, errors=errors,
                    form_data={"name": name, "description": description}, status_code=400,
                )
            return _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.tag_list"),
                message=_tag_error_message(exc=exc, verb="creating"),
                category=flash.CATEGORY_ERROR,
            )
        return _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("resources.tag_list"),
            message='Tag "{}" created.'.format(name),
            category=flash.CATEGORY_SUCCESS,
        )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_tag_edit(request: Request) -> Response:
    """
        ``GET|POST /resources/tags/{tag_id}/edit`` -- rename a tag or
        change its description (manager only). Every resource that
        carries the tag keeps it under the new name.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny = _tag_gate(auth=auth, action="edit a tag")
        if deny is not None:
            return deny
        tag_id = _coerce_int(raw=request.path_params.get("tag_id", None))
        resource_manager = _build_resource_manager(db_session=db_session)
        tag = resource_manager.get_tag(tag_id) if tag_id is not None else None
        if tag is None:
            return _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.tag_list"),
                message="That tag no longer exists.",
                category=flash.CATEGORY_ERROR,
            )

        errors: Dict[str, str] = {}
        form_data: Optional[Dict[str, str]] = None
        status_code = 200
        if request.method.upper() == "POST":
            single_form = _parse_form_or_empty(request=request)
            csrf_redirect = _csrf_or_none(
                auth=auth, form=single_form,
                fallback=_url_for_module.url_for("resources.tag_edit", tag_id=tag_id),
            )
            if csrf_redirect is not None:
                return csrf_redirect
            name = str(single_form.get("name", "") or "").strip()
            description = str(single_form.get("description", "") or "").strip()
            try:
                resource_manager.update_tag(tag_id, name=name, description=description, user_id=auth.user_id)
                return _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for("resources.tag_list"),
                    message='Tag "{}" saved.'.format(name),
                    category=flash.CATEGORY_SUCCESS,
                )
            except Exception as exc:
                errors = form_errors.field_errors_from(exc)
                form_data = {"name": name, "description": description}
                status_code = 400
                if len(errors) == 0:
                    flash.add_flash(
                        session=auth.session,
                        message=_tag_error_message(exc=exc, verb="saving"),
                        category=flash.CATEGORY_ERROR,
                    )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="resources.tag_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context.update(_resources_permission_flags(auth=auth))
        context["tag"] = tag
        context["errors"] = errors
        context["error_labels"] = TAG_FIELD_LABELS
        context["form_data"] = form_data
        response = _render(
            template_name="resources/tags/edit.html",
            context=context,
            status_code=status_code,
        )
        _attach_session_to_response(response=response, session=auth.session)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_tag_delete(request: Request) -> Response:
    """
        ``POST /resources/tags/{tag_id}/delete`` -- delete a tag
        (manager only). Resources that carried it stay, untagged.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        deny = _tag_gate(auth=auth, action="delete a tag")
        if deny is not None:
            return deny
        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = _csrf_or_none(
            auth=auth, form=single_form, fallback=_url_for_module.url_for("resources.tag_list"),
        )
        if csrf_redirect is not None:
            return csrf_redirect
        tag_id = _coerce_int(raw=request.path_params.get("tag_id", None))
        resource_manager = _build_resource_manager(db_session=db_session)
        try:
            carried = resource_manager.delete_tag(tag_id, auth.user_id) if tag_id is not None else 0
        except Exception as exc:
            return _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("resources.tag_list"),
                message=_tag_error_message(exc=exc, verb="deleting"),
                category=flash.CATEGORY_ERROR,
            )
        return _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("resources.tag_list"),
            message=(
                "Tag deleted; it was removed from {} resource{}.".format(carried, "" if carried == 1 else "s")
            ),
            category=flash.CATEGORY_SUCCESS,
        )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "resources.tag_list": handle_tag_list,
    "resources.tag_create": handle_tag_create,
    "resources.tag_edit": handle_tag_edit,
    "resources.tag_delete": handle_tag_delete,
}


def register_tags_routes(*, app: Any) -> None:
    """
        Attach the tag list route to a webworks app and register
        its endpoint name with the url_for shim.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = RESOURCES_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _wrap_resources_handler_in_shell(handler)
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_tags_routes",
    "handle_tag_list",
    "handle_tag_create",
    "handle_tag_edit",
    "handle_tag_delete",
]
