"""
.. module:: webinterface.blueprints.projects.routes_release_templates
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for
               ``/projects/{project_id}/release-templates``.

.. moduleauthor:: Code Craft AI LLC

CRUD UI for project-scoped release templates -- modeled directly
on the F2 ``routes_repositories`` slice.

* ``GET  /projects/{project_id}/release-templates``
* ``GET  /projects/{project_id}/release-templates/create``
* ``POST /projects/{project_id}/release-templates/create``
* ``GET  /projects/{project_id}/release-templates/{template_id}``
* ``GET  /projects/{project_id}/release-templates/{template_id}/edit``
* ``POST /projects/{project_id}/release-templates/{template_id}/edit``
* ``POST /projects/{project_id}/release-templates/{template_id}/delete``
* ``POST /projects/{project_id}/release-templates/{template_id}/create-release``

Permission tiers:

* ``view``      -- list + detail pages.
* ``developer`` -- create / edit.
* ``admin``     -- delete.
* ``release.create`` (administrators and owners) -- create a draft
  release from a template.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json

from typing import Any, Callable, Dict, List, Optional

from ccai.webworks.routing.request import Request
from ccai.webworks.routing.response import (
    HTMLResponse,
    RedirectResponse,
    Response,
)

from ccai.pychestrate.webservice.webinterface.foundation import (
    auth_guard,
    flash,
    url_for as _url_for_module,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    MultiFormView,
    _AuthResolution,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _not_found_redirect,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    PROJECTS_PATH,
    ProjectsFormError,
    _describe_failure,
    _field_errors_from,
    _require_project_permission_or_redirect,
    _resolve_project_or_redirect,
)


_ROUTE_TABLE = (
    (
        "projects.release_template_list",
        "/{project_id}/release-templates",
        ("GET",),
    ),
    (
        "projects.release_template_create",
        "/{project_id}/release-templates/create",
        ("GET", "POST"),
    ),
    (
        "projects.release_template_detail",
        "/{project_id}/release-templates/{template_id}",
        ("GET",),
    ),
    (
        "projects.release_template_edit",
        "/{project_id}/release-templates/{template_id}/edit",
        ("GET", "POST"),
    ),
    (
        "projects.release_template_delete",
        "/{project_id}/release-templates/{template_id}/delete",
        ("POST",),
    ),
    (
        "projects.release_template_create_release",
        "/{project_id}/release-templates/{template_id}/create-release",
        ("POST",),
    ),
)

#: Project permission needed to create a release from a template
#: (administrators and owners, see ``ROLE_PERMISSIONS``).
RELEASE_CREATE_PERMISSION = "release.create"

#: Inputs the template create / edit forms show errors for.
_TEMPLATE_FORM_FIELDS = ("name", "version_pattern", "default_repo_ids")


# ---------------------------------------------------------------------------
# Lazy-import builder seams
# ---------------------------------------------------------------------------


def _build_project_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ProjectManager`. Lazy-imports.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.project_access import (  # noqa: E402
        build_access_aware_project_manager,
    )
    rtnval = build_access_aware_project_manager(db_session=db_session)
    return rtnval


def _build_template_manager(*, db_session: Any) -> Any:
    """
        Construct a :class:`ReleaseTemplateManager`. Lazy-imports.
    """
    from ccai.pychestrate.core.managers.release_template_manager import (  # noqa: E402
        ReleaseTemplateManager,
    )
    rtnval = ReleaseTemplateManager(db_session=db_session)
    return rtnval


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------


def _coerce_int(*, raw: Any) -> Optional[int]:
    """
        Coerce a value to ``Optional[int]``.

        :param raw: Raw value.

        :returns: Integer or ``None`` if coercion fails.
    """
    if raw is None:
        return None
    try:
        rtnval = int(raw)
    except (TypeError, ValueError):
        return None
    return rtnval


def _coerce_int_with_default(*, raw: Any, default: int) -> int:
    """
        Coerce ``raw`` to int, falling back to ``default``.

        :param raw: Raw value.
        :param default: Fallback integer.

        :returns: Integer.
    """
    parsed = _coerce_int(raw=raw)
    if parsed is None:
        return default
    return parsed


def _parse_pagination_params(
        *, request: Request, default_per_page: int = 20
    ) -> Dict[str, Any]:
    """
        Parse ``page`` and ``per_page`` query parameters.

        :param request: Incoming webworks request.
        :param default_per_page: Default page size.

        :returns: Dict containing ``page`` and ``per_page``.
    """
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
    rtnval = {"page": page, "per_page": per_page}
    return rtnval


def _total_pages_from_count(*, total: int, per_page: int) -> int:
    """
        Compute the real page count from a list response's
        ``total`` field.

        :param total: Total matching rows reported by the manager.
        :param per_page: Page size.

        :returns: Number of pages (at least 1).
    """
    if total is None:
        return 1
    if total <= 0:
        return 1
    rtnval = (total + per_page - 1) // per_page
    return rtnval


def _parse_json_object_or_none(
        *, raw: str, field_label: str
    ) -> Optional[Dict[str, Any]]:
    """
        Parse an optional JSON-object textarea field.

        :param raw: Raw value from the form.
        :param field_label: Label for error messages.

        :returns: ``None`` for empty input; a dict otherwise.

        :raises ValueError: Invalid JSON or non-object payload.
    """
    if raw is None:
        return None
    stripped = raw.strip()
    if len(stripped) == 0:
        return None
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError as exc:
        err_msg_lines = [
            "Invalid JSON in {} field.".format(field_label)
        ]
        err_msg_lines.append("ERROR: {}".format(str(exc)))
        err_msg = "; ".join(err_msg_lines)
        raise ProjectsFormError(err_msg) from exc

    if not isinstance(parsed, dict):
        err_msg = "{} must be a JSON object.".format(field_label)
        raise ProjectsFormError(err_msg)

    rtnval = parsed
    return rtnval


def _parse_repo_id_csv(*, raw: str) -> List[int]:
    """
        Parse a comma-separated list of repository ids.

        :param raw: Raw form value.

        :returns: List of integers.

        :raises ValueError: If any token cannot be coerced to int.
    """
    if raw is None:
        return []
    stripped = raw.strip()
    if len(stripped) == 0:
        return []

    tokens = stripped.split(",")
    rtnval: List[int] = []
    for token in tokens:
        candidate = token.strip()
        if len(candidate) == 0:
            continue
        try:
            value = int(candidate)
        except ValueError as exc:
            err_msg = (
                "default_repo_ids contains a non-integer value: {!r}".format(
                    candidate
                )
            )
            raise ProjectsFormError(err_msg) from exc
        rtnval.append(value)

    return rtnval


def _resolve_template_or_redirect(
        *,
        auth: _AuthResolution,
        template_manager: Any,
        project_id: int,
        template_id: Optional[int]
    ) -> Any:
    """
        Look up a release template AND verify it belongs to the
        supplied project.

        :param auth: Authenticated request resolution.
        :param template_manager: ``ReleaseTemplateManager``.
        :param project_id: Owning project id.
        :param template_id: Candidate template id (may be ``None``).

        :returns: Template response on success; a redirect response
                  on failure.
    """
    if template_id is None:
        rtnval = _not_found_redirect(
            session=auth.session,
            url=_url_for_module.url_for(
                "projects.release_template_list",
                project_id=project_id,
            ),
            message="Release template not found.",
        )
        return rtnval

    template = template_manager.get(template_id)
    if template is None:
        rtnval = _not_found_redirect(
            session=auth.session,
            url=_url_for_module.url_for(
                "projects.release_template_list",
                project_id=project_id,
            ),
            message="Release template not found.",
        )
        return rtnval

    if template.project_id != project_id:
        rtnval = _not_found_redirect(
            session=auth.session,
            url=_url_for_module.url_for(
                "projects.release_template_list",
                project_id=project_id,
            ),
            message="Release template not found.",
        )
        return rtnval
    return template


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _repository_name_map(*, db_session: Any, project_id: int) -> Dict[int, str]:
    """
        ``{repository_id: name}`` for the project, so templates can show
        repository names instead of raw ids (audit P-53). Any failure
        yields an empty map and the template falls back to the id.
    """
    rtnval: Dict[int, str] = {}
    try:
        from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
            RepositoryManager,
        )
        manager = RepositoryManager(db_session)
        response = manager.list_repositories(project_id, limit=500)
        for repository in getattr(response, "repositories", []) or []:
            rtnval[int(repository.id)] = str(repository.name)
    except Exception:
        return {}
    return rtnval


def handle_release_template_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/release-templates``.

        :param request: Incoming webworks request.

        :returns: Rendered list view or a redirect on auth failure.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )

        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="view",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_list"
            ),
            deny_message=(
                "You do not have permission to view this project."
            ),
        )
        if deny_response is not None:
            return deny_response

        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]

        template_manager = _build_template_manager(db_session=db_session)
        result = template_manager.list_for_project(
            project_id, offset=offset, limit=params["per_page"]
        )
        templates = result.templates

        try:
            can_manage = project_manager.check_permission(
                project_id, auth.user_id, "developer"
            )
        except Exception:
            can_manage = False

        total_pages = _total_pages_from_count(
            total=result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.release_template_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["templates"] = templates
        context["repository_names"] = _repository_name_map(db_session=db_session, project_id=project_id)
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages
        context["total"] = result.total

        response = _render(
            template_name="projects/release_templates/list.html",
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


def _render_template_create_form(
        *,
        auth: _AuthResolution,
        project: Any,
        form_data: Optional[MultiFormView],
        status_code: int = 200,
        errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    """
        Render the create form for a release template.

        :param auth: Authenticated request resolution.
        :param project: Resolved project.
        :param form_data: Multi-form view for re-rendering after a
                          validation failure.
        :param status_code: HTTP status code.
        :param errors: Inline field errors (input name -> message).

        :returns: Rendered HTML response.
    """
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.release_template_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["project"] = project
    context["form_data"] = form_data
    context["errors"] = errors if errors is not None else {}
    response = _render(
        template_name="projects/release_templates/create.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def handle_release_template_create(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/release-templates/create`` and
        ``POST .../create``. ``developer``-gated.

        :param request: Incoming webworks request.

        :returns: Rendered HTML response or a redirect.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )

        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="developer",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        method = request.method.upper()

        if method == "GET":
            response = _render_template_create_form(
                auth=auth, project=project, form_data=None
            )
            return response

        # POST
        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        form_view = MultiFormView(data=multi_form)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.release_template_create",
                project_id=project_id,
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        description = str(single_form.get("description", "")).strip()
        default_channel = str(
            single_form.get("default_channel", "")
        ).strip()
        version_pattern = str(
            single_form.get("version_pattern", "")
        ).strip()
        repo_ids_raw = str(single_form.get("default_repo_ids", ""))
        pipeline_raw = str(single_form.get("default_pipeline", ""))
        schedule_raw = str(single_form.get("default_schedule", ""))

        template_manager = _build_template_manager(db_session=db_session)
        try:
            repo_ids = _parse_repo_id_csv(raw=repo_ids_raw)
            pipeline_blob = _parse_json_object_or_none(
                raw=pipeline_raw, field_label="default_pipeline"
            )
            schedule_blob = _parse_json_object_or_none(
                raw=schedule_raw, field_label="default_schedule"
            )

            template = template_manager.create(
                project_id,
                name=name,
                description=description,
                default_channel=(
                    default_channel if len(default_channel) > 0 else None
                ),
                version_pattern=(
                    version_pattern if len(version_pattern) > 0 else None
                ),
                default_repo_ids=repo_ids,
                default_pipeline=pipeline_blob,
                default_schedule=schedule_blob,
                created_by=auth.user_id,
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.release_template_detail",
                    project_id=project_id,
                    template_id=template.id,
                ),
                message='Release template "{}" created successfully.'.format(
                    name
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except ValueError as exc:
            errors = {}
            flash.add_flash(
                session=auth.session,
                message=_describe_failure(exc=exc, prefix="", request_path=str(getattr(request, "path", ""))),
                category=flash.CATEGORY_ERROR,
            )
        except Exception as exc:
            # A problem with one field is shown next to it.
            errors = _field_errors_from(exc=exc, fields=_TEMPLATE_FORM_FIELDS)
            if len(errors) == 0:
                flash.add_flash(
                    session=auth.session,
                    message=_describe_failure(exc=exc, prefix="Error creating release template: ", request_path=str(getattr(request, "path", ""))),
                    category=flash.CATEGORY_ERROR,
                )

        response = _render_template_create_form(
            auth=auth,
            project=project,
            form_data=form_view,
            status_code=400,
            errors=errors,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_release_template_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/release-templates/{template_id}``.
        ``view``-gated.

        :param request: Incoming webworks request.

        :returns: Rendered HTML response or a redirect.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        template_id = _coerce_int(
            raw=request.path_params.get("template_id", None)
        )

        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="view",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_list"
            ),
            deny_message=(
                "You do not have permission to view this project."
            ),
        )
        if deny_response is not None:
            return deny_response

        template_manager = _build_template_manager(db_session=db_session)
        template_or_redirect = _resolve_template_or_redirect(
            auth=auth,
            template_manager=template_manager,
            project_id=project_id,
            template_id=template_id,
        )
        if isinstance(template_or_redirect, RedirectResponse):
            return template_or_redirect
        template = template_or_redirect

        response = _render_template_detail(
            auth=auth,
            project=project,
            template=template,
            project_manager=project_manager,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _render_template_detail(
        *,
        auth: _AuthResolution,
        project: Any,
        template: Any,
        project_manager: Any,
        status_code: int = 200,
        release_form: Optional[Dict[str, str]] = None,
        release_errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    """
        Render the release-template detail page, including the
        "Create release" form for users allowed to create releases.

        :param auth: Authenticated request resolution.
        :param project: The owning project.
        :param template: The release template.
        :param project_manager: ProjectManager for the permission probes.
        :param status_code: HTTP status (400 when re-rendering a
                            create-release form with errors).
        :param release_form: Values the user typed into the
                             create-release form, echoed back.
        :param release_errors: Field name -> message for the
                               create-release form.

        :returns: The rendered response.
    """
    project_id = project.id

    try:
        can_manage = project_manager.check_permission(
            project_id, auth.user_id, "developer"
        )
    except Exception:
        can_manage = False

    try:
        can_delete = project_manager.check_permission(
            project_id, auth.user_id, "admin"
        )
    except Exception:
        can_delete = False

    try:
        can_create_release = project_manager.check_permission(
            project_id, auth.user_id, RELEASE_CREATE_PERMISSION
        )
    except Exception:
        can_create_release = False

    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.release_template_detail",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["project"] = project
    context["template"] = template
    context["repository_names"] = _repository_name_map(db_session=auth.db_session, project_id=project_id)
    context["can_manage"] = can_manage
    context["can_delete"] = can_delete
    context["can_create_release"] = can_create_release
    context["release_form"] = release_form if release_form is not None else {}
    context["release_errors"] = release_errors if release_errors is not None else {}
    context["default_pipeline_json"] = (
        json.dumps(template.default_pipeline, indent=2)
        if template.default_pipeline is not None else ""
    )
    context["default_schedule_json"] = (
        json.dumps(template.default_schedule, indent=2)
        if template.default_schedule is not None else ""
    )

    response = _render(
        template_name="projects/release_templates/detail.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def handle_release_template_create_release(request: Request) -> Response:
    """
        ``POST /projects/{project_id}/release-templates/{template_id}/create-release``.
        Creates a draft release from the template. Needs the project's
        ``release.create`` permission (administrators and owners).

        A version that is missing, not a semantic version, outside the
        template's version pattern, or already released re-renders the
        template page with the message next to the version field.

        :param request: Incoming webworks request.

        :returns: Redirect to the new release, or the template page with
                  field errors.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        template_id = _coerce_int(
            raw=request.path_params.get("template_id", None)
        )

        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        detail_url = _url_for_module.url_for(
            "projects.release_template_detail",
            project_id=project_id,
            template_id=template_id,
        ) if template_id is not None else _url_for_module.url_for(
            "projects.release_template_list", project_id=project_id
        )

        single_form = _parse_form_or_empty(request=request)
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=detail_url,
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission=RELEASE_CREATE_PERMISSION,
            deny_redirect_url=detail_url,
            deny_message=(
                "Only project administrators and owners can create "
                "releases."
            ),
        )
        if deny_response is not None:
            return deny_response

        template_manager = _build_template_manager(db_session=db_session)
        template_or_redirect = _resolve_template_or_redirect(
            auth=auth,
            template_manager=template_manager,
            project_id=project_id,
            template_id=template_id,
        )
        if isinstance(template_or_redirect, RedirectResponse):
            return template_or_redirect
        template = template_or_redirect

        version = str(single_form.get("version", "")).strip()
        name = str(single_form.get("name", "")).strip()
        release_form = {"version": version, "name": name}

        try:
            release = template_manager.create_release_from_template(
                project_id,
                template_id,
                version=version,
                name=name if len(name) > 0 else None,
                user_id=auth.user_id,
            )
        except Exception as exc:
            if _is_release_input_error(exc=exc) is False:
                raise
            db_session.rollback()
            response = _render_template_detail(
                auth=auth,
                project=project,
                template=template,
                project_manager=project_manager,
                status_code=400,
                release_form=release_form,
                release_errors={
                    "version": _first_line(
                        text=getattr(exc, "message", None) or str(exc)
                    ),
                },
            )
            return response

        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for(
                "projects.release_detail",
                project_id=project_id,
                release_id=release.id,
            ),
            message='Draft release {} created from template "{}".'.format(
                release.version, template.name
            ),
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _is_release_input_error(*, exc: BaseException) -> bool:
    """
        Whether ``exc`` is a problem with the version the user typed
        (missing, not semantic, outside the template's pattern, or
        already released) rather than an internal failure.

        :param exc: The exception raised while creating the release.

        :returns: ``True`` for the four user-input errors.
    """
    from ccai.pychestrate.core.managers.release_manager import (  # noqa: E402
        DuplicateReleaseVersionError,
        ReleaseVersionValidationError,
    )
    from ccai.pychestrate.core.managers.release_template_manager import (  # noqa: E402
        ReleaseTemplateValidationError,
    )
    rtnval = isinstance(
        exc,
        (
            DuplicateReleaseVersionError,
            ReleaseVersionValidationError,
            ReleaseTemplateValidationError,
        ),
    )
    return rtnval


def _first_line(*, text: str) -> str:
    """
        The first line of a (possibly multi-line) manager message.

        :param text: Message text.

        :returns: Its first non-empty line.
    """
    for line in str(text).splitlines():
        if len(line.strip()) > 0:
            return line.strip()
    return str(text).strip()


def handle_release_template_edit(request: Request) -> Response:
    """
        ``GET .../{template_id}/edit`` / ``POST .../{template_id}/edit``.
        ``developer``-gated.

        :param request: Incoming webworks request.

        :returns: Rendered HTML response or a redirect.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        template_id = _coerce_int(
            raw=request.path_params.get("template_id", None)
        )

        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(resolved, RedirectResponse):
            return resolved
        project = resolved

        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="developer",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        template_manager = _build_template_manager(db_session=db_session)
        template_or_redirect = _resolve_template_or_redirect(
            auth=auth,
            template_manager=template_manager,
            project_id=project_id,
            template_id=template_id,
        )
        if isinstance(template_or_redirect, RedirectResponse):
            return template_or_redirect
        template = template_or_redirect

        method = request.method.upper()

        # Populated on a POST that falls through to the re-render
        # so the form shows the submitted values rather than the
        # stale database copy.
        form_view: Optional[MultiFormView] = None
        errors: Dict[str, str] = {}

        if method == "POST":
            single_form = _parse_form_or_empty(request=request)
            multi_form = _parse_form_multi(request=request)
            form_view = MultiFormView(data=multi_form)

            csrf_redirect = auth_guard.enforce_csrf_or_redirect(
                form=single_form,
                session=auth.session,
                fallback_url=_url_for_module.url_for(
                    "projects.release_template_edit",
                    project_id=project_id,
                    template_id=template_id,
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            name = str(single_form.get("name", "")).strip()
            description = str(single_form.get("description", "")).strip()
            default_channel = str(
                single_form.get("default_channel", "")
            ).strip()
            version_pattern = str(
                single_form.get("version_pattern", "")
            ).strip()
            repo_ids_raw = str(single_form.get("default_repo_ids", ""))
            pipeline_raw = str(single_form.get("default_pipeline", ""))
            schedule_raw = str(single_form.get("default_schedule", ""))

            try:
                repo_ids = _parse_repo_id_csv(raw=repo_ids_raw)
                pipeline_blob = _parse_json_object_or_none(
                    raw=pipeline_raw, field_label="default_pipeline"
                )
                schedule_blob = _parse_json_object_or_none(
                    raw=schedule_raw, field_label="default_schedule"
                )

                template_manager.update(
                    template_id,
                    name=name if len(name) > 0 else None,
                    description=description,
                    default_channel=default_channel,
                    version_pattern=version_pattern,
                    default_repo_ids=repo_ids,
                    default_pipeline=(
                        pipeline_blob
                        if pipeline_blob is not None else {}
                    ),
                    default_schedule=(
                        schedule_blob
                        if schedule_blob is not None else {}
                    ),
                    updated_by=auth.user_id,
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "projects.release_template_detail",
                        project_id=project_id,
                        template_id=template_id,
                    ),
                    message="Release template updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except ValueError as exc:
                flash.add_flash(
                    session=auth.session,
                    message=_describe_failure(exc=exc, prefix="", request_path=str(getattr(request, "path", ""))),
                    category=flash.CATEGORY_ERROR,
                )
            except Exception as exc:
                # A problem with one field is shown next to it.
                errors = _field_errors_from(exc=exc, fields=_TEMPLATE_FORM_FIELDS)
                if len(errors) == 0:
                    flash.add_flash(
                        session=auth.session,
                        message=_describe_failure(exc=exc, prefix="Error updating release template: ", request_path=str(getattr(request, "path", ""))),
                        category=flash.CATEGORY_ERROR,
                    )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.release_template_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["template"] = template
        context["errors"] = errors
        context["repository_names"] = _repository_name_map(db_session=db_session, project_id=project_id)
        context["form_data"] = form_view
        context["default_pipeline_json"] = (
            json.dumps(template.default_pipeline, indent=2)
            if template.default_pipeline is not None else ""
        )
        context["default_schedule_json"] = (
            json.dumps(template.default_schedule, indent=2)
            if template.default_schedule is not None else ""
        )
        context["default_repo_ids_csv"] = ", ".join(
            str(value) for value in template.default_repo_ids
        )

        response = _render(
            template_name="projects/release_templates/edit.html",
            context=context,
            status_code=400 if form_view is not None else 200,
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


def handle_release_template_delete(request: Request) -> Response:
    """
        ``POST /projects/{project_id}/release-templates/{template_id}/delete``.
        ``admin``-gated.

        :param request: Incoming webworks request.

        :returns: Redirect response.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        template_id = _coerce_int(
            raw=request.path_params.get("template_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=(
                _url_for_module.url_for(
                    "projects.release_template_list",
                    project_id=project_id,
                )
                if project_id is not None
                else _url_for_module.url_for("projects.project_list")
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if project_id is None or template_id is None:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for("projects.project_list"),
                message="Release template not found.",
            )
            return response

        project_manager = _build_project_manager(db_session=db_session)
        deny_response = _require_project_permission_or_redirect(
            project_manager=project_manager,
            auth=auth,
            project_id=project_id,
            permission="admin",
            deny_redirect_url=_url_for_module.url_for(
                "projects.project_detail", project_id=project_id
            ),
        )
        if deny_response is not None:
            return deny_response

        template_manager = _build_template_manager(db_session=db_session)
        existing = template_manager.get(template_id)
        if existing is None or existing.project_id != project_id:
            response = _not_found_redirect(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.release_template_list",
                    project_id=project_id,
                ),
                message="Release template not found.",
            )
            return response

        try:
            template_manager.delete(
                template_id, deleted_by=auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.release_template_list",
                    project_id=project_id,
                ),
                message="Release template deleted successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.release_template_list",
                    project_id=project_id,
                ),
                message=_describe_failure(exc=exc, prefix="Error deleting release template: ", request_path=str(getattr(request, "path", ""))),
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
    "projects.release_template_list": handle_release_template_list,
    "projects.release_template_create": handle_release_template_create,
    "projects.release_template_detail": handle_release_template_detail,
    "projects.release_template_edit": handle_release_template_edit,
    "projects.release_template_delete": handle_release_template_delete,
    "projects.release_template_create_release": handle_release_template_create_release,
}


def register_release_templates_routes(*, app: Any) -> None:
    """
        Attach the release-template UI routes to a webworks app and
        register their endpoint names with the url_for shim.

        :param app: WebWorks application built by
                    ``establish_webapp_persona``.

        :returns: None.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = PROJECTS_PATH + relative_path
        _url_for_module.register_endpoint(
            endpoint=endpoint_name, pattern=full_path
        )
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(handler)
    return


__all__ = [
    "register_release_templates_routes",
    "handle_release_template_list",
    "handle_release_template_create",
    "handle_release_template_detail",
    "handle_release_template_edit",
    "handle_release_template_delete",
    "handle_release_template_create_release",
]
