"""
.. module:: ccai.testshared.factories.webui.template_contexts
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Variable-name -> fixture registry for the consumer
               web UI templates.

.. moduleauthor:: Code Craft AI LLC

The render-smoke suite asks jinja which top-level variables each
template reads (``jinja2.meta.find_undeclared_variables``) and
builds a context for exactly those names from this registry. The
registry mirrors what the route handlers *actually* pass: manager
response dataclasses for domain objects, ``MultiFormView`` for
``form_data``, ``(category, message)`` tuples for ``flashes``.

A name that is not in the registry is a test failure -- the
smoke test refuses to guess, because a guessed value would hide
exactly the drift the suite exists to catch. Add the name here
with the type the handler passes.

Some names mean different things in different blueprints
(``specs`` is a ``BuildSpecResponse`` list under
``projects/builds/`` and a ``TestSpecResponse`` list under
``projects/tests/``). :data:`TEMPLATE_PREFIX_OVERRIDES` resolves
those by template-path prefix; longest prefix wins.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from typing import Any, Callable, Dict, List, Optional

from ccai.testshared.factories.webui.dataclass_fixtures import (
    FIXTURE_DATE,
    FIXTURE_DATETIME,
    MODE_POPULATED,
    MODE_SPARSE,
    build_fixture,
    build_fixture_list,
)

from ccai.pychestrate.core.managers.allocation_manager import (
    AllocationResponse,
    ReservationResponse,
)
from ccai.pychestrate.core.managers.audit_logger import AuditLogEntry
from ccai.pychestrate.core.managers.build_manager import (
    BuildArtifactResponse,
    BuildResponse,
    BuildSpecResponse,
)
from ccai.pychestrate.core.managers.global_variable_store import (
    GlobalVariableResponse,
    VariableChangeLog,
)
from ccai.pychestrate.core.managers.health_monitor import (
    HealthCheckConfigResponse,
    HealthTransitionResponse,
)
from ccai.pychestrate.core.managers.infrastructure_manager import (
    InfraJobResponse,
    InfraSpecResponse,
)
from ccai.pychestrate.core.managers.ip_pool_manager import (
    IPAllocationResponse,
    IPPoolResponse,
)
from ccai.pychestrate.core.managers.project_manager import (
    ProjectMemberResponse,
    ProjectResponse,
)
from ccai.pychestrate.core.managers.release_manager import (
    MergeEventResponse,
    PhaseEventResponse,
    PipelineRunResponse,
    PullEventResponse,
    ReleaseArtifactResponse,
    ReleaseBranchResponse,
    ReleaseChannelResponse,
    ReleaseEventResponse,
    ReleasePipelineResponse,
    ReleaseResponse,
    ReleaseScheduleResponse,
)
from ccai.pychestrate.core.managers.release_template_manager import (
    ReleaseTemplateResponse,
)
from ccai.pychestrate.core.managers.repository_manager import (
    RepositoryResponse,
)
from ccai.pychestrate.core.managers.resource_manager import (
    ResourcePoolResponse,
    ResourceResponse,
    TagResponse,
)
from ccai.pychestrate.core.managers.secret_manager import (
    SecretMetadataResponse,
    SecretScopeResponse,
)
from ccai.pychestrate.core.managers.test_manager import (
    TestCaseResult,
    TestJobResponse,
    TestSpecResponse,
)
from ccai.pychestrate.core.managers.user_manager import UserResponse
from ccai.pychestrate.core.managers.watch_manager import (
    WatchResponse,
    WatchTriggerLog,
)

from ccai.pychestrate.webservice.clients.enrollment.service import TokenView
from ccai.pychestrate.webservice.webinterface.blueprints.config.identity_admin import (
    AdminPermissionView,
    AdminRoleView,
    AdminUserView,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes import (
    MultiFormView,
)
from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_sessions import (
    _SessionRow,
)


Builder = Callable[[str], Any]


def _one(dataclass_type: Any) -> Builder:
    def _build(mode: str) -> Any:
        rtnval = build_fixture(dataclass_type, mode=mode)
        return rtnval
    return _build


def _many(dataclass_type: Any) -> Builder:
    def _build(mode: str) -> Any:
        rtnval = build_fixture_list(dataclass_type, mode=mode)
        return rtnval
    return _build


def _const(value: Any) -> Builder:
    def _build(mode: str) -> Any:
        return value
    return _build


def _by_mode(populated: Any, sparse: Any) -> Builder:
    def _build(mode: str) -> Any:
        rtnval = populated if mode == MODE_POPULATED else sparse
        return rtnval
    return _build


class _FixtureFormView(MultiFormView):
    """
        A :class:`MultiFormView` that answers every field name. On a
        real re-render the submitted form carries every field the
        template reads, so the fixture is permissive on purpose:
        ``form_data`` is user input, not a drift surface.
    """

    def __getitem__(self, key: str) -> str:
        if key in self:
            rtnval = MultiFormView.__getitem__(self, key)
            return rtnval
        rtnval = "{}-form-value".format(key)
        return rtnval

    def get(self, key: str, default: Any = None) -> Any:
        if key in self:
            rtnval = MultiFormView.get(self, key, default)
            return rtnval
        rtnval = "{}-form-value".format(key)
        return rtnval


def _form_data(mode: str) -> Any:
    """
        ``form_data`` is ``None`` on a fresh GET and a
        :class:`MultiFormView` on a re-render after a validation
        error. Sparse mode mirrors the GET.
    """
    if mode == MODE_SPARSE:
        return None
    data: Dict[str, List[str]] = {
        "name": ["form-name"],
        "description": ["form-description"],
        "value": ["form-value"],
        "var_type": ["string"],
        "secret_type": ["password"],
        "resource_type": ["device"],
        "metadata": ["{}"],
        "url": ["https://example.invalid/repo.git"],
        "branch": ["main"],
        "credential_secret_ref": [""],
        "enabled": ["true"],
        "event_type": ["push"],
        "action_type": ["trigger_build"],
        "branch_pattern": ["*"],
        "action_spec_id": ["7"],
        "repository_id": ["7"],
        "pool_id": ["7"],
        "user_id": ["7"],
        "role": ["developer"],
        "steps": ["[]"],
        "environment": ["{}"],
        "tags": ["tag-a", "tag-b"],
        "permissions": ["perm-a"],
        "roles": ["role-a"],
        "default_repo_ids": ["1, 2"],
        "pipeline_json": ["{}"],
        "schedule_json": ["{}"],
    }
    rtnval = _FixtureFormView(data=data)
    return rtnval


def _flashes(mode: str) -> Any:
    if mode == MODE_SPARSE:
        return []
    rtnval = [("success", "Saved."), ("error", "Something went wrong.")]
    return rtnval


def _calendar_days(mode: str) -> Any:
    events: List[Dict[str, Any]] = []
    if mode == MODE_POPULATED:
        events = [{"event_type": "release", "title": "Release 1.2.0", "id": 7}]
    rtnval = [
        {"day": 1, "other_month": True, "is_today": False, "events": []},
        {"day": 4, "other_month": False, "is_today": True, "events": events},
    ]
    return rtnval


def _minted(mode: str) -> Any:
    if mode == MODE_SPARSE:
        return None
    rtnval = {
        "token_id": "tok-7",
        "pod_name": "pod-alpha",
        "secret": "s3cr3t",
        "enroll_command": "pychestrate-client enroll --token tok-7",
        "run_command": "pychestrate-client run",
    }
    return rtnval


def _health_groups(mode: str) -> Any:
    groups = {"online": [], "degraded": [], "maintenance": [], "offline": []}
    if mode == MODE_POPULATED:
        for key in groups:
            groups[key] = build_fixture_list(ResourceResponse, mode=mode, count=1)
    return groups


def _health_counts(mode: str) -> Any:
    if mode == MODE_SPARSE:
        return {"online": 0, "degraded": 0, "maintenance": 0, "offline": 0}
    rtnval = {"online": 5, "degraded": 1, "maintenance": 2, "offline": 1}
    return rtnval


def _form_values(mode: str) -> Any:
    """
        The first-admin setup form echoes these three fields back on
        a validation error (``setup/routes.py``).
    """
    rtnval = {
        "login_name": "admin" if mode == MODE_POPULATED else "",
        "email": "admin@example.invalid" if mode == MODE_POPULATED else "",
        "display_name": "Admin" if mode == MODE_POPULATED else "",
    }
    return rtnval


_BUILD_STEP_FIXTURE: Dict[str, Any] = {
    "name": "compile",
    "type": "shell",
    "command": "make",
    "continue_on_failure": False,
}


def _build_spec(mode: str) -> Any:
    """
        ``BuildSpecResponse.steps`` is ``List[Dict[str, Any]]`` whose
        dicts carry ``name`` / ``type`` / ``continue_on_failure``;
        the generic populator cannot know the keys.
    """
    steps: List[Dict[str, Any]] = [] if mode == MODE_SPARSE else [dict(_BUILD_STEP_FIXTURE)]
    rtnval = build_fixture(BuildSpecResponse, mode=mode, overrides={"steps": steps})
    return rtnval


def _build_specs(mode: str) -> Any:
    if mode == MODE_SPARSE:
        return []
    rtnval = [_build_spec(mode), _build_spec(mode)]
    return rtnval


_PIPELINE_STAGE_FIXTURE: Dict[str, Any] = {
    "name": "build",
    "type": "build",
    "config": {"spec_id": 7},
    "requires_approval": False,
    "continue_on_failure": False,
}


def _pipeline(mode: str) -> Any:
    """
        ``ReleasePipelineResponse.stages`` is ``List[Dict[str, Any]]``
        shaped like :class:`PipelineStageDefinition`; supply the real
        keys so the template's ``stage.name`` reads resolve.
    """
    stages: List[Dict[str, Any]] = [] if mode == MODE_SPARSE else [dict(_PIPELINE_STAGE_FIXTURE)]
    rtnval = build_fixture(ReleasePipelineResponse, mode=mode, overrides={"stages": stages})
    return rtnval


def _pipelines(mode: str) -> Any:
    if mode == MODE_SPARSE:
        return []
    rtnval = [_pipeline(mode), _pipeline(mode)]
    return rtnval


# ---------------------------------------------------------------------------
# Default registry: variable name -> builder
# ---------------------------------------------------------------------------

DEFAULT_REGISTRY: Dict[str, Builder] = {
    # Shell / base context every page gets
    "flashes": _flashes,
    "request_endpoint": _const("config.dashboard"),
    "csrf_token": _const("csrf-token-value"),
    "username": _const("admin"),
    "current_user_id": _const(7),
    "current_session_id": _const("session_id-7"),
    "page_title": _const("Page Title"),
    "content_html": _const("<p>content</p>"),
    "bundle_names": _by_mode(["pyc-admin-bundle"], []),
    "bundle_stylesheets": _by_mode(["pyc-admin-bundle"], []),
    "user_display_name": _by_mode("admin", ""),
    "status_code": _const(404),
    "title": _const("Page not found"),
    "message": _const("The address may be mistyped, or the page may have moved."),
    "back_url": _by_mode("/admin/users", None),
    "initial_route": _const("/"),
    "next_target": _const("/"),

    # Pagination + filters
    "page": _const(1),
    "per_page": _const(20),
    "total_pages": _by_mode(3, 1),
    "total": _by_mode(42, 0),
    "page_window": _by_mode([1, 2, 3], [1]),
    "window_start": _const(1),
    "window_end": _by_mode(3, 1),
    "search": _by_mode("needle", ""),
    "filters_active": _by_mode(True, False),
    "filter_username": _by_mode("admin", ""),
    "filter_user_id": _by_mode("user_id-7", ""),
    "username_unmatched": _by_mode(False, False),
    "selected_status": _by_mode("running", ""),
    "selected_spec_id": _by_mode(7, None),
    "selected_resource_id": _by_mode(7, None),
    "selected_user_id": _by_mode("user_id-7", ""),
    "selected_scope_id": _by_mode(7, None),
    "selected_channel_id": _by_mode(7, None),
    "errors": _by_mode({"name": "Name is required."}, {}),
    "selected_pool_id": _by_mode(7, None),
    "selected_job_id": _by_mode(7, None),
    "selected_step": _by_mode("build", None),
    "selected_event_type": _by_mode("release", ""),
    "selected_health_status": _by_mode("online", ""),
    "selected_resource_type": _by_mode("device", ""),
    "selected_tags": _by_mode(["tag-a"], []),
    "selector_pool_id": _by_mode(7, None),
    "selector_resource_type": _by_mode("device", ""),
    "start_after": _by_mode("2026-09-01T00:00", ""),
    "end_before": _by_mode("2026-09-30T00:00", ""),
    "start_date": _const(FIXTURE_DATE),
    "end_date": _const(FIXTURE_DATE),

    # Permission flags
    "can_manage": _by_mode(True, False),
    "can_delete": _by_mode(True, False),
    "can_edit": _by_mode(True, False),
    "is_self": _by_mode(True, False),

    # Forms
    "form_data": _form_data,
    "form_values": _form_values,
    "error": _by_mode("Invalid token. Re-read the token from the server.", None),
    "token_path": _const("/var/lib/pychestrate/unlock.token"),
    "min_password_length": _const(12),
    "default_ttl_seconds": _const(3600),
    "default_pipeline_json": _const("{\n  \"stages\": []\n}"),
    "default_schedule_json": _const("{}"),
    "default_repo_ids_csv": _by_mode("1, 2", ""),
    "action_types": _const(["trigger_build", "trigger_pipeline", "notify"]),
    "event_types": _const(["push", "pull_request", "tag"]),
    "all_event_types": _const(["release", "merge", "pull"]),
    "auth_types": _const(["none", "ssh_key", "token"]),
    "available_users": _many(UserResponse),
    "available_ips": _by_mode(["10.0.0.5", "10.0.0.6"], []),

    # Calendar
    "calendar_days": _calendar_days,
    "month_name": _const("September"),
    "year": _const(2026),
    "prev_month": _const(8),
    "prev_year": _const(2026),
    "next_month": _const(10),
    "next_year": _const(2026),

    # Config / identity
    "users": _many(AdminUserView),
    "user": _one(AdminUserView),
    "roles": _many(AdminRoleView),
    "role": _one(AdminRoleView),
    "permissions": _many(AdminPermissionView),
    "current_permission_keys": _by_mode(["id-7"], []),
    "sessions": _many(_SessionRow),
    "tokens": _many(TokenView),
    "minted": _minted,
    "variables": _many(GlobalVariableResponse),
    "variable": _one(GlobalVariableResponse),
    "secrets": _many(SecretMetadataResponse),
    "secret": _one(SecretMetadataResponse),
    "scopes": _many(SecretScopeResponse),
    "scope": _one(SecretScopeResponse),

    # Projects
    "projects": _many(ProjectResponse),
    "project_total": _by_mode(42, 0),
    "project": _one(ProjectResponse),
    "members": _many(ProjectMemberResponse),
    "member": _one(ProjectMemberResponse),
    "repositories": _many(RepositoryResponse),
    "repository": _one(RepositoryResponse),
    "watches": _many(WatchResponse),
    "watch": _one(WatchResponse),
    "trigger_logs": _many(WatchTriggerLog),
    "builds": _many(BuildResponse),
    "build": _one(BuildResponse),
    "build_specs": _build_specs,
    "recent_builds": _many(BuildResponse),
    "recent_tests": _many(TestJobResponse),
    "recent_runs": _many(PipelineRunResponse),
    "artifacts": _many(BuildArtifactResponse),
    "releases": _many(ReleaseResponse),
    "release": _one(ReleaseResponse),
    "pipelines": _pipelines,
    "pipeline": _pipeline,
    "channels": _many(ReleaseChannelResponse),
    "schedules": _many(ReleaseScheduleResponse),
    "events": _many(ReleaseEventResponse),
    "event": _one(ReleaseEventResponse),
    "phases": _many(PhaseEventResponse),
    "templates": _many(ReleaseTemplateResponse),
    "repository_names": _by_mode({7: "repo-alpha"}, {}),
    "template": _one(ReleaseTemplateResponse),

    # Resources
    "resources": _many(ResourceResponse),
    "resource": _one(ResourceResponse),
    "resource_total": _by_mode(42, 0),
    "resource_count": _by_mode(3, 0),
    "pool_count": _by_mode(2, 0),
    "ip_pool_count": _by_mode(1, 0),
    "active_allocation_count": _by_mode(2, 0),
    "pools": _many(ResourcePoolResponse),
    "pool": _one(ResourcePoolResponse),
    "allocations": _many(AllocationResponse),
    "allocation": _one(AllocationResponse),
    "active_allocations": _many(AllocationResponse),
    "reservations": _many(ReservationResponse),
    "reservation": _one(ReservationResponse),
    "upcoming_reservations": _many(ReservationResponse),
    "tags": _many(TagResponse),
    "all_tags": _many(TagResponse),
    "health_groups": _health_groups,
    "health_counts": _health_counts,
    "config": _one(HealthCheckConfigResponse),
    "history": _many(HealthTransitionResponse),
}


# ---------------------------------------------------------------------------
# Per-template-prefix overrides: longest matching prefix wins
# ---------------------------------------------------------------------------

TEMPLATE_PREFIX_OVERRIDES: Dict[str, Dict[str, Builder]] = {
    "config/": {
        "logs": _many(AuditLogEntry),
        "history": _many(VariableChangeLog),
    },
    "projects/": {
        "logs": _by_mode("line one\nline two\n", ""),
    },
    "projects/builds/": {
        "specs": _build_specs,
        "spec": _build_spec,
        "jobs": _many(BuildResponse),
        "job": _one(BuildResponse),
        "recent_jobs": _many(BuildResponse),
    },
    "projects/infrastructure/": {
        "specs": _many(InfraSpecResponse),
        "spec": _one(InfraSpecResponse),
        "jobs": _many(InfraJobResponse),
        "job": _one(InfraJobResponse),
        "recent_jobs": _many(InfraJobResponse),
    },
    "projects/tests/": {
        "specs": _many(TestSpecResponse),
        "spec": _one(TestSpecResponse),
        "jobs": _many(TestJobResponse),
        "job": _one(TestJobResponse),
        "recent_jobs": _many(TestJobResponse),
        "results": _many(TestCaseResult),
    },
    "projects/releases/": {
        "artifacts": _many(ReleaseArtifactResponse),
    },
    "setup/": {
        "errors": _by_mode(["Email address looks invalid.", "Password and confirmation do not match."], []),
    },
    "projects/calendar/": {
        "start_date": _by_mode("2026-09-01", ""),
        "end_date": _by_mode("2026-09-30", ""),
    },
    "resources/ip_pools/": {
        "pools": _many(IPPoolResponse),
        "pool": _one(IPPoolResponse),
        "allocations": _many(IPAllocationResponse),
    },
}


def resolve_builder(*, template_name: str, variable_name: str) -> Optional[Builder]:
    """
        Find the fixture builder for ``variable_name`` as read by
        ``template_name``. Prefix overrides win over the default
        registry; the longest matching prefix wins among overrides.

        :param template_name: Template path relative to the loader
                              root (``projects/builds/list.html``).
        :param variable_name: Top-level variable the template reads.

        :returns: A builder, or ``None`` when the name is unknown.
    """
    best_prefix: Optional[str] = None
    for prefix in TEMPLATE_PREFIX_OVERRIDES:
        if template_name.startswith(prefix) is False:
            continue
        if variable_name not in TEMPLATE_PREFIX_OVERRIDES[prefix]:
            continue
        if best_prefix is None or len(prefix) > len(best_prefix):
            best_prefix = prefix
    if best_prefix is not None:
        rtnval = TEMPLATE_PREFIX_OVERRIDES[best_prefix][variable_name]
        return rtnval
    rtnval = DEFAULT_REGISTRY.get(variable_name, None)
    return rtnval


def build_template_context(
        *,
        template_name: str,
        variable_names: List[str],
        mode: str
    ) -> Dict[str, Any]:
    """
        Build a render context covering ``variable_names``.

        :param template_name: Template path relative to the loader.
        :param variable_names: Names reported by
                               ``jinja2.meta.find_undeclared_variables``
                               (minus environment globals).
        :param mode: :data:`MODE_POPULATED` or :data:`MODE_SPARSE`.

        :returns: Context dict.
        :raises: KeyError listing every name with no registered
                 builder, so the failure names the fix.
    """
    missing: List[str] = []
    rtnval: Dict[str, Any] = {}
    for name in variable_names:
        builder = resolve_builder(template_name=template_name, variable_name=name)
        if builder is None:
            missing.append(name)
            continue
        rtnval[name] = builder(mode)
    if len(missing) > 0:
        raise KeyError(
            "No fixture registered for template variables {} read by {}."
            " Add them to ccai.testshared.factories.webui.template_contexts"
            " with the type the route handler passes.".format(
                sorted(missing), template_name
            )
        )
    return rtnval


__all__ = [
    "DEFAULT_REGISTRY",
    "TEMPLATE_PREFIX_OVERRIDES",
    "resolve_builder",
    "build_template_context",
]
