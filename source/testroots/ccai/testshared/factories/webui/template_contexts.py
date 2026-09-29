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


from datetime import date, datetime, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

from ccai.testshared.factories.webui.dataclass_fixtures import (
    FIXTURE_DATE,
    FIXTURE_DATETIME,
    MODE_POPULATED,
    MODE_SPARSE,
    build_fixture,
    build_fixture_list,
)

from ccai.pychestrate.webservice.webinterface.blueprints.resources import availability_view
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
from ccai.pychestrate.webservice.orchestration.rpa.service import (
    RpaJobTypeVersionView,
    RpaJobTypeView,
    RpaJobView,
    RpaSpecView,
)
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
# Machine identity pages (config/tokens/*).
from ccai.pychestrate.webservice.security.auth.api_tokens.service import (
    ApiTokenView,
    ServiceAccountView,
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


def _api_token_minted(mode: str) -> Any:
    """
        The one-time panel ``routes_tokens`` renders after issuing an
        API token; ``None`` on a plain GET.
    """
    if mode == MODE_SPARSE:
        return None
    rtnval = {
        "token": "pyc_" + "x" * 43,
        "name": "laptop CLI",
        "owner_label": "admin",
        "scope": "read-write",
        "expires_at": FIXTURE_DATETIME,
        "login_command": "pyc login --server-url https://pyc.example.invalid",
        "curl_command": 'curl -H "Authorization: Bearer $PYC_TOKEN" https://pyc.example.invalid/api/v1/me',
    }
    return rtnval


def _availability_window(mode: str) -> Any:
    """A week for the availability view: Pacific time when populated (its zone, with "now" inside it), UTC otherwise."""
    zone: Any = ZoneInfo("America/Los_Angeles") if mode == MODE_POPULATED else timezone.utc
    rtnval = availability_view.week_window(
        anchor=date(2026, 9, 30), zone=zone, zone_name="America/Los_Angeles" if mode == MODE_POPULATED else "UTC",
        now=datetime(2026, 9, 30, 19, 0, tzinfo=timezone.utc) if mode == MODE_POPULATED else datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return rtnval


def _availability_rows(mode: str) -> Any:
    """Availability rows: two resources with a reservation, a shared one that overlaps it and a check-out; none when sparse."""
    if mode == MODE_SPARSE:
        return []
    window = _availability_window(mode)
    resources = [
        SimpleNamespace(id=1, name="lab-phone-1", health_status="online"),
        SimpleNamespace(id=2, name="lab-phone-2", health_status="offline"),
    ]
    reservations = [
        SimpleNamespace(
            id=11, resource_id=1, username="quinn", job_id="job-1", mode="exclusive", status="pending",
            start_time=datetime(2026, 9, 30, 18, 0, tzinfo=timezone.utc), end_time=datetime(2026, 9, 30, 22, 0, tzinfo=timezone.utc),
        ),
        SimpleNamespace(
            id=12, resource_id=1, username="riley", job_id=None, mode="shared", status="active",
            start_time=datetime(2026, 9, 30, 20, 0, tzinfo=timezone.utc), end_time=datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc),
        ),
    ]
    holders = {2: [{
        "username": "sam", "job_id": None, "mode": "exclusive",
        "checkout_time": datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc), "expected_checkin": None,
    }]}
    rows = availability_view.build_rows(resources=resources, reservations=reservations, holders=holders, window=window)
    for row in rows:
        for block in row.blocks:
            block.tooltip = "{} by {}".format(block.kind, block.who)
    return rows


def _availability_bookings(mode: str) -> Any:
    if mode == MODE_SPARSE:
        return []
    rtnval = [{
        "resource_id": 1, "resource_name": "lab-phone-1", "who": "quinn", "kind": "Reserved (exclusive)",
        "kind_key": "reserved-exclusive", "start_text": "2026-09-30 11:00 PDT", "end_text": "2026-09-30 15:00 PDT",
        "reservation_id": 11, "status": "pending", "job_id": "job-1",
    }, {
        "resource_id": 2, "resource_name": "lab-phone-2", "who": None, "kind": "Checked out",
        "kind_key": "checked-out", "start_text": "2026-09-29 08:00 PDT", "end_text": "no end set",
        "reservation_id": None, "status": "active", "job_id": None,
    }]
    return rtnval


def _token_rows_fixture(mode: str) -> Any:
    """The enrollment token list the way the route passes it: rows with real datetimes."""
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_enrollment import _token_rows

    rtnval = _token_rows(tokens=build_fixture_list(TokenView, mode=mode, count=2 if mode == MODE_POPULATED else 0))
    return rtnval


def _import_preview(mode: str) -> Any:
    """A spreadsheet preview: with problems (a bad row and a file problem) when populated, all ready when sparse."""
    from ccai.pychestrate.webservice.webinterface.blueprints.resources import resource_import  # noqa: E402

    preview = resource_import.parse_import(text=resource_import.EXAMPLE_TEXT)
    if mode == MODE_POPULATED:
        preview.rows[1].problems["name"] = "The pool \"android-phones\" already has a resource called \"phone-02\"."
        preview.file_problems.append("These column names are not known: \"colour\".")
    return preview


def _import_example(mode: str) -> Any:
    from ccai.pychestrate.webservice.webinterface.blueprints.resources import resource_import  # noqa: E402

    return resource_import.EXAMPLE_TEXT


def _import_columns(mode: str) -> Any:
    from ccai.pychestrate.webservice.webinterface.blueprints.resources import resource_import  # noqa: E402

    return resource_import.DOCUMENTED_COLUMNS


def _my_allocation(mode: str) -> Any:
    """The current person's own active allocation of the resource, or None."""
    if mode == MODE_SPARSE:
        return None
    rtnval = build_fixture(AllocationResponse, mode=mode)
    return rtnval


def _blocking_transition(mode: str) -> Any:
    """The health change that blocked a resource, or None."""
    if mode == MODE_SPARSE:
        return None
    rtnval = build_fixture(HealthTransitionResponse, mode=mode)
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
    "user_display_name": _by_mode("Ada Admin", ""),
    "user_login_name": _by_mode("admin", ""),
    "service_version": _by_mode("0.0.7-preview", ""),
    "status_code": _const(404),
    "title": _const("Page not found"),
    "message": _const("The address may be mistyped, or the page may have moved."),
    "back_url": _by_mode("/admin/users", None),
    "back_link": _by_mode(("Back to Users", "/admin/users"), None),
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
    "error_labels": _by_mode({"name": "Name"}, {}),
    # What the admin typed into a refused edit form (None on a fresh one).
    "submitted": _by_mode({"value": "typed value", "description": "typed description"}, None),
    "submitted_description": _by_mode("typed description", None),
    # What the admin typed into a refused health check form (None on a fresh one).
    "health_form": _by_mode(
        {"probe_url": "http://10.0.4.21/health", "interval_seconds": "60", "timeout_seconds": "10",
         "failure_threshold": "3", "success_threshold": "1", "enabled": True},
        None,
    ),
    "selected_pool_id": _by_mode(7, None),
    "selected_job_id": _by_mode(7, None),
    "selected_step": _by_mode("build", None),
    "status_choices": _const(["pending", "running", "succeeded", "failed"]),
    "default_packet_json": _const('{\n  "region": "eu"\n}'),
    "packet_schema_json": _by_mode('{\n  "type": "object"\n}', ""),
    "work_packet_json": _const('{\n  "customer_id": 42\n}'),
    "run_packet_json": _const('{\n  "region": "eu"\n}'),
    "secret_packet_keys": _by_mode(["auth"], []),
    "run_pods": _by_mode(
        [{"pod_id": "11111111-1111-4000-8000-000000000001", "label": "lab-pod-01 (11111111)"},
         {"pod_id": "22222222-2222-4000-8000-000000000002", "label": "lab-pod-02 (22222222)"}],
        [],
    ),
    "run_blocked_reason": _by_mode("", "No pod can run this job yet."),
    "run_errors": _by_mode(["/customer_id: required"], []),
    "run_selected_pod_id": _by_mode("11111111-1111-4000-8000-000000000001", ""),
    "replay_job": _by_mode(SimpleNamespace(job_id="0f6c2c1e-1111-4000-8000-000000000009"), None),
    # The registry project a web-UI project is linked to (projects.bridge).
    # The error catalogue pages (api.error_catalogue).
    "problem_types": _const([
        {"slug": "not-found", "status": 404, "title": "Not Found", "type": "/errors/not-found",
         "meaning": "Nothing is at that address.", "remedy": "Check the path."},
        {"slug": "unknown-error", "status": 0, "title": "Error", "type": "/errors/unknown-error",
         "meaning": "No page of its own.", "remedy": "Use the status."},
    ]),
    "problem_type": _const(
        {"slug": "not-found", "status": 404, "title": "Not Found", "type": "/errors/not-found",
         "meaning": "Nothing is at that address.", "remedy": "Check the path."},
    ),
    "unknown_slug": _by_mode("nope", ""),
    "registry_project": _by_mode(
        SimpleNamespace(project_id="0f6c2c1e-2222-4000-8000-00000000000a", slug="demo-project"), None,
    ),
    "replay_message": _by_mode("An identical run of this specification was submitted less than a minute ago, so no new job was started.", ""),
    "pod_choices": _by_mode(
        [{"pod_id": "11111111-1111-4000-8000-000000000001", "label": "lab-pod-01 (11111111)"}],
        [],
    ),
    "is_active": _by_mode(True, False),
    "job_types": _many(RpaJobTypeView),
    "job_type": _one(RpaJobTypeView),
    "versions": _many(RpaJobTypeVersionView),
    "execution_modes": _const([{"execution_mode": "process", "description": "Simple process job."}]),
    "has_override": _by_mode(True, False),
    "override_reset": _by_mode(True, False),
    "hidden_labels": _by_mode(["Infrastructure"], []),
    "surfaces": _by_mode(
        [{"surface": "rpa", "label": "Robotic Process Automation",
          "description": "RPA specifications and jobs.", "enabled": True, "entry_count": 1}],
        [],
    ),
    "enabled_count": _by_mode(4, 0),
    "surface_total": _const(4),
    "variable_name": _const("ui.profile.surfaces"),
    "selected_event_type": _by_mode("release", ""),
    "selected_health_status": _by_mode("online", ""),
    "selected_status": _by_mode("", "offline"),
    "check_queue_stale": _by_mode(True, False),
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
    "issue_for": _const(None),
    "next_reservation_by_other": _one(ReservationResponse),
    "selected_availability": _by_mode("available", ""),
    "holders": _by_mode({}, {}),
    "addable_resources": _many(ResourceResponse),
    "other_pools": _many(ResourcePoolResponse),
    "my_allocations": _many(IPAllocationResponse),
    "acting_for_other": _by_mode(True, False),
    "editable_project_ids": _by_mode([1, 2, 3], []),
    "submitted_role": _const(None),
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
    "tag": _one(TagResponse),

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
# Admin & identity: password rules, password lifecycle, audit, sessions
# (September 2026 audit fixes). Values come from the product modules so
# the fixtures cannot drift from what the handlers pass.
# ---------------------------------------------------------------------------

def _password_policy_value(key: str) -> Builder:
    def _build(mode: str) -> Any:
        from ccai.pychestrate.webservice.security.auth.password_policy import (  # noqa: E402
            password_policy_template_context,
        )
        rtnval = password_policy_template_context()[key]
        return rtnval
    return _build


def _format_variable_value_builder() -> Builder:
    def _build(mode: str) -> Any:
        from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_variables import (  # noqa: E402
            format_variable_value,
        )
        return format_variable_value
    return _build


def _change_diff_builder() -> Builder:
    def _build(mode: str) -> Any:
        from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_variables import (  # noqa: E402
            change_diff_lines,
        )
        return change_diff_lines
    return _build


_FIXTURE_UI_PROJECT_UUID: str = "5a0c2e62-8f7a-5d16-9f4e-3c1b2a0d9e11"
_FIXTURE_API_PROJECT_UUID: str = "0b6f3c1e-2d4a-4e8b-9c7d-1a2b3c4d5e6f"


def _project_choices(mode: str) -> Any:
    from ccai.pychestrate.webservice.webinterface.blueprints.config.routes_enrollment import (  # noqa: E402
        ProjectChoice,
    )
    if mode == MODE_SPARSE:
        return []
    rtnval = [
        ProjectChoice(
            value=_FIXTURE_UI_PROJECT_UUID, label="alpha",
            detail="web UI project #1", source="ui",
        ),
        ProjectChoice(
            value=_FIXTURE_API_PROJECT_UUID, label="Beta",
            detail="beta", source="api",
        ),
    ]
    return rtnval


def _project_choice_groups(mode: str) -> Any:
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        routes_enrollment,
    )
    rtnval = routes_enrollment._project_choice_groups(choices=_project_choices(mode))
    return rtnval


def _audit_rows(mode: str) -> Any:
    from ccai.pychestrate.webservice.audit.audit_presenter import AuditRow  # noqa: E402
    rtnval = build_fixture_list(AuditRow, mode=mode)
    return rtnval


def _action_groups(mode: str) -> Any:
    from ccai.pychestrate.webservice.audit.audit_query import AuditKindView  # noqa: E402
    from ccai.pychestrate.webservice.webinterface.blueprints.config import (  # noqa: E402
        routes_audit,
    )
    if mode == MODE_SPARSE:
        return []
    views = [
        AuditKindView(kind="audit.session.opened", area="session", description="A user signed in."),
        AuditKindView(kind="audit.data.updated", area="data", description="A record was changed."),
    ]
    rtnval = routes_audit._action_groups(kind_views=views)
    return rtnval


_AUDIT_FILTERS_POPULATED = {
    "action": "audit.session.opened", "actor": "admin", "target": "projects:1",
    "since": "2026-09-01T00:00", "until": "2026-09-30T23:59", "per_page": 50,
}
_AUDIT_FILTERS_SPARSE = {
    "action": "", "actor": "", "target": "", "since": "", "until": "", "per_page": 50,
}


def _minted_with_project(mode: str) -> Any:
    base = _minted(mode)
    if base is None:
        return None
    rtnval = dict(base)
    rtnval["project_label"] = "alpha"
    return rtnval


DEFAULT_REGISTRY.update({
    "password_rules": _password_policy_value("password_rules"),
    "password_summary": _password_policy_value("password_summary"),
    "password_pattern": _password_policy_value("password_pattern"),
    "password_title": _password_policy_value("password_title"),
    "password_min_length": _password_policy_value("password_min_length"),
    "password_max_length": _password_policy_value("password_max_length"),
    "password_input_id": _const("password"),
    "value_cleared": _by_mode(True, False),
    "format_value": _format_variable_value_builder(),
    "change_diff": _change_diff_builder(),
    "project_choices": _project_choices,
    "project_choice_groups": _project_choice_groups,
    "project_labels": _by_mode({_FIXTURE_UI_PROJECT_UUID: "alpha"}, {}),
    "mint_form": _by_mode(
        {"project_id": _FIXTURE_UI_PROJECT_UUID, "pod_name": "pod-alpha",
         "ttl_seconds": "3600", "one_shot": True},
        {"project_id": "", "pod_name": "", "ttl_seconds": "", "one_shot": True},
    ),
    "minted": _minted_with_project,
    "audit_rows": _audit_rows,
    "audit_total": _by_mode(2, 0),
    "audit_filters": _by_mode(_AUDIT_FILTERS_POPULATED, _AUDIT_FILTERS_SPARSE),
    "audit_notices": _by_mode(['No user has the username "ghost".'], []),
    "action_groups": _action_groups,
    "older_url": _by_mode("/admin/audit-logs?before=10", None),
    "newer_url": _by_mode("/admin/audit-logs?after=20", None),
    "newest_url": _by_mode("/admin/audit-logs", None),
    "export_csv_url": _const("/admin/audit-logs/export?format=csv"),
    "export_jsonl_url": _const("/admin/audit-logs/export?format=jsonl"),
    "issued_link": _by_mode(
        {"url": "https://pyc.example.invalid/password/set/abc", "purpose": "RESET",
         "expires_at": FIXTURE_DATETIME},
        None,
    ),
    "problems": _by_mode(["Password must contain a digit.", "Password must contain a symbol, such as ! # or -."], []),
    "just_created": _by_mode(True, False),
    "link_valid": _by_mode(True, False),
    "invalid_message": _const("This link is not valid. It may have expired or already been used."),
    "purpose": _by_mode("INVITE", "RESET"),
    "login_name": _const("jdoe"),
    "form_action": _const("/password/set/abc"),
    "idle_timeout_minutes": _const(30),
    "max_lifetime_hours": _const(24),
    "sessions_by_user": _by_mode({"user_id-0": 3}, {}),
})


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
    "projects/rpa/": {
        "specs": _many(RpaSpecView),
        "spec": _one(RpaSpecView),
        "jobs": _many(RpaJobView),
        "job": _one(RpaJobView),
        "recent_jobs": _many(RpaJobView),
        "selected_spec_id": _by_mode("spec_id-7", None),
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
    # -- projects-a audit fixes (PRJ-*) -----------------------------------
    "projects/members/": {
        "user_search": _by_mode("ali", ""),
        "can_create_users": _by_mode(True, False),
        "roles": _const(["owner", "administrator", "developer", "viewer"]),
        "role_descriptions": _const({
            "owner": "Owner - everything",
            "developer": "Developer - run jobs",
        }),
        "global_access": _by_mode(
            [{"user_id": "user_id-7", "username": "bob", "display_name": "Bob",
              "role": "developer", "roles": ["project-editor"]}],
            [],
        ),
    },
    "projects/release_templates/": {
        "can_create_release": _by_mode(True, False),
        "release_form": _by_mode({"version": "1.4.0", "name": "Spring"}, {}),
        "release_errors": _by_mode({"version": "Version 1.4 does not match this template's version pattern."}, {}),
    },
    "projects/releases/detail": {
        "provenance": _by_mode(
            {
                "template_id": 7,
                "template_name": "standard",
                "channel": "stable",
                "version_pattern": "^\\d+\\.\\d+\\.\\d+$",
                "repositories": [{"id": 7, "name": "repo-alpha"}, {"id": 8, "name": None}],
                "pipeline_json": "{\n  \"stages\": []\n}",
                "schedule_json": "",
            },
            None,
        ),
    },
    "projects/repositories/": {
        "secret_refs": _by_mode(["ci/github-token", "ci/deploy-key"], []),
        "repository_specs": _by_mode(["nightly"], []),
    },
    "projects/builds/spec_detail": {
        "spec_usage": _by_mode(
            {"builds": 3, "active_builds": 1, "watches": ["build-on-push"]},
            {"builds": 0, "active_builds": 0, "watches": []},
        ),
    },
    "projects/rpa/detail": {
        "job_names": _by_mode(
            {"triggered_by": "Admin User", "pod": "lab-a", "client": "client of lab-a"},
            {"triggered_by": None, "pod": None, "client": None},
        ),
    },
    "projects/builds/spec_edit": {
        "form_values": _by_mode(
            {"name": "nightly", "repository_id": "7", "branch": "main", "timeout_minutes": "60",
             "steps": "[]", "environment": "{}", "description": "Nightly build"},
            {"name": "", "repository_id": "", "branch": "", "timeout_minutes": "",
             "steps": "", "environment": "", "description": ""},
        ),
    },
    "projects/watches/": {
        "trigger_labels": _const({
            "repository_commit": "New commits on a branch",
            "build_completion": "A build finishes",
        }),
        "action_labels": _const({"trigger_build": "Run a build"}),
        "target_names": _by_mode({"trigger_build:1": "nightly"}, {}),
        "test_sample": _by_mode({"sample_branch": "main", "sample_build_status": "failed"}, {}),
        "test_result": _by_mode(
            {
                "watch_id": 7,
                "watch_name": "build-on-push",
                "trigger_source": "repository_commit",
                "enabled": True,
                "would_trigger": False,
                "conditions_match": False,
                "condition_results": {
                    "branch_pattern": {"pattern": "^main$", "value": "dev", "matches": False, "applies": True},
                    "tag_pattern": {"pattern": None, "value": "", "matches": True, "applies": False},
                    "file_pattern": {"pattern": None, "value": [], "matches": True, "applies": False},
                    "build_status": {"pattern": "failed", "value": "failed", "matches": True, "applies": True},
                },
                "actions_count": 1,
                "actions": [{"action": "trigger_build", "target_id": 3}],
            },
            None,
        ),
    },
    # -- end projects-a audit fixes --------------------------------------
    "setup/": {
        "errors": _by_mode(["Email address looks invalid.", "Password and confirmation do not match."], []),
        "field_errors": _by_mode(
            {"email": "Email address looks invalid.", "password_confirm": "Password and confirmation do not match."},
            {},
        ),
        "first_invalid": _by_mode("email", None),
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
    # Resources audit fixes (RES-02 / RES-17): the IANA zone a
    # reservation form's times are typed in ("" = fresh form, UTC).
    # A deleted variable's history is kept and shown (ADM-36).
    "config/variables/": {
        "variable_name": _const("ui.example"),
        "variable_deleted": _by_mode(True, False),
    },
    # Enrollment tokens as the route's rows (ADM-40): datetimes, not ISO text.
    "config/enrollment/": {
        "tokens": _token_rows_fixture,
    },
    # The resource page's checkout card (RES-30): why checkout is not offered.
    "resources/resources/": {
        "my_allocation": _my_allocation,
        "blocking_transition": _blocking_transition,
        # The spreadsheet import page (RES-22).
        "import_text": _by_mode("name\nphone-01\n", ""),
        "import_preview": _import_preview,
        "documented_columns": _import_columns,
        "example_text": _import_example,
        "max_rows": _const(500),
    },
    "resources/reservations/": {
        "viewer_timezone": _by_mode("America/Los_Angeles", ""),
        # Reservation list status filter and the availability week (RES-43).
        "status_filters": _const([{"key": "open", "label": "Pending and active"}, {"key": "all", "label": "All"}]),
        "selected_reservation_status": _by_mode("all", "open"),
        "window": _availability_window,
        "rows": _availability_rows,
        "bookings": _availability_bookings,
        "zone_name": _by_mode("America/Los_Angeles", "UTC"),
        "zone_chosen": _by_mode(True, False),
        "this_week": _const("2026-09-28"),
    },
    # Machine identity: API tokens and service accounts
    # (webinterface/blueprints/config/routes_tokens.py).
    "config/tokens/": {
        "tokens": _many(ApiTokenView),
        "minted": _api_token_minted,
        "service_accounts": _many(ServiceAccountView),
        "lifetime_choices": _const((7, 30, 90, 180, 366)),
        "default_lifetime_days": _const(90),
        "can_view_admin_tokens": _by_mode(True, False),
        "can_manage_tokens": _by_mode(True, False),
        "can_create_service_accounts": _by_mode(True, False),
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
