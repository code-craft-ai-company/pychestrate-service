"""
.. module:: webinterface.blueprints.config.routes_rpa_types
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Admin registry pages for RPA job types (6-rpa-orchestration M2).

.. moduleauthor:: Code Craft AI LLC

* ``GET  /admin/rpa-job-types``                                   -- registry list.
* ``GET  /admin/rpa-job-types/create``                            -- register form.
* ``POST /admin/rpa-job-types/create``                            -- register.
* ``GET  /admin/rpa-job-types/{type_id}``                         -- detail + versions
                                                                     + publish form.
* ``GET|POST /admin/rpa-job-types/{type_id}/edit``                 -- edit the display
                                                                     name, description,
                                                                     schema, secret
                                                                     fields, capabilities.
* ``POST /admin/rpa-job-types/{type_id}/versions``                -- publish a version.
* ``POST /admin/rpa-job-types/{type_id}/versions/{version}/state`` -- deprecate /
                                                                     retire / activate.
* ``POST /admin/rpa-job-types/{type_id}/retire``                  -- retire the type.

Every write is CSRF-gated and requires ``system:rpa.job_types.manage``;
reads require ``system:rpa.read``.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import HTMLResponse, Response

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    CONFIG_PATH,
    MultiFormView,
    _attach_session_to_response,
    _build_default_template_context,
    _has_permission,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _require_admin_permission_for,
    _require_permission_or_redirect,
    _resolve_authenticated_request,
    _wrap_admin_handler_in_shell,
)


RPA_TYPES_READ_PERMISSION: str = "system:rpa.read"
RPA_TYPES_MANAGE_PERMISSION: str = "system:rpa.job_types.manage"

_ROUTE_TABLE = (
    ("config.rpa_type_list", "/rpa-job-types", ("GET",)),
    ("config.rpa_type_create", "/rpa-job-types/create", ("GET", "POST")),
    ("config.rpa_type_detail", "/rpa-job-types/{type_id}", ("GET",)),
    ("config.rpa_type_edit", "/rpa-job-types/{type_id}/edit", ("GET", "POST")),
    ("config.rpa_type_publish", "/rpa-job-types/{type_id}/versions", ("POST",)),
    ("config.rpa_type_version_state", "/rpa-job-types/{type_id}/versions/{version}/state", ("POST",)),
    ("config.rpa_type_retire", "/rpa-job-types/{type_id}/retire", ("POST",)),
)


# Permission each route enforces server-side before its handler runs
# (see ``routes._require_admin_permission_for``): a route that accepts
# POST changes the registry and needs the manage permission; the
# read-only pages need the read permission. A refused viewer gets the
# shared 403 page naming the permission (it used to be redirected to
# the dashboard with a flash -- audit ADM-21).
_ROUTE_PERMISSIONS = {
    endpoint_name: (
        RPA_TYPES_MANAGE_PERMISSION if "POST" in methods else RPA_TYPES_READ_PERMISSION
    )
    for endpoint_name, _relative_path, methods in _ROUTE_TABLE
}


def _build_rpa_service() -> Any:
    from ccai.pychestrate.webservice.orchestration.rpa import (  # noqa: E402
        service as rpa_service,
    )
    rtnval = rpa_service
    return rtnval


def _parse_json_or_default(*, raw: str, default: Any, field_label: str) -> Any:
    text = str(raw or "").strip()
    if len(text) == 0:
        return default
    try:
        rtnval = json.loads(text)
    except ValueError as exc:
        raise ValueError("{} must be valid JSON: {}".format(field_label, str(exc))) from None
    return rtnval


def _csv(raw: Any) -> List[str]:
    rtnval = [part.strip() for part in str(raw or "").split(",") if len(part.strip()) > 0]
    return rtnval


def _pretty_json(value: Any) -> str:
    try:
        rtnval = json.dumps(value, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        rtnval = ""
    return rtnval


def _execution_modes() -> List[Dict[str, str]]:
    rpa = _build_rpa_service()
    rtnval: List[Dict[str, str]] = []
    for impl in rpa.list_execution_modes():
        rtnval.append({"execution_mode": impl.execution_mode(), "description": impl.describe()})
    return rtnval


def _deny_read(auth: Any) -> Optional[Response]:
    rtnval = _require_permission_or_redirect(
        auth=auth,
        permission=RPA_TYPES_READ_PERMISSION,
        deny_redirect_url=_url_for_module.url_for("config.dashboard"),
        deny_message="You do not have permission to view RPA job types.",
    )
    return rtnval


def _deny_manage(auth: Any, *, fallback_endpoint: str = "config.rpa_type_list", **kwargs: Any) -> Optional[Response]:
    rtnval = _require_permission_or_redirect(
        auth=auth,
        permission=RPA_TYPES_MANAGE_PERMISSION,
        deny_redirect_url=_url_for_module.url_for(fallback_endpoint, **kwargs),
        deny_message="You do not have permission to manage RPA job types.",
    )
    return rtnval


def handle_rpa_type_list(request: Request) -> Response:
    """
        ``GET /admin/rpa-job-types``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        denied = _deny_read(auth)
        if denied is not None:
            return denied
        rpa = _build_rpa_service()
        job_types = rpa.list_job_types(db_session=db_session)
        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="config.rpa_type_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["job_types"] = list(job_types)
        context["can_manage"] = _has_permission(auth=auth, permission=RPA_TYPES_MANAGE_PERMISSION)
        context["total"] = len(job_types)
        response = _render(template_name="config/rpa_types/list.html", context=context)
        _attach_session_to_response(response=response, session=auth.session)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


#: Visible labels of the job type and version form fields, for the
#: error summary.
RPA_TYPE_FIELD_LABELS: Dict[str, str] = {
    "type_id": "Type ID",
    "display_name": "Display Name",
    "packet_schema": "Packet Schema",
    "version": "Version",
    "entrypoint": "Entrypoint",
    "environment": "Environment",
    "timeout_minutes": "Timeout",
}


def _rpa_field_errors(*, exc: BaseException, parsing_field: Optional[str] = None) -> Dict[str, str]:
    """
        The ``{field: message}`` for a refused job type or version form,
        or an empty dict when the error is about no single input (the
        caller then flashes it).

        A duplicate slug is about the type ID and a duplicate version
        about the version. A ``ValueError`` from parsing typed text
        (JSON, the timeout) is about the input being parsed
        (``parsing_field``). Other RPA errors can be about several
        inputs, so they stay a banner.

        :param exc: The error being handled.
        :param parsing_field: The input a ``ValueError`` is about.

        :returns: One entry, or an empty dict.
    """
    from ccai.pychestrate.webservice.orchestration.rpa.errors import (  # noqa: E402
        DuplicateRpaJobTypeError,
        DuplicateVersionError,
    )

    first_line = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
    rtnval: Dict[str, str] = {}
    if isinstance(exc, DuplicateRpaJobTypeError) is True:
        rtnval = {"type_id": first_line}
    elif isinstance(exc, DuplicateVersionError) is True:
        rtnval = {"version": first_line}
    elif isinstance(exc, ValueError) is True and parsing_field is not None:
        rtnval = {parsing_field: first_line}
    return rtnval


def _render_create_form(
        *, auth: Any, form_data: Optional[MultiFormView], status_code: int = 200,
        errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="config.rpa_type_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["form_data"] = form_data
    context["execution_modes"] = _execution_modes()
    context["errors"] = errors if errors is not None else {}
    context["error_labels"] = RPA_TYPE_FIELD_LABELS
    response = _render(template_name="config/rpa_types/create.html", context=context, status_code=status_code)
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_rpa_type_create(request: Request) -> Response:
    """
        ``GET|POST /admin/rpa-job-types/create``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        denied = _deny_manage(auth)
        if denied is not None:
            return denied
        if request.method.upper() == "GET":
            return _render_create_form(auth=auth, form_data=None)

        single_form = _parse_form_or_empty(request=request)
        form_view = MultiFormView(data=_parse_form_multi(request=request))
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for("config.rpa_type_create"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        rpa = _build_rpa_service()
        type_id = str(single_form.get("type_id", "")).strip()
        errors: Dict[str, str] = {}
        parsing_field = "packet_schema"
        try:
            packet_schema = _parse_json_or_default(
                raw=str(single_form.get("packet_schema", "")), default=None, field_label="Packet schema",
            )
            parsing_field = "type_id"
            inputs = rpa.RpaJobTypeInputs(
                type_id=type_id,
                display_name=str(single_form.get("display_name", "")).strip(),
                description=str(single_form.get("description", "")).strip(),
                execution_mode=str(single_form.get("execution_mode", "process")).strip() or "process",
                capability_requirements=tuple(_csv(single_form.get("capability_requirements", ""))),
                packet_schema=packet_schema,
                secret_fields=tuple(_csv(single_form.get("secret_fields", ""))),
            )
            view = rpa.register_job_type(db_session=db_session, inputs=inputs, actor_id=auth.user_id)
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("config.rpa_type_detail", type_id=view.type_id),
                message='RPA job type "{}" registered. Publish a version to make it runnable.'.format(view.type_id),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            errors = _rpa_field_errors(exc=exc, parsing_field=parsing_field if parsing_field == "packet_schema" else None)
            if len(errors) == 0:
                message = str(exc) if isinstance(exc, ValueError) else "Error registering RPA job type: {}".format(str(exc))
                flash.add_flash(session=auth.session, message=message, category=flash.CATEGORY_ERROR)
        return _render_create_form(auth=auth, form_data=form_view, status_code=400, errors=errors)
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _resolve_type_or_redirect(*, auth: Any, rpa: Any, type_id: str) -> Any:
    try:
        rtnval = rpa.get_job_type(db_session=auth.db_session, type_id=type_id)
        return rtnval
    except Exception:
        pass
    rtnval = _redirect_with_flash(
        session=auth.session,
        url=_url_for_module.url_for("config.rpa_type_list"),
        message="RPA job type not found.",
        category=flash.CATEGORY_ERROR,
    )
    return rtnval


def _render_detail(
        *,
        auth: Any,
        job_type: Any,
        form_data: Optional[MultiFormView] = None,
        status_code: int = 200,
        errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    """
        Render the job type page. A failed publish re-renders it with the
        submitted version fields in ``form_data`` so nothing is lost.
    """
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="config.rpa_type_detail",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["job_type"] = job_type
    context["versions"] = list(job_type.versions)
    context["can_manage"] = _has_permission(auth=auth, permission=RPA_TYPES_MANAGE_PERMISSION)
    context["packet_schema_json"] = _pretty_json(dict(job_type.packet_schema)) if job_type.packet_schema else ""
    context["form_data"] = form_data
    context["errors"] = errors if errors is not None else {}
    context["error_labels"] = RPA_TYPE_FIELD_LABELS
    response = _render(template_name="config/rpa_types/detail.html", context=context, status_code=status_code)
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_rpa_type_detail(request: Request) -> Response:
    """
        ``GET /admin/rpa-job-types/{type_id}``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        denied = _deny_read(auth)
        if denied is not None:
            return denied
        rpa = _build_rpa_service()
        type_id = str(request.path_params.get("type_id", ""))
        job_type = _resolve_type_or_redirect(auth=auth, rpa=rpa, type_id=type_id)
        if isinstance(job_type, Response):
            return job_type
        response = _render_detail(auth=auth, job_type=job_type)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _edit_form_values(*, job_type: Any) -> Dict[str, str]:
    """
        The edit form's initial values, from the stored job type.
    """
    rtnval = {
        "display_name": str(job_type.display_name or ""),
        "description": str(job_type.description or ""),
        "capability_requirements": ", ".join(job_type.capability_requirements or ()),
        "secret_fields": ", ".join(job_type.secret_fields or ()),
        "packet_schema": _pretty_json(dict(job_type.packet_schema)) if job_type.packet_schema else "",
    }
    return rtnval


def _render_edit_form(
        *,
        auth: Any,
        job_type: Any,
        form_data: Dict[str, str],
        status_code: int = 200,
        errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="config.rpa_type_edit",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["job_type"] = job_type
    context["form_data"] = form_data
    context["errors"] = errors if errors is not None else {}
    context["error_labels"] = RPA_TYPE_FIELD_LABELS
    response = _render(template_name="config/rpa_types/edit.html", context=context, status_code=status_code)
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_rpa_type_edit(request: Request) -> Response:
    """
        ``GET|POST /admin/rpa-job-types/{type_id}/edit`` -- edit the
        fields a registered type may change. A validation error re-renders
        the form with what was typed.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        type_id = str(request.path_params.get("type_id", ""))
        denied = _deny_manage(auth, fallback_endpoint="config.rpa_type_detail", type_id=type_id)
        if denied is not None:
            return denied
        rpa = _build_rpa_service()
        job_type = _resolve_type_or_redirect(auth=auth, rpa=rpa, type_id=type_id)
        if isinstance(job_type, Response):
            return job_type
        if request.method.upper() == "GET":
            return _render_edit_form(auth=auth, job_type=job_type, form_data=_edit_form_values(job_type=job_type))

        edit_url = _url_for_module.url_for("config.rpa_type_edit", type_id=type_id)
        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form, session=auth.session, fallback_url=edit_url,
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        submitted = {
            key: str(single_form.get(key, "") or "")
            for key in ("display_name", "description", "capability_requirements", "secret_fields", "packet_schema")
        }
        parsing_field = "packet_schema"
        try:
            packet_schema = _parse_json_or_default(
                raw=submitted["packet_schema"], default=None, field_label="Packet schema",
            )
            parsing_field = ""
            rpa.update_job_type(
                db_session=db_session,
                type_id=type_id,
                display_name=submitted["display_name"],
                description=submitted["description"].strip(),
                capability_requirements=_csv(submitted["capability_requirements"]),
                secret_fields=_csv(submitted["secret_fields"]),
                packet_schema=packet_schema,
                actor_id=auth.user_id,
            )
        except Exception as exc:
            errors = _rpa_field_errors(exc=exc, parsing_field=parsing_field or None)
            if len(errors) == 0:
                flash.add_flash(
                    session=auth.session,
                    message="Error saving the job type: {}".format(str(exc).splitlines()[0] if str(exc) else exc),
                    category=flash.CATEGORY_ERROR,
                )
            return _render_edit_form(
                auth=auth, job_type=job_type, form_data=submitted, status_code=400, errors=errors,
            )
        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for("config.rpa_type_detail", type_id=type_id),
            message="RPA job type {} saved.".format(type_id),
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_rpa_type_publish(request: Request) -> Response:
    """
        ``POST /admin/rpa-job-types/{type_id}/versions``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        type_id = str(request.path_params.get("type_id", ""))
        denied = _deny_manage(auth, fallback_endpoint="config.rpa_type_detail", type_id=type_id)
        if denied is not None:
            return denied
        detail_url = _url_for_module.url_for("config.rpa_type_detail", type_id=type_id)
        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form, session=auth.session, fallback_url=detail_url,
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        rpa = _build_rpa_service()
        form_view = MultiFormView(data=_parse_form_multi(request=request))
        parsing_field = "entrypoint"
        try:
            entrypoint = _parse_json_or_default(
                raw=str(single_form.get("entrypoint", "")), default={}, field_label="Entrypoint",
            )
            if not isinstance(entrypoint, dict):
                raise ValueError("Entrypoint must be a JSON object.")
            parsing_field = "environment"
            environment = _parse_json_or_default(
                raw=str(single_form.get("environment", "")), default={}, field_label="Environment",
            )
            if not isinstance(environment, dict):
                raise ValueError("Environment must be a JSON object.")
            parsing_field = "timeout_minutes"
            timeout_raw = str(single_form.get("timeout_minutes", "")).strip()
            try:
                timeout_minutes = int(timeout_raw) if len(timeout_raw) > 0 else 60
            except ValueError:
                raise ValueError("Timeout must be a whole number of minutes.") from None
            parsing_field = ""
            inputs = rpa.RpaVersionInputs(
                version=str(single_form.get("version", "")).strip(),
                source_kind=str(single_form.get("source_kind", "git")).strip() or "git",
                source_ref=str(single_form.get("source_ref", "")).strip(),
                entrypoint=entrypoint,
                environment=environment,
                timeout_minutes=timeout_minutes,
            )
            view = rpa.publish_version(
                db_session=db_session, type_id=type_id, inputs=inputs, actor_id=auth.user_id,
            )
            response = _redirect_with_flash(
                session=auth.session, url=detail_url,
                message="Version {} published.".format(view.version),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            # Re-render (don't redirect) so the typed version, source,
            # entrypoint and environment survive the error.
            job_type = _resolve_type_or_redirect(auth=auth, rpa=rpa, type_id=type_id)
            if isinstance(job_type, Response):
                return job_type
            errors = _rpa_field_errors(exc=exc, parsing_field=parsing_field or None)
            if len(errors) == 0:
                flash.add_flash(
                    session=auth.session,
                    message="Error publishing version: {}".format(str(exc).splitlines()[0] if str(exc) else exc),
                    category=flash.CATEGORY_ERROR,
                )
            return _render_detail(
                auth=auth, job_type=job_type, form_data=form_view, status_code=400, errors=errors,
            )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_rpa_type_version_state(request: Request) -> Response:
    """
        ``POST /admin/rpa-job-types/{type_id}/versions/{version}/state``
        with form field ``state`` in ``active | deprecated | retired``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        type_id = str(request.path_params.get("type_id", ""))
        version = str(request.path_params.get("version", ""))
        denied = _deny_manage(auth, fallback_endpoint="config.rpa_type_detail", type_id=type_id)
        if denied is not None:
            return denied
        detail_url = _url_for_module.url_for("config.rpa_type_detail", type_id=type_id)
        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form, session=auth.session, fallback_url=detail_url,
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect
        rpa = _build_rpa_service()
        try:
            from ccai.pychestrate.webservice.orchestration.rpa.models import RpaVersionState  # noqa: E402
            state = RpaVersionState(str(single_form.get("state", "")).strip())
            rpa.set_version_state(db_session=db_session, type_id=type_id, version=version, state=state)
            response = _redirect_with_flash(
                session=auth.session, url=detail_url,
                message="Version {} is now {}.".format(version, state.value),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session, url=detail_url,
                message="Error changing version state: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_rpa_type_retire(request: Request) -> Response:
    """
        ``POST /admin/rpa-job-types/{type_id}/retire``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response
    db_session = auth.db_session
    try:
        type_id = str(request.path_params.get("type_id", ""))
        denied = _deny_manage(auth, fallback_endpoint="config.rpa_type_detail", type_id=type_id)
        if denied is not None:
            return denied
        detail_url = _url_for_module.url_for("config.rpa_type_detail", type_id=type_id)
        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form, session=auth.session, fallback_url=detail_url,
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect
        rpa = _build_rpa_service()
        try:
            rpa.retire_job_type(db_session=db_session, type_id=type_id, actor_id=auth.user_id)
            response = _redirect_with_flash(
                session=auth.session, url=detail_url,
                message="RPA job type {} retired. New runs are refused; existing jobs stay readable.".format(type_id),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session, url=detail_url,
                message="Error retiring job type: {}".format(str(exc)),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "config.rpa_type_list": handle_rpa_type_list,
    "config.rpa_type_create": handle_rpa_type_create,
    "config.rpa_type_detail": handle_rpa_type_detail,
    "config.rpa_type_edit": handle_rpa_type_edit,
    "config.rpa_type_publish": handle_rpa_type_publish,
    "config.rpa_type_version_state": handle_rpa_type_version_state,
    "config.rpa_type_retire": handle_rpa_type_retire,
}


def register_rpa_types_routes(*, app: Any) -> None:
    """
        Attach the RPA job type registry routes to a webworks app.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = CONFIG_PATH + relative_path
        _url_for_module.register_endpoint(endpoint=endpoint_name, pattern=full_path)
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        wrapped_handler = _require_admin_permission_for(
            _wrap_admin_handler_in_shell(handler),
            permission=_ROUTE_PERMISSIONS[endpoint_name],
        )
        app.attach_route(full_path, methods=list(methods))(wrapped_handler)
    return


__all__ = [
    "register_rpa_types_routes",
    "handle_rpa_type_list",
    "handle_rpa_type_create",
    "handle_rpa_type_detail",
    "handle_rpa_type_edit",
    "handle_rpa_type_publish",
    "handle_rpa_type_version_state",
    "handle_rpa_type_retire",
]
