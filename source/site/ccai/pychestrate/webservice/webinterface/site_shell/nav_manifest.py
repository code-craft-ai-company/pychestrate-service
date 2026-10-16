"""
.. module:: webinterface.site_shell.nav_manifest
    :platform: Darwin, Linux, Unix, Windows
    :synopsis: Central, authoritative navigation manifest for the
               site shell sidebar.

.. moduleauthor:: Code Craft AI LLC

Historically every feature bundle (``pyc-admin-bundle``,
``pyc-runs-bundle``, ...) registered its own sidebar group and
entries against the in-browser ``SidebarRegistry`` from its
``<script type="module">`` body. Because the shell document only
injects a feature bundle when the request path matches that
bundle's route prefix (see :mod:`bundle_registry`), the sidebar
was only ever *partially* populated -- and on the bare ``/`` route
(which loads only ``pyc-site-shell.js``) it was completely empty,
so the shell rendered its zero-entries "no access" empty state
even for a full administrator.

This module is the single, authoritative source of truth for the
sidebar navigation. It declares every group and entry once,
server-side, decoupled from which feature bundle happens to be
loaded. The :mod:`me_routes` ``GET /api/v1/me/navigation`` endpoint
permission-filters this manifest against the calling principal's
effective permissions and the shell renders the full sidebar from
the result on every route.

Feature bundles still own their *views* (route-scoped Web
Component mounting) -- that is legitimately route-scoped -- but the
sidebar entries are no longer owned per-bundle.
"""

__author__ = "Code Craft AI LLC"
__copyright__ = "Copyright 2026, Code Craft AI LLC"
__credits__ = []
__version__ = "1.0.0"


from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class NavEntry:
    """
        A single navigable sidebar item.

        :ivar entry_id: Stable identifier for the entry.
        :ivar label: Human-readable label rendered in the sidebar.
        :ivar route: Path the shell navigates to on activation.
        :ivar group_id: Identifier of the owning :class:`NavGroup`.
        :ivar required_permissions: System-scoped permission keys
                                    the caller must hold for the
                                    entry to be visible.
        :ivar icon: Optional icon token.
        :ivar section: Optional heading the sidebar writes above this entry
                       and the entries after it that share it, inside the
                       group (the Admin group has four).
    """
    entry_id: str
    label: str
    route: str
    group_id: str
    required_permissions: List[str] = field(default_factory=list)
    icon: str = ""
    surfaces: Tuple[str, ...] = ()
    section: str = ""


@dataclass(frozen=True)
class NavGroup:
    """
        A labeled section of the sidebar containing one or more
        :class:`NavEntry` items.

        :ivar group_id: Stable identifier for the group.
        :ivar label: Human-readable section heading.
        :ivar required_permissions: System-scoped permission keys
                                    the caller must hold for the
                                    whole group to be visible.
        :ivar icon: Optional icon token.
    """
    group_id: str
    label: str
    required_permissions: List[str] = field(default_factory=list)
    icon: str = ""
    surfaces: Tuple[str, ...] = ()


#: Suffix of the label of an entry whose page works only in part
#: (see the PREVIEW LABELS note above :data:`NAV_ENTRIES`).
PREVIEW_LABEL_SUFFIX: str = " (preview)"


# Group identifiers -- mirror the ``groupId`` values the feature
# bundles historically registered so existing CSS / tests keep
# matching.
GROUP_PROJECTS: str = "projects"
GROUP_ORCHESTRATION: str = "orchestration"
GROUP_INSIGHTS: str = "insights"
GROUP_FLEET: str = "fleet"
GROUP_OPERATIONS: str = "operations"
GROUP_SYSTEM: str = "system"
GROUP_ADMIN: str = "admin"


# The authoritative group list. A group is hidden when the caller
# lacks every one of its ``required_permissions`` (an empty list
# means the group is never hidden on the group check alone -- entry
# checks still apply).
NAV_GROUPS: List[NavGroup] = [
    NavGroup(
        group_id=GROUP_PROJECTS,
        label="Projects",
        icon="projects",
        # Derived for project members and global project-role holders
        # (system administrators included) -- see
        # blueprints/projects/project_access.py (PRJ-17).
        required_permissions=["system:projects.access"],
    ),
    NavGroup(
        group_id=GROUP_ORCHESTRATION,
        label="Orchestration",
        icon="orchestration",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_INSIGHTS,
        label="Insights",
        icon="insights",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_FLEET,
        label="Fleet",
        icon="fleet",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_OPERATIONS,
        label="Operations",
        icon="operations",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_SYSTEM,
        label="System",
        icon="system",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_ADMIN,
        label="Admin",
        icon="admin",
        required_permissions=["system:ui.admin.view"],
    ),
]


# The authoritative entry list. Each entry mirrors the descriptor
# the corresponding feature bundle historically registered.
#
# PREVIEW LABELS (audit ORG-F14): an entry whose page works only in
# part carries :data:`PREVIEW_LABEL_SUFFIX` in its label, and the page
# itself says what is missing. Drop the suffix when the missing part
# ships:
#
# * Alert Rules -- rules are evaluated and show their state, but no
#   notification is sent to their targets.
# * Webhooks -- inbound deliveries are verified and recorded but start
#   nothing; outbound subscriptions receive test events only.
# * Pod Resource Pools -- pools can be managed, but job dispatch does
#   not allocate from them.
#
# INVARIANT: every key named in ``required_permissions`` (here and
# in NAV_GROUPS) MUST be declared in the in-tree permission
# catalog (:mod:`security.rbac.extensions.core_permissions`). An
# entry that requires an undeclared key can never be held by any
# principal, so the entry -- and, once its siblings are filtered,
# its whole group -- silently disappears for every user. Where an
# entry's route is backed by a REST surface, the keys should match
# what that surface actually enforces.
NAV_ENTRIES: List[NavEntry] = [
    # ---- Projects ------------------------------------------------
    # Two pages, two names, the same in the sidebar and on the project pages'
    # own navigation (PRJ-27): the dashboard says what needs attention, "All
    # Projects" lists every project. "All Projects" owns the bare ``/projects``
    # prefix, so a project's own pages keep it highlighted; the dashboard
    # is one segment longer and wins on its own address. Labeled apart from
    # the group ("Projects") and from Insights' "Dashboards".
    NavEntry(
        entry_id="projects.dashboard",
        label="Projects Dashboard",
        route="/projects/dashboard",
        group_id=GROUP_PROJECTS,
        required_permissions=["system:projects.access"],
    ),
    NavEntry(
        entry_id="projects.list",
        label="All Projects",
        route="/projects",
        group_id=GROUP_PROJECTS,
        required_permissions=["system:projects.access"],
    ),
    # ---- Orchestration -------------------------------------------
    NavEntry(
        entry_id="orchestration.runs",
        surfaces=('build', 'testing', 'rpa'),
        label="Runs",
        route="/runs",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:runs.read"],
    ),
    NavEntry(
        entry_id="orchestration.builds",
        surfaces=('build',),
        label="Builds",
        route="/builds",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:builds.read"],
    ),
    NavEntry(
        entry_id="orchestration.pipelines",
        surfaces=('build',),
        label="Pipelines",
        route="/pipelines",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:pipelines.read"],
    ),
    NavEntry(
        entry_id="orchestration.test-catalog",
        surfaces=('testing',),
        label="Test Catalog",
        route="/test-catalog",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:test_catalog.read"],
    ),
    NavEntry(
        entry_id="orchestration.environments",
        surfaces=('infra',),
        label="Environments",
        route="/environments",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:environments.read"],
    ),
    NavEntry(
        entry_id="orchestration.provisioning",
        surfaces=('infra',),
        label="Provisioning",
        route="/provisioning-runs",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:provisioning.read"],
    ),
    NavEntry(
        entry_id="orchestration.guards",
        surfaces=('infra',),
        label="Blast-Radius Guards",
        route="/blast-radius-guards",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:guards.read"],
    ),
    # ---- Insights ------------------------------------------------
    NavEntry(
        entry_id="insights.test-metrics",
        surfaces=('testing',),
        label="Test Metrics",
        route="/test-metrics",
        group_id=GROUP_INSIGHTS,
        required_permissions=["system:metrics.read"],
    ),
    NavEntry(
        entry_id="insights.timeseries",
        label="Timeseries",
        route="/timeseries",
        group_id=GROUP_INSIGHTS,
        required_permissions=["system:metrics.read"],
    ),
    NavEntry(
        entry_id="insights.dashboards",
        label="Dashboards",
        route="/dashboards",
        group_id=GROUP_INSIGHTS,
        # The dashboards REST surface enforces
        # ``system:dashboards.read`` (dashboards_routes) and the
        # rendered dashboards query metric timeseries, which
        # enforce ``system:metrics.read``, so the entry requires
        # both.
        required_permissions=[
            "system:metrics.read",
            "system:dashboards.read",
        ],
    ),
    NavEntry(
        entry_id="insights.slos",
        label="SLOs",
        route="/slos",
        group_id=GROUP_INSIGHTS,
        required_permissions=["system:slos.read"],
    ),
    NavEntry(
        entry_id="insights.metric-alerts",
        label="Alert Rules" + PREVIEW_LABEL_SUFFIX,
        route="/metric-alerts",
        group_id=GROUP_INSIGHTS,
        required_permissions=["system:metric_alerts.read"],
    ),
    # ---- Fleet ---------------------------------------------------
    NavEntry(
        entry_id="fleet.pods",
        label="Pods",
        route="/pods",
        group_id=GROUP_FLEET,
        required_permissions=["system:pods.read"],
    ),
    NavEntry(
        entry_id="fleet.clients",
        label="Clients",
        route="/clients",
        group_id=GROUP_FLEET,
        required_permissions=["system:clients.read"],
    ),
    NavEntry(
        entry_id="fleet.resources",
        label="Resources and Pools" + PREVIEW_LABEL_SUFFIX,
        route="/resource-pools",
        group_id=GROUP_FLEET,
        # The /resource-pools surface enforces
        # ``system:resource_pools.read`` (resource_pools_routes)
        # and the per-resource views it links into enforce
        # ``system:resources.read`` (resources_routes), so the
        # entry requires both.
        required_permissions=[
            "system:resources.read",
            "system:resource_pools.read",
        ],
    ),
    # The server-rendered /resources/* pages hold the older resource
    # records (RES-05): their list was reachable only through another
    # page's sub-navigation. They also cover what the /resource-pools
    # bundle does not yet: IP pools, reservations, and health
    # monitoring. They render inside the shell.
    NavEntry(
        entry_id="fleet.older-resources",
        label="Older Resources",
        route="/resources/list",
        group_id=GROUP_FLEET,
        required_permissions=["system:resources.read"],
    ),
    NavEntry(
        entry_id="fleet.ip-pools",
        label="IP Pools",
        route="/resources/ip-pools",
        group_id=GROUP_FLEET,
        required_permissions=["system:resources.read"],
    ),
    NavEntry(
        entry_id="fleet.reservations",
        label="Reservations",
        route="/resources/reservations",
        group_id=GROUP_FLEET,
        required_permissions=["system:resources.read"],
    ),
    NavEntry(
        entry_id="fleet.resource-health",
        label="Resource Health",
        route="/resources/health",
        group_id=GROUP_FLEET,
        required_permissions=["system:resources.read"],
    ),
    # ---- Operations ----------------------------------------------
    NavEntry(
        entry_id="operations.webhooks",
        label="Webhooks" + PREVIEW_LABEL_SUFFIX,
        route="/webhooks",
        group_id=GROUP_OPERATIONS,
        required_permissions=["system:webhooks.read"],
    ),
    # ---- System --------------------------------------------------
    NavEntry(
        entry_id="system.secrets",
        label="Secrets",
        route="/secrets",
        group_id=GROUP_SYSTEM,
        required_permissions=["system:secrets.read"],
    ),
    # ---- Admin ---------------------------------------------------
    NavEntry(
        entry_id="admin.overview",
        label="Overview",
        route="/admin",
        group_id=GROUP_ADMIN,
        required_permissions=["system:ui.admin.view"],
    ),
    NavEntry(
        entry_id="admin.users",
        label="Users",
        route="/admin/users",
        group_id=GROUP_ADMIN,
        required_permissions=["system:users.read"],
        section="People & access",
    ),
    NavEntry(
        entry_id="admin.roles",
        label="Roles",
        route="/admin/roles",
        group_id=GROUP_ADMIN,
        required_permissions=["system:rbac.read"],
        section="People & access",
    ),
    NavEntry(
        entry_id="admin.sessions",
        label="Sessions",
        route="/admin/sessions",
        group_id=GROUP_ADMIN,
        required_permissions=["system:auth.read"],
        section="People & access",
    ),
    # Machine identity: service accounts and every API token
    # (webinterface/blueprints/config/routes_tokens.py). A user's own
    # tokens live at /account/api-tokens.
    NavEntry(
        entry_id="admin.api-tokens",
        label="API Tokens",
        route="/admin/api-tokens",
        group_id=GROUP_ADMIN,
        required_permissions=["system:auth.read"],
        section="People & access",
    ),
    NavEntry(
        entry_id="admin.audit",
        label="Audit Logs",
        route="/admin/audit-logs",
        group_id=GROUP_ADMIN,
        required_permissions=["system:audit.read"],
        section="People & access",
    ),
    NavEntry(
        entry_id="admin.variables",
        label="Variables",
        route="/admin/variables",
        group_id=GROUP_ADMIN,
        # There is no ``system:variables.*`` key in the catalog;
        # like Feature Flags, the page is gated by the admin UX
        # signal (the group requires it too).
        required_permissions=["system:ui.admin.view"],
        section="Configuration",
    ),
    NavEntry(
        entry_id="admin.notifications",
        label="Notifications",
        route="/admin/notifications",
        group_id=GROUP_ADMIN,
        required_permissions=["system:notifications.read"],
        section="Configuration",
    ),
    NavEntry(
        entry_id="admin.rpa-job-types",
        label="RPA Job Types",
        route="/admin/rpa-job-types",
        group_id=GROUP_ADMIN,
        required_permissions=["system:rpa.job_types.manage"],
        surfaces=("rpa",),
        section="Configuration",
    ),
    NavEntry(
        entry_id="admin.ui-profile",
        label="UI Profile",
        route="/admin/ui-profile",
        group_id=GROUP_ADMIN,
        required_permissions=["system:ui.profile.manage"],
        section="Configuration",
    ),
    NavEntry(
        entry_id="admin.feature-flags",
        label="Feature Flags",
        route="/admin/feature-flags",
        group_id=GROUP_ADMIN,
        required_permissions=["system:ui.admin.view"],
        section="Configuration",
    ),
    NavEntry(
        entry_id="admin.enrollment-tokens",
        label="Enrollment Tokens",
        route="/admin/enrollment-tokens",
        group_id=GROUP_ADMIN,
        # ``system:resources.manage`` looks unrelated to
        # enrollment, but it is the key the enrollment admin page
        # deliberately guards its routes with (see
        # ``_ADMIN_PERMISSION`` in
        # webinterface/blueprints/config/routes_enrollment.py), so
        # the nav gate matches the page's actual enforcement.
        required_permissions=["system:resources.manage"],
        section="Fleet enrollment",
    ),
    NavEntry(
        entry_id="admin.system-health",
        label="System Health",
        route="/admin/system-health",
        group_id=GROUP_ADMIN,
        required_permissions=["system:ui.admin.view"],
        section="Platform",
    ),
    NavEntry(
        entry_id="admin.extensions",
        label="Extension Registry",
        route="/admin/extensions",
        group_id=GROUP_ADMIN,
        required_permissions=["system:plugin_api.read"],
        section="Platform",
    ),
    # Pychestrate's own update channels (canary / beta / stable
    # releases of the service and agent). Formerly "Release Channels"
    # under Operations and tagged as a Build Automation surface, which
    # read as a project's release channels (audit ORC-31). The route
    # keeps its name so existing links still work.
    NavEntry(
        entry_id="admin.pychestrate-updates",
        label="Pychestrate Updates",
        route="/release-channels",
        group_id=GROUP_ADMIN,
        required_permissions=["system:release_channels.read"],
        section="Platform",
    ),
]


def _all_required_permission_keys() -> List[str]:
    """
        Collect every distinct permission key referenced by any
        group or entry in the manifest.

        :returns: Sorted list of distinct permission keys.
    """
    keys: set = set()
    for group in NAV_GROUPS:
        for key in group.required_permissions:
            keys.add(key)
    for entry in NAV_ENTRIES:
        for key in entry.required_permissions:
            keys.add(key)
    rtnval = sorted(keys)
    return rtnval


def _entry_to_dict(entry: NavEntry) -> Dict[str, Any]:
    """
        Serialize a :class:`NavEntry` to its JSON-response dict.

        :param entry: Entry to serialize.

        :returns: Plain dict suitable for JSON encoding.
    """
    rtnval: Dict[str, Any] = {
        "entry_id": entry.entry_id,
        "label": entry.label,
        "route": entry.route,
        "icon": entry.icon if len(entry.icon) > 0 else None,
        "required_permissions": list(entry.required_permissions),
        "surfaces": list(entry.surfaces),
    }
    if len(entry.section) > 0:
        rtnval["section"] = entry.section
    return rtnval


def _surface_visible(*, tags: Tuple[str, ...], enabled: Optional[set]) -> bool:
    """
        Whether an item tagged with ``tags`` shows under ``enabled``
        surfaces. No tags means core (always visible); ``enabled``
        ``None`` means no surface filtering at all.
    """
    if enabled is None or len(tags) == 0:
        return True
    for tag in tags:
        if str(tag) in enabled:
            return True
    return False


def validate_manifest_surfaces() -> List[str]:
    """
        Startup lint: every surface tag on a group or entry must name
        a known :class:`UiSurface`. Returns the offending tags.

        :returns: List of ``"<entry_id>: <tag>"`` strings (empty when
                  the manifest is clean).
    """
    from ccai.pychestrate.webservice.webinterface.site_shell.ui_profile import (  # noqa: E402
        validate_surface_tags,
    )
    problems: List[str] = []
    for group in NAV_GROUPS:
        for bad in validate_surface_tags(group.surfaces):
            problems.append("{}: {}".format(group.group_id, bad))
    for entry in NAV_ENTRIES:
        for bad in validate_surface_tags(entry.surfaces):
            problems.append("{}: {}".format(entry.entry_id, bad))
    return problems


def hidden_routes_for(*, held_permissions: List[str], enabled_surfaces: Iterable[str]) -> List[str]:
    """
        Routes of the entries the caller may see but the enabled
        surfaces hide. The shell uses these to show the
        hidden-surface notice when such a route is opened by URL.
    """
    held = set(held_permissions)
    enabled = set(str(getattr(x, "value", x)) for x in enabled_surfaces)
    rtnval: List[str] = []
    for entry in NAV_ENTRIES:
        if any(key not in held for key in entry.required_permissions):
            continue
        if len(entry.surfaces) == 0:
            continue
        if _surface_visible(tags=entry.surfaces, enabled=enabled) is False:
            rtnval.append(entry.route)
    return rtnval


def governed_entry_counts() -> Dict[str, int]:
    """
        How many navigation entries each surface tag governs.
    """
    rtnval: Dict[str, int] = {}
    for entry in NAV_ENTRIES:
        for tag in entry.surfaces:
            rtnval[str(tag)] = rtnval.get(str(tag), 0) + 1
    return rtnval


def build_navigation_manifest(
        *,
        held_permissions: List[str],
        enabled_surfaces: Optional[Iterable[str]] = None
    ) -> Dict[str, Any]:
    """
        Build the permission-filtered navigation manifest for a
        caller holding the supplied set of permission keys.

        A group is included only when (a) the caller holds every
        one of the group's ``required_permissions`` AND (b) at
        least one of the group's entries is itself visible. An
        entry is visible only when the caller holds every one of
        the entry's ``required_permissions``.

        :param held_permissions: System-scoped permission keys the
                                 caller's session effectively
                                 holds.

        :returns: Dict of the form
                  ``{"groups": [{"group_id", "label", "icon",
                  "required_permissions", "entries": [...]}]}``.
    """
    held = set(held_permissions)
    enabled: Optional[set] = None
    if enabled_surfaces is not None:
        enabled = set(str(getattr(x, "value", x)) for x in enabled_surfaces)

    groups_payload: List[Dict[str, Any]] = []
    for group in NAV_GROUPS:
        group_visible = True
        for key in group.required_permissions:
            if key not in held:
                group_visible = False
                break
        if group_visible is False:
            continue
        if _surface_visible(tags=group.surfaces, enabled=enabled) is False:
            continue

        visible_entries: List[Dict[str, Any]] = []
        for entry in NAV_ENTRIES:
            if entry.group_id != group.group_id:
                continue
            entry_visible = True
            for key in entry.required_permissions:
                if key not in held:
                    entry_visible = False
                    break
            if entry_visible is False:
                continue
            if _surface_visible(tags=entry.surfaces, enabled=enabled) is False:
                continue
            visible_entries.append(_entry_to_dict(entry))

        if len(visible_entries) == 0:
            # A group with zero visible entries is dropped so the
            # shell's empty-state predicate lines up with what the
            # user actually sees.
            continue

        group_payload: Dict[str, Any] = {
            "group_id": group.group_id,
            "label": group.label,
            "icon": group.icon if len(group.icon) > 0 else None,
            "required_permissions": list(group.required_permissions),
            "entries": visible_entries,
        }
        groups_payload.append(group_payload)

    rtnval: Dict[str, Any] = {"groups": groups_payload}
    return rtnval


__all__ = [
    "PREVIEW_LABEL_SUFFIX",
    "NavEntry",
    "validate_manifest_surfaces",
    "governed_entry_counts",
    "hidden_routes_for",
    "NavGroup",
    "NAV_GROUPS",
    "NAV_ENTRIES",
    "build_navigation_manifest",
]
