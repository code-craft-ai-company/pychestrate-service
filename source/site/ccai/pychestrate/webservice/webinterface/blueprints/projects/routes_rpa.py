"""
.. module:: webinterface.blueprints.projects.routes_rpa
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: WebWorks-native consumer-facing UI for /projects/*/rpa
               (6-rpa-orchestration -- Robotic Process Automation).

.. moduleauthor:: Code Craft AI LLC

The RPA routes served under the projects blueprint:

* ``GET  /projects/{project_id}/rpa``                       -- jobs list
                                                              (status / spec
                                                              filter).
* ``GET  /projects/{project_id}/rpa/specs``                 -- spec list.
* ``GET  /projects/{project_id}/rpa/specs/create``          -- spec form
                                                              (developer).
* ``POST /projects/{project_id}/rpa/specs/create``          -- create spec.
* ``GET  /projects/{project_id}/rpa/specs/{spec_id}``       -- spec detail
                                                              + Run form.
* ``POST /projects/{project_id}/rpa/specs/{spec_id}/run``   -- trigger a
                                                              job with a
                                                              work packet
                                                              (developer).
* ``GET  /projects/{project_id}/rpa/jobs/{job_id}``         -- job detail.
* ``GET  /projects/{project_id}/rpa/jobs/{job_id}/logs``    -- job logs.
* ``POST /projects/{project_id}/rpa/jobs/{job_id}/cancel``  -- cancel
                                                              (developer).

Unlike the build pages, these handlers talk to the orchestration
service (:mod:`orchestration.rpa.service`) directly: an RPA job
triggered from the UI mints a signed envelope and dispatches it to a
pod. The consumer project id is carried as a string reference; the
service maps it onto the Layer-5 project UUID.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


import json
import logging

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
    _redirect_with_flash,
    _render,
    _resolve_authenticated_request,
)
from ccai.pychestrate.webservice.webinterface.blueprints.projects.routes import (
    PROJECTS_PATH,
    ProjectsFormError,
    _describe_failure,
    _is_user_facing_error,
    _require_project_permission_or_redirect,
    _resolve_project_or_redirect,
)


_rpa_ui_logger = logging.getLogger("pychestrate.ui.rpa")

_ROUTE_TABLE = (
    ("projects.rpa_list", "/{project_id}/rpa", ("GET",)),
    ("projects.rpa_spec_list", "/{project_id}/rpa/specs", ("GET",)),
    ("projects.rpa_spec_create", "/{project_id}/rpa/specs/create", ("GET", "POST")),
    ("projects.rpa_spec_detail", "/{project_id}/rpa/specs/{spec_id}", ("GET",)),
    ("projects.rpa_run", "/{project_id}/rpa/specs/{spec_id}/run", ("POST",)),
    ("projects.rpa_detail", "/{project_id}/rpa/jobs/{job_id}", ("GET",)),
    ("projects.rpa_logs", "/{project_id}/rpa/jobs/{job_id}/logs", ("GET",)),
    ("projects.rpa_cancel", "/{project_id}/rpa/jobs/{job_id}/cancel", ("POST",)),
)

#: Status vocabulary offered by the list filter.
RPA_STATUS_CHOICES = (
    "pending", "dispatching", "running", "succeeded", "failed", "timeout", "cancelled",
)


# ---------------------------------------------------------------------------
# Lazy-import builder seams (test-patchable)
# ---------------------------------------------------------------------------


def _build_project_manager(*, db_session: Any) -> Any:
    from ccai.pychestrate.webservice.webinterface.blueprints.projects.project_access import (  # noqa: E402
        build_access_aware_project_manager,
    )
    rtnval = build_access_aware_project_manager(db_session=db_session)
    return rtnval


def _build_rpa_service() -> Any:
    """
        The orchestration RPA service module. Lazy so the blueprint
        stays importable when the orchestration package is unavailable
        and so tests can substitute a fake.
    """
    from ccai.pychestrate.webservice.orchestration.rpa import (  # noqa: E402
        service as rpa_service,
    )
    rtnval = rpa_service
    return rtnval


def _resolve_candidates(*, db_session: Any, project_id: str, target_pod_id: Optional[str]) -> List[Any]:
    from ccai.pychestrate.webservice.orchestration.rpa.candidates import (  # noqa: E402
        resolve_dispatch_candidates,
    )
    rtnval = resolve_dispatch_candidates(
        db_session=db_session, project_id=project_id, target_pod_id=target_pod_id,
    )
    return rtnval


def _pod_names(*, db_session: Any) -> Dict[str, str]:
    """
        Map every defined pod's id to its name, for pickers that must
        not ask operators to type raw pod UUIDs.
    """
    try:
        from ccai.pychestrate.webservice.pods.models import PodDefinition  # noqa: E402
        rows = db_session.query(PodDefinition).filter(PodDefinition.deleted_at.is_(None)).all()
    except Exception:
        return {}
    rtnval = {str(row.pod_id): str(row.pod_name) for row in rows}
    return rtnval


def _pod_choices(*, db_session: Any, pod_ids: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """
        ``[{"pod_id", "label"}]`` for a pod picker, sorted by label.
        ``pod_ids`` limits the choices (e.g. to pods able to run a
        job); ``None`` lists every defined pod.
    """
    names = _pod_names(db_session=db_session)
    ids = list(names.keys()) if pod_ids is None else list(dict.fromkeys(str(p) for p in pod_ids))
    rtnval = []
    for pod_id in ids:
        name = names.get(pod_id, "")
        label = "{} ({})".format(name, pod_id[:8]) if len(name) > 0 else pod_id
        rtnval.append({"pod_id": pod_id, "label": label})
    rtnval.sort(key=lambda choice: choice["label"].lower())
    return rtnval


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _coerce_int(*, raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        rtnval = int(str(raw))
    except (TypeError, ValueError):
        rtnval = None
    return rtnval


def _coerce_int_with_default(*, raw: Any, default: int) -> int:
    value = _coerce_int(raw=raw)
    rtnval = value if value is not None else default
    return rtnval


def _parse_pagination_params(*, request: Request) -> Dict[str, int]:
    page = _coerce_int_with_default(raw=request.query_params.get("page", None), default=1)
    per_page = _coerce_int_with_default(raw=request.query_params.get("per_page", None), default=20)
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 20
    if per_page > 100:
        per_page = 100
    rtnval = {"page": page, "per_page": per_page}
    return rtnval


def _total_pages_from_count(*, total: int, per_page: int) -> int:
    if per_page <= 0:
        return 1
    rtnval = (total + per_page - 1) // per_page
    if rtnval < 1:
        rtnval = 1
    return rtnval


def _parse_json_object(*, raw: str, field_label: str) -> Dict[str, Any]:
    """
        Parse a JSON object from a form textarea. Empty means ``{}``.

        :raises: ValueError with a user-facing message.
    """
    text = str(raw or "").strip()
    if len(text) == 0:
        return {}
    try:
        decoded = json.loads(text)
    except ValueError as exc:
        raise ProjectsFormError("{} must be valid JSON: {}".format(field_label, str(exc))) from None
    if not isinstance(decoded, dict):
        raise ProjectsFormError("{} must be a JSON object.".format(field_label))
    rtnval = decoded
    return rtnval


def _pretty_json(value: Any) -> str:
    try:
        rtnval = json.dumps(value, indent=2, sort_keys=True)
    except (TypeError, ValueError):
        rtnval = "{}"
    return rtnval


def _resolve_view_authorized_project(*, request: Request, auth: _AuthResolution) -> Any:
    project_id = _coerce_int(raw=request.path_params.get("project_id", None))
    project_manager = _build_project_manager(db_session=auth.db_session)
    resolved = _resolve_project_or_redirect(
        auth=auth, project_manager=project_manager, project_id=project_id,
    )
    if isinstance(resolved, RedirectResponse):
        return (project_id, project_manager, resolved)
    project = resolved
    deny_response = _require_project_permission_or_redirect(
        project_manager=project_manager,
        auth=auth,
        project_id=project_id,
        permission="view",
        deny_redirect_url=_url_for_module.url_for("projects.project_list"),
        deny_message="You do not have permission to view this project.",
    )
    if deny_response is not None:
        return (project_id, project_manager, deny_response)
    return (project_id, project_manager, project)


def _can_manage(*, project_manager: Any, project_id: int, user_id: str) -> bool:
    try:
        rtnval = project_manager.check_permission(project_id, user_id, "developer")
    except Exception:
        rtnval = False
    return rtnval


def _resolve_spec_or_redirect(*, auth: _AuthResolution, rpa: Any, project_id: int, spec_id: str) -> Any:
    not_found = _url_for_module.url_for("projects.rpa_spec_list", project_id=project_id)
    try:
        spec = rpa.get_spec(db_session=auth.db_session, spec_id=spec_id)
    except Exception:
        spec = None
    if spec is None or str(spec.project_id) != str(project_id):
        rtnval = _redirect_with_flash(
            session=auth.session, url=not_found,
            message="RPA specification not found.", category=flash.CATEGORY_ERROR,
        )
        return rtnval
    return spec


def _resolve_job_or_redirect(*, auth: _AuthResolution, rpa: Any, project_id: int, job_id: str) -> Any:
    not_found = _url_for_module.url_for("projects.rpa_list", project_id=project_id)
    try:
        job = rpa.get_job(db_session=auth.db_session, job_id=job_id)
    except Exception:
        job = None
    if job is None or str(job.project_id) != str(project_id):
        rtnval = _redirect_with_flash(
            session=auth.session, url=not_found,
            message="RPA job not found.", category=flash.CATEGORY_ERROR,
        )
        return rtnval
    return job


def _status_filter(*, rpa: Any, value: Optional[str]) -> Any:
    if value is None or len(value) == 0:
        return None
    try:
        from ccai.pychestrate.webservice.orchestration.rpa.models import RpaJobStatus  # noqa: E402
        rtnval = RpaJobStatus(value)
    except Exception:
        rtnval = None
    return rtnval


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def handle_rpa_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/rpa`` -- jobs list.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]
        status = request.query_params.get("status", None) or None
        spec_id = request.query_params.get("spec_id", None) or None

        rpa = _build_rpa_service()
        listing = rpa.list_jobs(
            db_session=db_session,
            project_id=str(project_id),
            spec_id=spec_id,
            status=_status_filter(rpa=rpa, value=status),
            offset=offset,
            limit=params["per_page"],
        )
        specs, _spec_total = rpa.list_specs(db_session=db_session, project_id=str(project_id), limit=100)
        can_manage = _can_manage(
            project_manager=project_manager, project_id=project_id, user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.rpa_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["jobs"] = list(listing.jobs)
        context["specs"] = list(specs)
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total"] = listing.total
        context["total_pages"] = _total_pages_from_count(
            total=listing.total, per_page=params["per_page"],
        )
        context["selected_status"] = status
        context["selected_spec_id"] = spec_id
        context["status_choices"] = list(RPA_STATUS_CHOICES)

        response = _render(template_name="projects/rpa/list.html", context=context)
        _attach_session_to_response(response=response, session=auth.session)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_rpa_spec_list(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/rpa/specs``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        params = _parse_pagination_params(request=request)
        offset = (params["page"] - 1) * params["per_page"]
        rpa = _build_rpa_service()
        specs, total = rpa.list_specs(
            db_session=db_session, project_id=str(project_id), offset=offset, limit=params["per_page"],
        )
        can_manage = _can_manage(
            project_manager=project_manager, project_id=project_id, user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.rpa_spec_list",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["specs"] = list(specs)
        context["can_manage"] = can_manage
        context["page"] = params["page"]
        context["per_page"] = params["per_page"]
        context["total"] = total
        context["total_pages"] = _total_pages_from_count(total=total, per_page=params["per_page"])

        response = _render(template_name="projects/rpa/spec_list.html", context=context)
        _attach_session_to_response(response=response, session=auth.session)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _render_rpa_spec_create_form(
        *,
        auth: _AuthResolution,
        project: Any,
        job_types: List[Any],
        form_data: Optional[MultiFormView],
        status_code: int = 200
    ) -> HTMLResponse:
    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.rpa_spec_create",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["project"] = project
    context["job_types"] = job_types
    context["form_data"] = form_data
    context["pod_choices"] = _pod_choices(db_session=auth.db_session)
    response = _render(
        template_name="projects/rpa/spec_create.html", context=context, status_code=status_code,
    )
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_rpa_spec_create(request: Request) -> Response:
    """
        ``GET|POST /projects/{project_id}/rpa/specs/create``.
        ``developer``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(raw=request.path_params.get("project_id", None))
        project_manager = _build_project_manager(db_session=db_session)
        resolved = _resolve_project_or_redirect(
            auth=auth, project_manager=project_manager, project_id=project_id,
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
                "projects.project_detail", project_id=project_id,
            ),
        )
        if deny_response is not None:
            return deny_response

        rpa = _build_rpa_service()
        job_types = [
            t for t in rpa.list_job_types(db_session=db_session)
            if getattr(getattr(t, "state", None), "value", "active") == "active"
        ]
        method = request.method.upper()

        if method == "GET":
            return _render_rpa_spec_create_form(
                auth=auth, project=project, job_types=job_types, form_data=None,
            )

        single_form = _parse_form_or_empty(request=request)
        multi_form = _parse_form_multi(request=request)
        form_view = MultiFormView(data=multi_form)

        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form,
            session=auth.session,
            fallback_url=_url_for_module.url_for(
                "projects.rpa_spec_create", project_id=project_id,
            ),
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        name = str(single_form.get("name", "")).strip()
        type_id = str(single_form.get("type_id", "")).strip()
        version_selector = str(single_form.get("version_selector", "")).strip() or "latest-active"
        target_pod_id = str(single_form.get("target_pod_id", "")).strip() or None
        timeout_raw = str(single_form.get("timeout_minutes", "")).strip()
        description = str(single_form.get("description", "")).strip()

        try:
            default_packet = _parse_json_object(
                raw=str(single_form.get("default_packet", "")), field_label="Default packet",
            )
            required_capabilities = [
                c.strip() for c in str(single_form.get("required_capabilities", "")).split(",")
                if len(c.strip()) > 0
            ]
            timeout_minutes = _coerce_int(raw=timeout_raw) if len(timeout_raw) > 0 else None
            inputs = rpa.RpaSpecInputs(
                name=name,
                type_id=type_id,
                version_selector=version_selector,
                default_packet=default_packet,
                target_pod_id=target_pod_id,
                required_capabilities=tuple(required_capabilities),
                timeout_minutes=timeout_minutes,
                description=description,
            )
            spec = rpa.create_spec(
                db_session=db_session, project_id=str(project_id), inputs=inputs,
                actor_id=auth.user_id,
            )
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for(
                    "projects.rpa_spec_detail", project_id=project_id, spec_id=spec.spec_id,
                ),
                message='RPA specification "{}" created successfully.'.format(name),
                category=flash.CATEGORY_SUCCESS,
            )
            return response
        except ValueError as exc:
            flash.add_flash(session=auth.session, message=_describe_failure(exc=exc, prefix="", request_path=str(getattr(request, "path", ""))), category=flash.CATEGORY_ERROR)
        except Exception as exc:
            flash.add_flash(
                session=auth.session,
                message=_describe_failure(exc=exc, prefix="Error creating RPA specification: ", request_path=str(getattr(request, "path", ""))),
                category=flash.CATEGORY_ERROR,
            )

        return _render_rpa_spec_create_form(
            auth=auth, project=project, job_types=job_types, form_data=form_view, status_code=400,
        )
    finally:
        try:
            db_session.close()
        except Exception:
            pass


NO_ELIGIBLE_POD_MESSAGE: str = (
    "No pod can run this job yet. A pod needs at least one enrolled client "
    "registered to it (Fleet > Pods), and it must offer the capabilities this "
    "specification and its job type require."
)

REPLAY_MESSAGE: str = (
    "An identical run of this specification was submitted less than a minute "
    "ago, so no new job was started."
)


def _run_availability(*, db_session: Any, project_id: int, spec: Any) -> Dict[str, Any]:
    """
        Which pods could run the specification right now, for the Run
        form: ``{"pods": [{"pod_id", "label"}], "blocked_reason": str}``.
        ``blocked_reason`` is empty when at least one pod is eligible.
    """
    try:
        candidates = _resolve_candidates(
            db_session=db_session, project_id=str(project_id), target_pod_id=spec.target_pod_id,
        )
    except Exception as exc:
        _rpa_ui_logger.warning(
            "pychestrate.ui.rpa.candidates_unavailable spec_id=%s error=%s", spec.spec_id, exc,
        )
        rtnval = {"pods": [], "blocked_reason": ""}
        return rtnval
    pod_ids = [str(getattr(candidate, "pod_id", "")) for candidate in candidates]
    rtnval = {
        "pods": _pod_choices(db_session=db_session, pod_ids=[p for p in pod_ids if len(p) > 0]),
        "blocked_reason": "" if len(candidates) > 0 else NO_ELIGIBLE_POD_MESSAGE,
    }
    return rtnval


def _render_spec_detail(
        *,
        auth: _AuthResolution,
        rpa: Any,
        project: Any,
        project_id: int,
        project_manager: Any,
        spec: Any,
        run_packet_json: Optional[str] = None,
        run_errors: Optional[List[str]] = None,
        replay_job: Any = None,
        selected_pod_id: str = "",
        status_code: int = 200
    ) -> HTMLResponse:
    """
        Render the specification page. The run handler re-renders it
        (instead of redirecting) when a run fails or is a replay, so the
        packet the operator typed is kept and the reason is shown next
        to the form.
    """
    db_session = auth.db_session
    recent = rpa.list_jobs(
        db_session=db_session, project_id=str(project_id), spec_id=spec.spec_id, offset=0, limit=10,
    )
    can_manage = _can_manage(
        project_manager=project_manager, project_id=project_id, user_id=auth.user_id,
    )

    flashes = flash.consume_flashes(session=auth.session)
    context = _build_default_template_context(
        session=auth.session,
        request_endpoint="projects.rpa_spec_detail",
        flashes=flashes,
        csrf_token=auth.csrf_token,
    )
    context["project"] = project
    context["spec"] = spec
    context["recent_jobs"] = list(recent.jobs)
    context["can_manage"] = can_manage
    # Secret-declared paths are never shown. The display gets the
    # redacted packet; the run form leaves out every top-level key
    # that holds a secret, so the stored default applies unless the
    # operator types a new value (packets merge at the top level).
    from ccai.pychestrate.webservice.orchestration.rpa import packet as _rpa_packet  # noqa: E402

    secret_fields = list(getattr(spec, "secret_fields", ()) or ())
    secret_keys = _rpa_packet.secret_top_level_keys(secret_fields=secret_fields)
    context["default_packet_json"] = _pretty_json(
        _rpa_packet.redact_packet(packet=dict(spec.default_packet), secret_fields=secret_fields)
    )
    if run_packet_json is None:
        run_packet_json = _pretty_json(
            {k: v for k, v in dict(spec.default_packet).items() if k not in secret_keys}
        )
    context["run_packet_json"] = run_packet_json
    context["secret_packet_keys"] = secret_keys
    context["packet_schema_json"] = (
        _pretty_json(dict(spec.packet_schema)) if spec.packet_schema else ""
    )
    availability = (
        _run_availability(db_session=db_session, project_id=project_id, spec=spec)
        if can_manage
        else {"pods": [], "blocked_reason": ""}
    )
    context["run_pods"] = availability["pods"]
    context["run_blocked_reason"] = availability["blocked_reason"]
    context["run_errors"] = list(run_errors or [])
    context["run_selected_pod_id"] = selected_pod_id
    context["replay_job"] = replay_job
    context["replay_message"] = REPLAY_MESSAGE if replay_job is not None else ""

    response = _render(
        template_name="projects/rpa/spec_detail.html", context=context, status_code=status_code,
    )
    _attach_session_to_response(response=response, session=auth.session)
    return response


def handle_rpa_spec_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/rpa/specs/{spec_id}``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        rpa = _build_rpa_service()
        spec_id = str(request.path_params.get("spec_id", ""))
        spec_or_redirect = _resolve_spec_or_redirect(
            auth=auth, rpa=rpa, project_id=project_id, spec_id=spec_id,
        )
        if isinstance(spec_or_redirect, RedirectResponse):
            return spec_or_redirect
        spec = spec_or_redirect

        response = _render_spec_detail(
            auth=auth, rpa=rpa, project=project, project_id=project_id,
            project_manager=project_manager, spec=spec,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _packet_error_lines(*, exc: Exception, request_path: str = "") -> List[str]:
    """
        One line per problem for the run form's error list: each schema
        issue with its path, otherwise the error's own message -- or, for
        an error not written for users, a log reference instead of its
        text (PRJ-29).
    """
    issues = getattr(exc, "issues", None)
    if issues:
        rtnval = ["{}: {}".format(path or "/", message) for path, message in issues]
        return rtnval
    if _is_user_facing_error(exc=exc) is not True:
        rtnval = [_describe_failure(exc=exc, prefix="", request_path=request_path)]
        return rtnval
    text = str(exc).strip()
    first_line = text.splitlines()[0] if len(text) > 0 else "The job could not be started."
    rtnval = [first_line]
    return rtnval


def handle_rpa_run(request: Request) -> Response:
    """
        ``POST /projects/{project_id}/rpa/specs/{spec_id}/run`` --
        trigger a job with the submitted work packet.
        ``developer``-gated.

        On success, redirect to the new job. When the packet is invalid,
        no pod can run the job, or the dispatcher refuses, re-render the
        specification page with the typed packet and the reason (422).
        When an identical run was submitted inside the idempotency window,
        re-render with a notice, a link to that job and a "Run anyway"
        button (which posts ``allow_duplicate=1``).
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(raw=request.path_params.get("project_id", None))
        spec_id = str(request.path_params.get("spec_id", ""))
        single_form = _parse_form_or_empty(request=request)

        fallback = (
            _url_for_module.url_for("projects.rpa_list", project_id=project_id)
            if project_id is not None
            else _url_for_module.url_for("projects.project_list")
        )
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form, session=auth.session, fallback_url=fallback,
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        if project_id is None:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("projects.project_list"),
                message="Project not found.",
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
                "projects.project_detail", project_id=project_id,
            ),
        )
        if deny_response is not None:
            return deny_response

        rpa = _build_rpa_service()
        spec_or_redirect = _resolve_spec_or_redirect(
            auth=auth, rpa=rpa, project_id=project_id, spec_id=spec_id,
        )
        if isinstance(spec_or_redirect, RedirectResponse):
            return spec_or_redirect
        spec = spec_or_redirect
        project = project_manager.get_project(project_id)

        raw_packet = str(single_form.get("work_packet", ""))
        selected_pod_id = str(single_form.get("target_pod", "") or "").strip()
        allow_duplicate = str(single_form.get("allow_duplicate", "")).strip() in ("1", "true", "on")

        def _rerender(*, errors: List[str], replay_job: Any = None, status_code: int = 422) -> HTMLResponse:
            rtnval = _render_spec_detail(
                auth=auth, rpa=rpa, project=project, project_id=project_id,
                project_manager=project_manager, spec=spec, run_packet_json=raw_packet,
                run_errors=errors, replay_job=replay_job, selected_pod_id=selected_pod_id,
                status_code=status_code,
            )
            return rtnval

        try:
            work_packet = _parse_json_object(raw=raw_packet, field_label="Work packet")
            # Check the packet before choosing pods, so a bad packet is
            # reported as such even when no pod is available.
            rpa.check_trigger_packet(
                db_session=db_session, project_id=str(project_id), spec_id=spec_id,
                work_packet=work_packet,
            )
            candidates = _resolve_candidates(
                db_session=db_session, project_id=str(project_id), target_pod_id=spec.target_pod_id,
            )
            if len(selected_pod_id) > 0:
                candidates = [c for c in candidates if str(getattr(c, "pod_id", "")) == selected_pod_id]
            if len(candidates) == 0:
                raise ProjectsFormError(NO_ELIGIBLE_POD_MESSAGE)
            project_slug = str(getattr(project_manager, "slug", "") or getattr(spec, "name", ""))
            aspect_kwargs: Dict[str, Any] = {
                "actor_id": auth.user_id,
                "candidates": candidates,
                "project_slug": project_slug,
                "trigger_cause": {"kind": "manual", "via": "web"},
            }
            if allow_duplicate is True:
                aspect_kwargs["idempotency_window_seconds"] = 0
            aspects = rpa.RpaTriggerAspects(**aspect_kwargs)
            job = rpa.trigger_job(
                db_session=db_session, project_id=str(project_id), spec_id=spec_id,
                work_packet=work_packet, aspects=aspects,
            )
        except Exception as exc:
            response = _rerender(errors=_packet_error_lines(
                exc=exc, request_path=str(getattr(request, "path", "")),
            ))
            return response

        if getattr(job, "replayed", False) is True:
            response = _rerender(errors=[], replay_job=job, status_code=200)
            return response

        response = _redirect_with_flash(
            session=auth.session,
            url=_url_for_module.url_for(
                "projects.rpa_detail", project_id=project_id, job_id=job.job_id,
            ),
            message="RPA job {} triggered successfully.".format(job.job_id[:8]),
            category=flash.CATEGORY_SUCCESS,
        )
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def _job_names(*, db_session: Any, job: Any) -> Dict[str, Optional[str]]:
    """
        The people and machines behind an RPA job, by name instead of
        UUID (PRJ-33): who triggered it, and the pod and client that ran
        it. A name that cannot be found is None (the page then shows the
        id).

        :param db_session: Open SQLAlchemy session.
        :param job: The RPA job view.

        :returns: ``{"triggered_by", "pod", "client"}``.
    """
    rtnval: Dict[str, Optional[str]] = {"triggered_by": None, "pod": None, "client": None}
    lookups = (
        ("triggered_by", "ccai.pychestrate.core.orm", "User", "id",
         getattr(job, "triggered_by_id", None), ("display_name", "login")),
        ("pod", "ccai.pychestrate.webservice.pods.models", "PodDefinition", "pod_id",
         getattr(job, "pod_id", None), ("pod_name",)),
        ("client", "ccai.pychestrate.webservice.clients.models", "Client", "client_id",
         getattr(job, "client_id", None), ("pod_name",)),
    )
    for key, module_name, model_name, id_column, raw_id, name_columns in lookups:
        if raw_id is None or len(str(raw_id)) == 0:
            continue
        try:
            import importlib  # noqa: E402
            import uuid as uuid_module  # noqa: E402
            model = getattr(importlib.import_module(module_name), model_name)
            row = db_session.query(model).filter(
                getattr(model, id_column) == uuid_module.UUID(str(raw_id))
            ).first()
        except Exception:
            row = None
        if row is None:
            continue
        for column in name_columns:
            value = getattr(row, column, None)
            if value:
                rtnval[key] = str(value)
                break
    if rtnval["client"] is not None:
        rtnval["client"] = "client of {}".format(rtnval["client"])
    return rtnval


def handle_rpa_detail(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/rpa/jobs/{job_id}``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        rpa = _build_rpa_service()
        job_id = str(request.path_params.get("job_id", ""))
        job_or_redirect = _resolve_job_or_redirect(
            auth=auth, rpa=rpa, project_id=project_id, job_id=job_id,
        )
        if isinstance(job_or_redirect, RedirectResponse):
            return job_or_redirect
        job = job_or_redirect

        can_manage = _can_manage(
            project_manager=project_manager, project_id=project_id, user_id=auth.user_id,
        )

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.rpa_detail",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["job"] = job
        context["can_manage"] = can_manage
        context["work_packet_json"] = _pretty_json(dict(job.work_packet))
        context["is_active"] = job.status.value in ("pending", "dispatching", "running")
        context["job_names"] = _job_names(db_session=db_session, job=job)

        response = _render(template_name="projects/rpa/detail.html", context=context)
        _attach_session_to_response(response=response, session=auth.session)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_rpa_logs(request: Request) -> Response:
    """
        ``GET /projects/{project_id}/rpa/jobs/{job_id}/logs``.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id, project_manager, project_or_redirect = (
            _resolve_view_authorized_project(request=request, auth=auth)
        )
        if isinstance(project_or_redirect, RedirectResponse):
            return project_or_redirect
        project = project_or_redirect

        rpa = _build_rpa_service()
        job_id = str(request.path_params.get("job_id", ""))
        job_or_redirect = _resolve_job_or_redirect(
            auth=auth, rpa=rpa, project_id=project_id, job_id=job_id,
        )
        if isinstance(job_or_redirect, RedirectResponse):
            return job_or_redirect
        job = job_or_redirect

        logs = rpa.get_job_log_text(db_session=db_session, job_id=job_id)

        flashes = flash.consume_flashes(session=auth.session)
        context = _build_default_template_context(
            session=auth.session,
            request_endpoint="projects.rpa_logs",
            flashes=flashes,
            csrf_token=auth.csrf_token,
        )
        context["project"] = project
        context["job"] = job
        context["logs"] = logs
        context["is_active"] = job.status.value in ("pending", "dispatching", "running")

        response = _render(template_name="projects/rpa/logs.html", context=context)
        _attach_session_to_response(response=response, session=auth.session)
        return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


def handle_rpa_cancel(request: Request) -> Response:
    """
        ``POST /projects/{project_id}/rpa/jobs/{job_id}/cancel``.
        ``developer``-gated.
    """
    auth = _resolve_authenticated_request(request=request)
    if auth.redirect_response is not None:
        return auth.redirect_response

    db_session = auth.db_session
    try:
        project_id = _coerce_int(raw=request.path_params.get("project_id", None))
        job_id = str(request.path_params.get("job_id", ""))
        single_form = _parse_form_or_empty(request=request)

        fallback = (
            _url_for_module.url_for("projects.rpa_list", project_id=project_id)
            if project_id is not None
            else _url_for_module.url_for("projects.project_list")
        )
        csrf_redirect = auth_guard.enforce_csrf_or_redirect(
            form=single_form, session=auth.session, fallback_url=fallback,
        )
        if csrf_redirect is not None:
            _attach_session_to_response(response=csrf_redirect, session=auth.session)
            return csrf_redirect

        if project_id is None or len(job_id) == 0:
            response = _redirect_with_flash(
                session=auth.session,
                url=_url_for_module.url_for("projects.project_list"),
                message="RPA job not found.",
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
                "projects.project_detail", project_id=project_id,
            ),
        )
        if deny_response is not None:
            return deny_response

        detail_url = _url_for_module.url_for(
            "projects.rpa_detail", project_id=project_id, job_id=job_id,
        )
        rpa = _build_rpa_service()
        job_or_redirect = _resolve_job_or_redirect(
            auth=auth, rpa=rpa, project_id=project_id, job_id=job_id,
        )
        if isinstance(job_or_redirect, RedirectResponse):
            return job_or_redirect
        try:
            view = rpa.cancel_job(db_session=db_session, job_id=job_id, actor_id=auth.user_id)
            message = "RPA job cancelled."
            if getattr(view, "status", None) != "cancelled":
                message = ("Cancel requested. The job stops when its pod picks up the "
                           "cancel on its next heartbeat.")
            response = _redirect_with_flash(
                session=auth.session, url=detail_url,
                message=message, category=flash.CATEGORY_SUCCESS,
            )
            return response
        except Exception as exc:
            response = _redirect_with_flash(
                session=auth.session, url=detail_url,
                message=_describe_failure(exc=exc, prefix="Error cancelling RPA job: ", request_path=str(getattr(request, "path", ""))),
                category=flash.CATEGORY_ERROR,
            )
            return response
    finally:
        try:
            db_session.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Watch action bridge
# ---------------------------------------------------------------------------


def build_watch_rpa_trigger(*, db_session: Any) -> Callable[..., Any]:
    """
        Build the ``trigger_rpa_job`` callable the core
        :class:`WatchManager` invokes: ``(spec_id, work_packet, user_id)``
        resolves the specification, picks eligible pods, and triggers
        the job with ``trigger_cause = watch``. When the watch's
        ``project_id`` is given, a specification from any other project
        is refused.
    """
    def _trigger(
            *, spec_id: str, work_packet: Dict[str, Any], user_id: str,
            project_id: Optional[Any] = None
        ) -> Any:
        rpa = _build_rpa_service()
        spec = rpa.get_spec(db_session=db_session, spec_id=spec_id)
        if project_id is not None and str(spec.project_id) != str(project_id):
            # A watch may only start RPA jobs in its own project.
            raise ProjectsFormError(
                "RPA specification {} is not part of project {}.".format(spec_id, project_id)
            )
        candidates = _resolve_candidates(
            db_session=db_session, project_id=str(spec.project_id), target_pod_id=spec.target_pod_id,
        )
        aspects = rpa.RpaTriggerAspects(
            actor_id=user_id,
            candidates=candidates,
            project_slug=spec.name,
            trigger_cause={"kind": "watch"},
            idempotency_window_seconds=0,
        )
        rtnval = rpa.trigger_job(
            db_session=db_session, project_id=str(spec.project_id), spec_id=spec_id,
            work_packet=dict(work_packet or {}), aspects=aspects,
        )
        return rtnval
    return _trigger


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


_HANDLERS_BY_ENDPOINT: Dict[str, Callable[[Request], Response]] = {
    "projects.rpa_list": handle_rpa_list,
    "projects.rpa_spec_list": handle_rpa_spec_list,
    "projects.rpa_spec_create": handle_rpa_spec_create,
    "projects.rpa_spec_detail": handle_rpa_spec_detail,
    "projects.rpa_run": handle_rpa_run,
    "projects.rpa_detail": handle_rpa_detail,
    "projects.rpa_logs": handle_rpa_logs,
    "projects.rpa_cancel": handle_rpa_cancel,
}


def register_rpa_routes(*, app: Any) -> None:
    """
        Attach the RPA project routes to a webworks app.
    """
    for endpoint_name, relative_path, methods in _ROUTE_TABLE:
        full_path = PROJECTS_PATH + relative_path
        _url_for_module.register_endpoint(endpoint=endpoint_name, pattern=full_path)
        handler = _HANDLERS_BY_ENDPOINT[endpoint_name]
        app.attach_route(full_path, methods=list(methods))(handler)
    return


__all__ = [
    "register_rpa_routes",
    "handle_rpa_list",
    "handle_rpa_spec_list",
    "handle_rpa_spec_create",
    "handle_rpa_spec_detail",
    "handle_rpa_run",
    "handle_rpa_detail",
    "handle_rpa_logs",
    "handle_rpa_cancel",
]
