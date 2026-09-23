"""
.. module:: webinterface.blueprints.projects.routes_repositories
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /projects/*/repositories
               (F2 slice -- repository management).

.. moduleauthor:: Code Craft AI LLC

The seven repository routes served under the projects blueprint:

* ``GET  /projects/{project_id}/repositories``                          -- list.
* ``GET  /projects/{project_id}/repositories/create``                   -- form.
* ``POST /projects/{project_id}/repositories/create``                   -- create
                                                                           (developer).
* ``GET  /projects/{project_id}/repositories/{repository_id}``          -- detail.
* ``GET  /projects/{project_id}/repositories/{repository_id}/edit``     -- form
                                                                           (developer).
* ``POST /projects/{project_id}/repositories/{repository_id}/edit``     -- update
                                                                           (developer).
* ``POST /projects/{project_id}/repositories/{repository_id}/delete``   -- delete
                                                                           (admin).
* ``POST /projects/{project_id}/repositories/{repository_id}/test``     -- ping
                                                                           connectivity.
* ``POST /projects/{project_id}/repositories/{repository_id}/fetch``    -- refresh
                                                                           remote
                                                                           metadata.

Permission tiers used here:

* ``view`` -- list + detail pages (read-only access for any
  project member).
* ``developer`` -- create / edit / test / fetch (writes that
  don't destroy data).
* ``admin`` -- delete (destructive).
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


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
    MultiFormView,
    _AuthResolution,
    _attach_session_to_response,
    _build_default_template_context,
    _parse_form_multi,
    _parse_form_or_empty,
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    PROJECTS_PATH,
    ProjectsFormError,
    _describe_failure,
    _field_errors_from,
    _is_user_facing_error,
    _require_project_permission_or_redirect,
    _resolve_project_or_redirect,
)


_ROUTE_TABLE = (
    (
        "projects.repository_list",
        "/{project_id}/repositories",
        ("GET",),
    ),
    (
        "projects.repository_create",
        "/{project_id}/repositories/create",
        ("GET", "POST"),
    ),
    (
        "projects.repository_detail",
        "/{project_id}/repositories/{repository_id}",
        ("GET",),
    ),
    (
        "projects.repository_edit",
        "/{project_id}/repositories/{repository_id}/edit",
        ("GET", "POST"),
    ),
    (
        "projects.repository_delete",
        "/{project_id}/repositories/{repository_id}/delete",
        ("POST",),
    ),
    (
        "projects.repository_test",
        "/{project_id}/repositories/{repository_id}/test",
        ("POST",),
    ),
    (
        "projects.repository_fetch",
        "/{project_id}/repositories/{repository_id}/fetch",
        ("POST",),
    ),
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams (defined locally per the E2 lesson)
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


def _build_repository_manager(
        *, db_session: Any, user_id: Optional[str] = None
    ) -> Any:
    """
        Construct a :class:`RepositoryManager`. Lazy-imports.

        :param db_session: Open SQLAlchemy session.
        :param user_id: The signed-in user. When given, the manager can
                        read the repository's credential secret from the
                        secrets vault with that user's permissions, and
                        the watches a fetch fires run their actions as
                        that user (for the test and fetch actions).

        :returns: RepositoryManager instance.
    """
    from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryManager,
    )
    credential_resolver = None
    event_sink = None
    if user_id is not None:
        from ccai.pychestrate.webservice.webinterface.blueprints.projects.repository_credentials import (  # noqa: E402
            build_credential_resolver,
        )
        from ccai.pychestrate.webservice.webinterface.blueprints.projects.watch_events import (  # noqa: E402
            build_watch_event_sink,
        )
        credential_resolver = build_credential_resolver(
            db_session=db_session, user_id=user_id
        )
        event_sink = build_watch_event_sink(
            db_session=db_session, user_id=user_id
        )
    rtnval = RepositoryManager(
        db_session, credential_resolver=credential_resolver,
        event_sink=event_sink,
    )
    return rtnval


def _check_credential_reference(
        *, db_session: Any, user_id: str, secret_ref: str
    ) -> None:
    """
        Refuse a credential secret the signed-in user cannot read (see
        :mod:`repository_credentials`). Lazy-imports.

        :raises RepositoryCredentialError: when the reference is unusable.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.repository_credentials import (  # noqa: E402
        check_credential_reference,
    )
    check_credential_reference(
        db_session=db_session, user_id=user_id, secret_ref=secret_ref
    )
    return


def _build_specs_using_repository(
        *, db_session: Any, project_id: int, repository_id: int
    ) -> List[str]:
    """
        Names of the project's build specifications that build the
        repository (they block its removal). Lazy-imports; any failure
        yields an empty list.
    """
    from ccai.pychestrate.core.managers.build_manager import (  # noqa: E402
        BuildManager,
    )
    try:
        specs = BuildManager(db_session).list_specs(project_id, limit=500).specs
        rtnval = sorted(
            str(spec.name) for spec in specs
            if getattr(spec, "repository_id", None) == repository_id
        )
    except Exception:
        rtnval = []
    return rtnval


def _list_secret_refs(*, db_session: Any, user_id: str) -> List[str]:
    """
        Secret references to offer in the repository forms. Lazy-imports.

        :returns: Sorted secret references (possibly empty).
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.repository_credentials import (  # noqa: E402
        list_readable_secret_refs,
    )
    rtnval = list_readable_secret_refs(db_session=db_session, user_id=user_id)
    return rtnval


def _resolve_repository_auth_type(*, auth_type_str: str) -> Any:
    """
        Resolve a string to the :class:`RepositoryAuthType`
        enum value. Raises ValueError on unknown.
    """
    from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryAuthType,
    )
    try:
        rtnval = RepositoryAuthType(auth_type_str)
    except ValueError:
        raise ProjectsFormError(
            "Choose how the server signs in to the repository."
        ) from None
    return rtnval


def _enumerate_repository_auth_type_values() -> List[str]:
    """
        Return every :class:`RepositoryAuthType` value as a
        string. For the auth-type <select> dropdown.
    """
    try:
        from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
            RepositoryAuthType,
        )
    except ImportError:
        return []
    rtnval: List[str] = []
    for member in RepositoryAuthType:
        rtnval.append(member.value)
    return rtnval


def _build_repository_create_request(
        *,
        name: str,
        url: str,
        auth_type: Any,
        credential_secret_ref: Optional[str],
        default_branch: str,
        description: str
    ) -> Any:
    """
        Construct a :class:`RepositoryCreateRequest`.
        Lazy-imports.
    """
    from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryCreateRequest,
    )
    rtnval = RepositoryCreateRequest(
        name=name,
        url=url,
        auth_type=auth_type,
        credential_secret_ref=credential_secret_ref,
        default_branch=default_branch,
        description=description,
    )
    return rtnval


def _build_repository_update_request(
        *,
        name: Optional[str],
        credential_secret_ref: Optional[str],
        default_branch: Optional[str],
        description: Optional[str]
    ) -> Any:
    """
        Construct a :class:`RepositoryUpdateRequest`.
        Lazy-imports.
    """
    from ccai.pychestrate.core.managers.repository_manager import (  # noqa: E402
        RepositoryUpdateRequest,
    )
    rtnval = RepositoryUpdateRequest(
        name=name,
        credential_secret_ref=credential_secret_ref,
        default_branch=default_branch,
        description=description,
    )
    return rtnval


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


def _resolve_repository_or_redirect(
        *,
        auth: _AuthResolution,
        repository_manager: Any,
        project_id: int,
        repository_id: Optional[int]
    ) -> Any:
    """
        Look up a repository AND verify it belongs to the
        supplied project (mirrors the legacy
        ``repository.project_id != project_id`` guard). On
        failure returns a redirect to the project's repository
        list.

        :returns: The repository on success; a
                  ``RedirectResponse`` to the repository list
                  on any failure.
    """
    if repository_id is None:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for(
                "projects.repository_list", project_id=project_id
            ),
            message="Repository not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval

    repository = repository_manager.get_repository(repository_id)
    if repository is None:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for(
                "projects.repository_list", project_id=project_id
            ),
            message="Repository not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval

    # Repository belongs to a different project -- treat as not
    # found rather than leak existence.
    if getattr(repository, "project_id", None) != project_id:
        rtnval = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for(
                "projects.repository_list", project_id=project_id
            ),
            message="Repository not found.",
            category=flash.CATEGORY_ERROR,
        )
        return rtnval
    return repository


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_repository_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/repositories`` --
        ``view``-gated; ``can_manage`` flag toggled by
        ``developer``.
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

        repository_manager = _build_repository_manager(
            db_session=db_session
        )
        repositories_result = repository_manager.list_repositories(
            project_id, offset=offset, limit=params["per_page"]
        )
        repositories = repositories_result.repositories

        try:
            can_manage = project_manager.check_permission(
                project_id, auth.user_id, "developer"
            )
        except Exception:
            can_manage = False

        total_pages = _total_pages_from_count(
            total=repositories_result.total,
            per_page=params["per_page"],
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.repository_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["repositories"] = repositories
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total_pages"] = total_pages

        response = _render(
            template_name="projects/repositories/list.html",
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


#: Inputs the repository create form shows errors for.
_CREATE_FORM_FIELDS = ("name", "url", "auth_type", "credential_secret_ref", "default_branch")

#: Inputs the repository edit form shows errors for.
_EDIT_FORM_FIELDS = ("name", "credential_secret_ref", "default_branch")


def _repository_form_errors(
        *, exc: BaseException, fields: Any = _CREATE_FORM_FIELDS
    ) -> Dict[str, str]:
    """
        Inline errors for the repository forms: the manager's field, or
        the credential secret field for a secret that cannot be used.

        :param exc: The exception being handled.
        :param fields: The inputs the form shows errors for.

        :returns: ``{input name: message}`` (empty: show a message above
                  the form instead).
    """
    if getattr(exc, "error_code", None) == "REPOSITORY_CREDENTIAL_UNAVAILABLE":
        rtnval = {"credential_secret_ref": getattr(exc, "message", None) or str(exc)}
    else:
        rtnval = _field_errors_from(exc=exc, fields=fields)
    return rtnval


def _render_repository_create_form(
        *, auth: _AuthResolution, project: Any,
        form_data: Optional[MultiFormView],
        status_code: int = 200,
        errors: Optional[Dict[str, str]] = None
    ) -> HTMLResponse:
    auth_types = _enumerate_repository_auth_type_values()
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.repository_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["project"] = project
    context["auth_types"] = auth_types
    context["form_data"] = form_data
    context["errors"] = errors if errors is not None else {}
    context["secret_refs"] = _list_secret_refs(
        db_session=auth.db_session, user_id=auth.user_id
    )
    response = _render(
        template_name="projects/repositories/create.html",
        context=context,
        status_code=status_code,
    )
    _attach_session_to_response(
        response=response, session=auth.session
    )
    return response


def handle_repository_create(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/repositories/create`` /
        ``POST .../create``. ``developer``-gated.
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
            return _render_repository_create_form(
                auth=auth, project=project, form_data=None
            )

        # POST
        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        form_view = MultiFormView(data=multi_form)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.repository_create",
                project_id=project_id,
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        url = str(single_form.get("url", "")).strip()
        auth_type_str = str(single_form.get("auth_type", "none")).strip()
        credential_secret_ref = str(
            single_form.get("credential_secret_ref", "")
        ).strip()
        if auth_type_str == "none":
            # A public repository has no credential; drop any secret
            # name left in the form.
            credential_secret_ref = ""
        default_branch = str(
            single_form.get("default_branch", "main")
        ).strip()
        if len(default_branch) == 0:
            default_branch = "main"
        description = str(
            single_form.get("description", "")
        ).strip()

        repository_manager = _build_repository_manager(
            db_session=db_session
        )

        try:
            auth_type = _resolve_repository_auth_type(
                auth_type_str=auth_type_str
            )
            # A repository may only use a secret its creator can read:
            # the server authenticates with it on everyone's behalf.
            if len(credential_secret_ref) > 0:
                _check_credential_reference(
                    db_session=db_session,
                    user_id=auth.user_id,
                    secret_ref=credential_secret_ref,
                )
            create_request = _build_repository_create_request(
                name=name,
                url=url,
                auth_type=auth_type,
                credential_secret_ref=(
                    credential_secret_ref
                    if len(credential_secret_ref) > 0 else None
                ),
                default_branch=default_branch,
                description=description,
            )
            repository = repository_manager.add_repository(
                project_id, create_request, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.repository_detail",
                    project_id=project_id,
                    repository_id=repository.id,
                ),
                message='Repository "{}" added successfully.'.format(
                    name
                ),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            # A problem with one field is shown next to it; anything
            # else as a message above the form.
            errors = _repository_form_errors(exc=exc)
            if len(errors) == 0:
                flash.add_flash(
                    session=auth.session,
                    message=_describe_failure(
                        exc=exc,
                        prefix="Error adding repository: ",
                        request_path=str(getattr(request, "path", "")),
                    ),
                    category=flash.CATEGORY_ERROR,
                )
            return _render_repository_create_form(
                auth=auth, project=project, form_data=form_view,
                status_code=400, errors=errors,
            )

        return _render_repository_create_form(
            auth=auth, project=project, form_data=form_view,
            status_code=400,
        )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_repository_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/repositories/{repository_id}``
        -- ``view``-gated; ``can_manage`` toggled by
        ``developer``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        repository_id = _coerce_int(
            raw=request.path_params.get("repository_id", None)
        )

        project_manager = _build_project_manager(db_session=db_session)
        project_resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(project_resolved, RedirectResponse):
            return project_resolved
        project = project_resolved

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

        repository_manager = _build_repository_manager(
            db_session=db_session
        )
        repo_resolved = _resolve_repository_or_redirect(
            auth=auth,
            repository_manager=repository_manager,
            project_id=project_id,
            repository_id=repository_id,
        )
        if isinstance(repo_resolved, RedirectResponse):
            return repo_resolved
        repository = repo_resolved

        try:
            can_manage = project_manager.check_permission(
                project_id, auth.user_id, "developer"
            )
        except Exception:
            can_manage = False
        # Deletion is admin-gated in handle_repository_delete; gate
        # the button the same way so developers never see a Remove
        # control that bounces them with an error.
        try:
            can_delete = project_manager.check_permission(
                project_id, auth.user_id, "admin"
            )
        except Exception:
            can_delete = False

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.repository_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["repository"] = repository
        context["can_manage"] = can_manage
        context["can_delete"] = can_delete
        # A repository that build specifications build cannot be
        # removed; the page names them instead of offering Remove.
        context["repository_specs"] = _build_specs_using_repository(
            db_session=db_session, project_id=project_id,
            repository_id=repository_id,
        )

        response = _render(
            template_name="projects/repositories/detail.html",
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


def handle_repository_edit(request: Request) -> Response:
    """
        ``GET .../{repository_id}/edit`` /
        ``POST .../{repository_id}/edit``. ``developer``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        repository_id = _coerce_int(
            raw=request.path_params.get("repository_id", None)
        )

        project_manager = _build_project_manager(db_session=db_session)
        project_resolved = _resolve_project_or_redirect(
            auth=auth,
            project_manager=project_manager,
            project_id=project_id,
        )
        if isinstance(project_resolved, RedirectResponse):
            return project_resolved
        project = project_resolved

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

        repository_manager = _build_repository_manager(
            db_session=db_session
        )
        repo_resolved = _resolve_repository_or_redirect(
            auth=auth,
            repository_manager=repository_manager,
            project_id=project_id,
            repository_id=repository_id,
        )
        if isinstance(repo_resolved, RedirectResponse):
            return repo_resolved
        repository = repo_resolved

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
                    "projects.repository_edit",
                    project_id=project_id,
                    repository_id=repository_id,
                ),
            )
            if csrf_redirect is not None:
                _attach_session_to_response(
                    response=csrf_redirect, session=auth.session
                )
                return csrf_redirect

            name = str(single_form.get("name", "")).strip()
            credential_secret_ref = str(
                single_form.get("credential_secret_ref", "")
            ).strip()
            default_branch = str(
                single_form.get("default_branch", "")
            ).strip()
            description = str(
                single_form.get("description", "")
            ).strip()

            try:
                # A new credential secret must be one the editor can read.
                current_ref = getattr(repository, "credential_secret_ref", None) or ""
                if (
                    len(credential_secret_ref) > 0
                    and credential_secret_ref != current_ref
                ):
                    _check_credential_reference(
                        db_session=db_session,
                        user_id=auth.user_id,
                        secret_ref=credential_secret_ref,
                    )
                update_request = _build_repository_update_request(
                    name=name if len(name) > 0 else None,
                    credential_secret_ref=(
                        credential_secret_ref
                        if len(credential_secret_ref) > 0 else None
                    ),
                    default_branch=(
                        default_branch
                        if len(default_branch) > 0 else None
                    ),
                    description=(
                        description if len(description) > 0 else None
                    ),
                )
                repository_manager.update_repository(
                    repository_id, update_request, auth.user_id
                )
                response = _redirect_with_flash(
                    session=auth.session,
                    url=_url_for_module.url_for(
                        "projects.repository_detail",
                        project_id=project_id,
                        repository_id=repository_id,
                    ),
                    message="Repository updated successfully.",
                    category=flash.CATEGORY_SUCCESS,
                )
                return response
            except Exception as exc:
                errors = _repository_form_errors(exc=exc, fields=_EDIT_FORM_FIELDS)
                if len(errors) == 0:
                    flash.add_flash(
                        session=auth.session,
                        message=_describe_failure(
                            exc=exc,
                            prefix="Error updating repository: ",
                            request_path=str(getattr(request, "path", "")),
                        ),
                        category=flash.CATEGORY_ERROR,
                    )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.repository_edit",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["repository"] = repository
        context["form_data"] = form_view
        context["errors"] = errors
        context["secret_refs"] = _list_secret_refs(
            db_session=db_session, user_id=auth.user_id
        )
        response = _render(
            template_name="projects/repositories/edit.html",
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


def handle_repository_delete(request: Request) -> Response:
    """
        ``POST /projects/{project_id}/repositories/{repository_id}/delete``.
        ``admin``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        repository_id = _coerce_int(
            raw=request.path_params.get("repository_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.repository_list", project_id=project_id
            )
            if project_id is not None
            else _url_for_module.url_for("projects.project_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if project_id is None or repository_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.project_list"
                ),
                message="Repository not found.",
                category=flash.CATEGORY_ERROR,
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

        repository_manager = _build_repository_manager(
            db_session=db_session
        )
        # The permission check above is for the project in the URL:
        # refuse repositories that belong to any other project.
        repo_resolved = _resolve_repository_or_redirect(
            auth=auth,
            repository_manager=repository_manager,
            project_id=project_id,
            repository_id=repository_id,
        )
        if isinstance(repo_resolved, RedirectResponse):
            return repo_resolved

        try:
            repository_manager.remove_repository(
                repository_id, auth.user_id
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.repository_list", project_id=project_id
                ),
                message="Repository removed successfully.",
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.repository_list", project_id=project_id
                ),
                message="Error removing repository: {}".format(
                    str(exc)
                ),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _handle_repository_action(
        *,
        request: Request,
        action_name: str,
        action_callable_name: str,
        success_truthy_message: str,
        success_falsey_message: Optional[str],
        success_falsey_category: str,
        error_message_prefix: str,
        describe_success: Optional[Callable[[Any], str]] = None
    ) -> Response:
    """
        Shared body for the ``test`` and ``fetch`` action
        handlers. Both follow the same shape: developer-gated;
        invokes a 1-arg method on RepositoryManager that may
        return a truthy/falsey result; redirects to the detail
        page with the appropriate flash.

        :param action_name: For diagnostic / endpoint-name use.
        :param action_callable_name: Method name on
                                     RepositoryManager (e.g.
                                     ``"test_connectivity"``).
        :param success_truthy_message: Flash message when the
                                       method returns truthy or
                                       returns no value.
        :param success_falsey_message: Flash message when the
                                       method returns False
                                       explicitly. ``None`` to
                                       skip the falsey path
                                       (e.g. fetch never
                                       reports failure that way).
        :param success_falsey_category: Flash category for the
                                        falsey case.
        :param error_message_prefix: Prefix for exception flashes
                                     (e.g. ``"Error testing
                                     repository: "``).
        :param describe_success: Optional ``(result) -> message`` used
                                 instead of ``success_truthy_message``
                                 (fetch reports what it found).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(
            raw=request.path_params.get("project_id", None)
        )
        repository_id = _coerce_int(
            raw=request.path_params.get("repository_id", None)
        )
        single_form = _parse_form_or_empty(request=request)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.repository_list", project_id=project_id
            )
            if project_id is not None
            else _url_for_module.url_for("projects.project_list"),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(
                response=csrf_redirect, session=auth.session
            )
            return csrf_redirect

        if project_id is None or repository_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.project_list"
                ),
                message="Repository not found.",
                category=flash.CATEGORY_ERROR,
            )
            return response

        project_manager = _build_project_manager(db_session=db_session)
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

        detail_url = _url_for_module.url_for(
            "projects.repository_detail",
            project_id=project_id,
            repository_id=repository_id,
        )

        # Test and fetch talk to the remote, so the manager must be able
        # to read the repository's credential secret -- as the signed-in
        # user, under the secrets vault's access rules.
        repository_manager = _build_repository_manager(
            db_session=db_session, user_id=auth.user_id
        )
        # The permission check above is for the project in the URL:
        # refuse repositories that belong to any other project.
        repo_resolved = _resolve_repository_or_redirect(
            auth=auth,
            repository_manager=repository_manager,
            project_id=project_id,
            repository_id=repository_id,
        )
        if isinstance(repo_resolved, RedirectResponse):
            return repo_resolved

        action = getattr(repository_manager, action_callable_name)
        try:
            result = action(repository_id)
            if (
                success_falsey_message is not None
                and result is False
            ):
                response = _redirect_with_flash(
                    session=auth.session,
                    url=detail_url,
                    message=success_falsey_message,
                    category=success_falsey_category,
                )
                return response

            message = success_truthy_message
            if describe_success is not None:
                message = describe_success(result)
            response = _redirect_with_flash(
                session=auth.session,
                url=detail_url,
                message=message,
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            # Git and credential failures carry complete messages written
            # for the user (the manager scrubs whatever git printed);
            # anything else is logged under a reference, never shown.
            if _is_user_facing_error(exc=exc) is True:
                message = getattr(exc, "message", None) or str(exc)
            else:
                message = _describe_failure(
                    exc=exc,
                    prefix=error_message_prefix,
                    request_path=str(getattr(request, "path", "")),
                )
            response = _redirect_with_flash(
                session=auth.session,
                url=detail_url,
                message=message,
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_repository_test(request: Request) -> Response:
    """
        ``POST .../{repository_id}/test`` -- ping connectivity.
        ``developer``-gated. ``RepositoryManager.test_connectivity``
        returns a bool; True -> success flash, False -> error
        flash.
    """
    rtnval = _handle_repository_action(
        request=request,
        action_name="test",
        action_callable_name="test_connectivity",
        success_truthy_message="Repository connectivity test successful.",
        success_falsey_message="Repository connectivity test failed.",
        success_falsey_category=flash.CATEGORY_ERROR,
        error_message_prefix="Error testing repository: ",
    )
    return rtnval


def _describe_fetch(result: Any) -> str:
    """
        The fetch flash: what changed since the previous fetch and how
        many watches fired (see :mod:`watch_events`). Lazy-imports.
    """
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.watch_events import (  # noqa: E402
        describe_fetch,
    )
    rtnval = describe_fetch(repository=result)
    return rtnval


def handle_repository_fetch(request: Request) -> Response:
    """
        ``POST .../{repository_id}/fetch`` -- refresh remote
        metadata. ``developer``-gated. ``RepositoryManager.
        fetch_latest`` returns no truthy/falsey distinction.
    """
    rtnval = _handle_repository_action(
        request=request,
        action_name="fetch",
        action_callable_name="fetch_latest",
        success_truthy_message="Repository information updated.",
        success_falsey_message=None,
        success_falsey_category=flash.CATEGORY_INFO,
        error_message_prefix="Error fetching repository: ",
        describe_success=_describe_fetch,
    )
    return rtnval


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "projects.repository_list": handle_repository_list,
    "projects.repository_create": handle_repository_create,
    "projects.repository_detail": handle_repository_detail,
    "projects.repository_edit": handle_repository_edit,
    "projects.repository_delete": handle_repository_delete,
    "projects.repository_test": handle_repository_test,
    "projects.repository_fetch": handle_repository_fetch,
}


def register_repositories_routes(*, app: Any) -> None:
    """
        Attach the F2 repository routes to a webworks app and
        register their endpoint names with the url_for shim.
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
    "register_repositories_routes",
    "handle_repository_list",
    "handle_repository_create",
    "handle_repository_detail",
    "handle_repository_edit",
    "handle_repository_delete",
    "handle_repository_test",
    "handle_repository_fetch",
]
