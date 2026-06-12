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
from typing import Any, Dict, List


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
    """
    entry_id: str
    label: str
    route: str
    group_id: str
    required_permissions: List[str] = field(default_factory=list)
    icon: str = ""


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
        required_permissions=["system:projects.read"],
    ),
    NavGroup(
        group_id=GROUP_ORCHESTRATION,
        label="Orchestration",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_INSIGHTS,
        label="Insights",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_FLEET,
        label="Fleet",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_OPERATIONS,
        label="Operations",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_SYSTEM,
        label="System",
        required_permissions=[],
    ),
    NavGroup(
        group_id=GROUP_ADMIN,
        label="Admin",
        required_permissions=["system:ui.admin.view"],
    ),
]


# The authoritative entry list. Each entry mirrors the descriptor
# the corresponding feature bundle historically registered. The
# permission keys are the same ``system:<feature>.read`` keys the
# bundles used (verified against the in-tree permission catalog).
NAV_ENTRIES: List[NavEntry] = [
    # ---- Projects ------------------------------------------------
    NavEntry(
        entry_id="projects.dashboard",
        label="Projects",
        route="/projects",
        group_id=GROUP_PROJECTS,
        required_permissions=["system:projects.read"],
    ),
    # ---- Orchestration -------------------------------------------
    NavEntry(
        entry_id="orchestration.runs",
        label="Runs",
        route="/runs",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:runs.read"],
    ),
    NavEntry(
        entry_id="orchestration.builds",
        label="Builds",
        route="/builds",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:builds.read"],
    ),
    NavEntry(
        entry_id="orchestration.pipelines",
        label="Pipelines",
        route="/pipelines",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:pipelines.read"],
    ),
    NavEntry(
        entry_id="orchestration.test-catalog",
        label="Test Catalog",
        route="/test-catalog",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:test_catalog.read"],
    ),
    NavEntry(
        entry_id="orchestration.environments",
        label="Environments",
        route="/environments",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:environments.read"],
    ),
    NavEntry(
        entry_id="orchestration.provisioning",
        label="Provisioning",
        route="/provisioning-runs",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:provisioning.read"],
    ),
    NavEntry(
        entry_id="orchestration.guards",
        label="Blast-Radius Guards",
        route="/blast-radius-guards",
        group_id=GROUP_ORCHESTRATION,
        required_permissions=["system:guards.read"],
    ),
    # ---- Insights ------------------------------------------------
    NavEntry(
        entry_id="insights.test-metrics",
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
        required_permissions=["system:metrics.read"],
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
        label="Alert Rules",
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
        label="Resources",
        route="/resource-pools",
        group_id=GROUP_FLEET,
        required_permissions=["system:resources.read"],
    ),
    # ---- Operations ----------------------------------------------
    NavEntry(
        entry_id="operations.webhooks",
        label="Webhooks",
        route="/webhooks",
        group_id=GROUP_OPERATIONS,
        required_permissions=["system:webhooks.read"],
    ),
    NavEntry(
        entry_id="operations.release-channels",
        label="Release Channels",
        route="/release-channels",
        group_id=GROUP_OPERATIONS,
        required_permissions=["system:release_channels.read"],
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
        entry_id="admin.feature-flags",
        label="Feature Flags",
        route="/admin/feature-flags",
        group_id=GROUP_ADMIN,
        required_permissions=["system:ui.admin.view"],
    ),
    NavEntry(
        entry_id="admin.extensions",
        label="Extension Registry",
        route="/admin/extensions",
        group_id=GROUP_ADMIN,
        required_permissions=["system:plugin_api.read"],
    ),
    NavEntry(
        entry_id="admin.system-health",
        label="System Health",
        route="/admin/system-health",
        group_id=GROUP_ADMIN,
        required_permissions=["system:ui.admin.view"],
    ),
    NavEntry(
        entry_id="admin.users",
        label="Users",
        route="/admin/users",
        group_id=GROUP_ADMIN,
        required_permissions=["system:users.read"],
    ),
    NavEntry(
        entry_id="admin.roles",
        label="Roles",
        route="/admin/roles",
        group_id=GROUP_ADMIN,
        required_permissions=["system:rbac.read"],
    ),
    NavEntry(
        entry_id="admin.scopes",
        label="Secret Scopes",
        route="/admin/scopes",
        group_id=GROUP_ADMIN,
        required_permissions=["system:secrets.admin"],
    ),
    NavEntry(
        entry_id="admin.secrets",
        label="Secrets",
        route="/admin/secrets",
        group_id=GROUP_ADMIN,
        required_permissions=["system:secrets.read"],
    ),
    NavEntry(
        entry_id="admin.sessions",
        label="Sessions",
        route="/admin/sessions",
        group_id=GROUP_ADMIN,
        required_permissions=["system:auth.read"],
    ),
    NavEntry(
        entry_id="admin.audit",
        label="Audit Logs",
        route="/admin/audit-logs",
        group_id=GROUP_ADMIN,
        required_permissions=["system:audit.read"],
    ),
    NavEntry(
        entry_id="admin.enrollment-tokens",
        label="Enrollment Tokens",
        route="/admin/enrollment-tokens",
        group_id=GROUP_ADMIN,
        required_permissions=["system:resources.manage"],
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
    }
    return rtnval


def build_navigation_manifest(
        *,
        held_permissions: List[str]
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

    groups_payload: List[Dict[str, Any]] = []
    for group in NAV_GROUPS:
        group_visible = True
        for key in group.required_permissions:
            if key not in held:
                group_visible = False
                break
        if group_visible is False:
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
    "NavEntry",
    "NavGroup",
    "NAV_GROUPS",
    "NAV_ENTRIES",
    "build_navigation_manifest",
]
