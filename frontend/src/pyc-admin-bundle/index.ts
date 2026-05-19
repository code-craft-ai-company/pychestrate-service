/**
 * pyc-admin-bundle -- admin sidebar registration.
 *
 * This bundle's only job is to add the "Admin" group and its
 * entries to the site shell's sidebar registry. The shell document
 * loads this bundle only for paths under `/admin/*` (see the
 * server-side `bundle_registry.py` mapping), so the registration
 * runs at most once per shell-served admin page.
 *
 * No Custom Elements are defined here -- the admin pages still
 * render server-side via the Jinja blueprint templates; this
 * bundle only contributes navigation metadata for the shell.
 *
 * Registration permission keys mirror the catalog in
 * `security/rbac/extensions/core_permissions.py`:
 *
 * - `system:ui.admin.view`     gates the whole "Admin" group.
 * - `system:users.read`        Users / Roles entries.
 * - `system:rbac.read`         Roles entry.
 * - `system:secrets.admin`     Secrets / Scopes entries.
 * - `system:secrets.read`      Secrets list entry.
 * - `system:audit.read`        Audit entry.
 * - `system:auth.read`         Sessions entry.
 *
 * Per `9-site-shell` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it. The
 * per-entry required_permissions further filter individual entries.
 */

interface SidebarEntryDescriptor {
    entryId: string
    label: string
    route: string
    requiredPermissions: readonly string[]
    group?: string | null
}

interface SidebarGroupDescriptor {
    groupId: string
    label: string
    requiredPermissions: readonly string[]
}

interface SidebarRegistryApi {
    registerGroup(group: SidebarGroupDescriptor): void
    registerEntry(entry: SidebarEntryDescriptor): void
}

interface PycSiteShellRegistryHandle {
    sidebar: SidebarRegistryApi
}

const ADMIN_GROUP_ID: string = "admin"

const ADMIN_ENTRIES: readonly SidebarEntryDescriptor[] = [
    {
        entryId: "admin.dashboard",
        label: "Dashboard",
        route: "/admin/dashboard",
        requiredPermissions: [],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.users",
        label: "Users",
        route: "/admin/users",
        requiredPermissions: ["system:users.read"],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.roles",
        label: "Roles",
        route: "/admin/roles",
        requiredPermissions: ["system:rbac.read"],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.variables",
        label: "Variables",
        route: "/admin/variables",
        requiredPermissions: [],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.scopes",
        label: "Secret Scopes",
        route: "/admin/scopes",
        requiredPermissions: ["system:secrets.admin"],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.secrets",
        label: "Secrets",
        route: "/admin/secrets",
        requiredPermissions: ["system:secrets.read"],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.sessions",
        label: "Sessions",
        route: "/admin/sessions",
        requiredPermissions: ["system:auth.read"],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.audit",
        label: "Audit Logs",
        route: "/admin/audit-logs",
        requiredPermissions: ["system:audit.read"],
        group: ADMIN_GROUP_ID,
    },
]

/**
 * Register the admin sidebar group and entries against the shell.
 * Exported so unit tests can drive registration against a stub
 * registry without going through the global window handle.
 *
 * @param sidebar Sidebar-registry API exposed by `<pyc-site-shell>`.
 */
export function register_admin_sidebar(sidebar: SidebarRegistryApi): void {
    sidebar.registerGroup({
        groupId: ADMIN_GROUP_ID,
        label: "Admin",
        requiredPermissions: ["system:ui.admin.view"],
    })
    for (const entry of ADMIN_ENTRIES) {
        sidebar.registerEntry(entry)
    }
    return
}

/**
 * Bundle-load entry point. Looks up `window.pychestrateShell`
 * (published by the shell bundle on connect) and registers the
 * admin sidebar. When the shell handle is not yet on the window
 * -- which happens when the admin bundle's <script> tag is parsed
 * before the shell bundle finishes connecting -- it queues a
 * single microtask retry; the shell publishes the handle
 * synchronously during `connectedCallback`, so a microtask
 * suffices.
 */
function _boot(): void {
    const target = window as unknown as {
        pychestrateShell?: PycSiteShellRegistryHandle
    }

    const handle = target.pychestrateShell
    if (handle !== undefined && handle.sidebar !== undefined) {
        register_admin_sidebar(handle.sidebar)
        return
    }

    queueMicrotask(() => {
        const retry = target.pychestrateShell
        if (retry !== undefined && retry.sidebar !== undefined) {
            register_admin_sidebar(retry.sidebar)
            return
        }
        console.warn(
            "pychestrate.ui.admin.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export const ADMIN_SIDEBAR_ENTRIES: readonly SidebarEntryDescriptor[] =
    ADMIN_ENTRIES

_boot()
