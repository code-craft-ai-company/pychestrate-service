/**
 * pyc-admin-bundle -- admin sidebar registration + shell-native
 * admin view mount.
 *
 * This bundle contributes the "Admin" sidebar group + entries and,
 * since PR p21f (audit items 9-admin-ui + E-extension-registry-ui),
 * mounts the shell-native admin Web Component views:
 *
 * * ``<pyc-admin-overview>``      -- the ``/admin`` landing page
 *   composing system-health, feature-flags and an
 *   extension-registry summary.
 * * ``<pyc-feature-flags>``       -- ``/admin/feature-flags``.
 * * ``<pyc-extension-registry>``  -- ``/admin/extensions``.
 * * ``<pyc-system-health>``       -- ``/admin/system-health``.
 *
 * The shell document loads this bundle for paths under
 * ``/admin/*`` (see the server-side ``bundle_registry.py``
 * mapping). For the four routes above the bundle replaces the
 * shell's ``<main>`` content with the route-appropriate Custom
 * Element -- so the new WC overview wins for the bare ``/admin``
 * path. The legacy Vue admin pages (users / roles / secrets /
 * audit / enrollment) keep working shell-wrapped: this bundle
 * only mounts a WC view for the four routes it explicitly owns and
 * leaves every other ``/admin/*`` path untouched.
 *
 * Registration permission keys mirror the catalog in
 * ``security/rbac/extensions/core_permissions.py``:
 *
 * - ``system:ui.admin.view``   gates the whole "Admin" group.
 * - ``system:users.read``      Users / Roles entries.
 * - ``system:rbac.read``       Roles entry.
 * - ``system:secrets.admin``   Secrets / Scopes entries.
 * - ``system:secrets.read``    Secrets list entry.
 * - ``system:audit.read``      Audit entry.
 * - ``system:auth.read``       Sessions entry.
 * - ``system:resources.manage`` Enrollment Tokens entry.
 *
 * Per ``9-site-shell`` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it. The
 * per-entry required_permissions further filter individual
 * entries.
 */

import { register_admin_palette_provider } from "./palette/admin-search-provider.js"
import { PycAdminOverview } from "./admin-overview-view.js"
import { PycFeatureFlags } from "./feature-flags-view.js"
import { PycExtensionRegistry } from "./extension-registry-view.js"
import { PycSystemHealth } from "./system-health-view.js"

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

interface PaletteProviderDescriptor {
    providerId: string
    label: string
    requiredPermissions?: readonly string[]
    timeoutMs?: number
    query: (q: string) => Promise<Array<{
        id: string
        label: string
        description?: string | null
        route?: string | null
    }>>
}

interface PaletteRegistryApi {
    registerProvider(provider: PaletteProviderDescriptor): void
}

interface PycSiteShellRegistryHandle {
    sidebar: SidebarRegistryApi
    palette?: PaletteRegistryApi
}

const ADMIN_GROUP_ID: string = "admin"

/**
 * Custom Element tag for the ``/admin`` overview landing page.
 */
const OVERVIEW_TAG: string = "pyc-admin-overview"

/**
 * Custom Element tag for the feature-flags view.
 */
const FEATURE_FLAGS_TAG: string = "pyc-feature-flags"

/**
 * Custom Element tag for the extension-registry view.
 */
const EXTENSION_REGISTRY_TAG: string = "pyc-extension-registry"

/**
 * Custom Element tag for the system-health view.
 */
const SYSTEM_HEALTH_TAG: string = "pyc-system-health"

/**
 * Route the ``/admin`` overview view owns (the bare admin path).
 */
const OVERVIEW_ROUTE: string = "/admin"

/**
 * Route alias the overview view also owns.
 */
const OVERVIEW_ALIAS_ROUTE: string = "/admin/overview"

/**
 * Route the feature-flags view owns.
 */
const FEATURE_FLAGS_ROUTE: string = "/admin/feature-flags"

/**
 * Route the extension-registry view owns.
 */
const EXTENSION_REGISTRY_ROUTE: string = "/admin/extensions"

/**
 * Route the system-health view owns.
 */
const SYSTEM_HEALTH_ROUTE: string = "/admin/system-health"

/**
 * Dist URL of the admin bundle stylesheet (copied by
 * ``build.mjs``).
 */
const ADMIN_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-admin-bundle.css"

const ADMIN_ENTRIES: readonly SidebarEntryDescriptor[] = [
    {
        entryId: "admin.overview",
        label: "Overview",
        route: OVERVIEW_ROUTE,
        requiredPermissions: ["system:ui.admin.view"],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.dashboard",
        label: "Dashboard",
        route: "/admin/dashboard",
        requiredPermissions: [],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.feature-flags",
        label: "Feature Flags",
        route: FEATURE_FLAGS_ROUTE,
        requiredPermissions: ["system:ui.admin.view"],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.extensions",
        label: "Extension Registry",
        route: EXTENSION_REGISTRY_ROUTE,
        requiredPermissions: ["system:plugin_api.read"],
        group: ADMIN_GROUP_ID,
    },
    {
        entryId: "admin.system-health",
        label: "System Health",
        route: SYSTEM_HEALTH_ROUTE,
        requiredPermissions: ["system:ui.admin.view"],
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
    {
        entryId: "admin.enrollment-tokens",
        label: "Enrollment Tokens",
        route: "/admin/enrollment-tokens",
        requiredPermissions: ["system:resources.manage"],
        group: ADMIN_GROUP_ID,
    },
]

/**
 * Inject the admin bundle stylesheet ``<link>`` into the document
 * head exactly once. The build copies ``admin.css`` to a stable
 * dist URL; the bundle owns loading it because the shell document
 * only references the shell's own stylesheet.
 */
export function ensure_admin_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-admin-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = ADMIN_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-admin-bundle")
    document.head.appendChild(link)
    return
}

/**
 * Register the admin sidebar group and entries against the shell.
 * Exported so unit tests can drive registration against a stub
 * registry without going through the global window handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
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
 * Define the admin Custom Elements when running in a browser
 * context. Idempotent -- a second call is a no-op for an
 * already-defined tag.
 */
export function define_admin_elements(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(OVERVIEW_TAG) === undefined) {
        customElements.define(OVERVIEW_TAG, PycAdminOverview)
    }
    if (customElements.get(FEATURE_FLAGS_TAG) === undefined) {
        customElements.define(FEATURE_FLAGS_TAG, PycFeatureFlags)
    }
    if (customElements.get(EXTENSION_REGISTRY_TAG) === undefined) {
        customElements.define(EXTENSION_REGISTRY_TAG, PycExtensionRegistry)
    }
    if (customElements.get(SYSTEM_HEALTH_TAG) === undefined) {
        customElements.define(SYSTEM_HEALTH_TAG, PycSystemHealth)
    }
    return
}

/**
 * Classify a shell-served path against the admin routes this
 * bundle mounts a Web Component view for. Only the four explicit
 * shell-native routes are owned; the legacy Vue admin pages
 * (users / roles / secrets / audit / enrollment / dashboard)
 * classify as ``"none"`` so this bundle leaves their
 * shell-wrapped fragment untouched.
 *
 * @param path A request path (typically
 *             ``window.location.pathname``).
 *
 * @returns A route classification, or ``"none"`` for an unowned
 *          path.
 */
export function classify_admin_route(path: string): string {
    if (typeof path !== "string") {
        const rtnval = "none"
        return rtnval
    }
    let working = path
    const query_index = working.indexOf("?")
    if (query_index >= 0) {
        working = working.slice(0, query_index)
    }
    if (working.length > 1 && working.endsWith("/") === true) {
        working = working.slice(0, working.length - 1)
    }
    if (working === FEATURE_FLAGS_ROUTE) {
        const rtnval = "feature-flags"
        return rtnval
    }
    if (working === EXTENSION_REGISTRY_ROUTE) {
        const rtnval = "extensions"
        return rtnval
    }
    if (working === SYSTEM_HEALTH_ROUTE) {
        const rtnval = "system-health"
        return rtnval
    }
    if (working === OVERVIEW_ROUTE || working === OVERVIEW_ALIAS_ROUTE) {
        const rtnval = "overview"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Resolve a route classification to its Custom Element tag.
 *
 * @param route A route classification from
 *              :func:`classify_admin_route`.
 *
 * @returns The matching tag name, or ``""`` for an unowned route.
 */
export function tag_for_admin_route(route: string): string {
    if (route === "overview") {
        const rtnval = OVERVIEW_TAG
        return rtnval
    }
    if (route === "feature-flags") {
        const rtnval = FEATURE_FLAGS_TAG
        return rtnval
    }
    if (route === "extensions") {
        const rtnval = EXTENSION_REGISTRY_TAG
        return rtnval
    }
    if (route === "system-health") {
        const rtnval = SYSTEM_HEALTH_TAG
        return rtnval
    }
    const rtnval = ""
    return rtnval
}

/**
 * Mount the route-appropriate admin view into the shell's
 * ``<main>`` region. A no-op when the path is not an owned admin
 * route or the main region is not yet in the document.
 * Idempotent -- when the correct view is already mounted nothing
 * is replaced.
 */
export function mount_admin_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_admin_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const target_tag = tag_for_admin_route(route)
    if (target_tag.length === 0) {
        return
    }
    const main = document.querySelector(
        "pyc-site-shell main.pyc-site-shell__main",
    )
    if (main === null) {
        return
    }
    const existing = main.querySelector(target_tag)
    if (existing !== null) {
        return
    }
    define_admin_elements()
    ensure_admin_stylesheet()
    const view = document.createElement(target_tag)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * admin sidebar, then mounts the route-appropriate view.
 *
 * The admin bundle and the shell bundle are independent
 * ``<script type="module">`` tags with no guaranteed relative
 * execution order. When the admin bundle runs first the shell
 * handle is not yet on ``window``; a single microtask retry is
 * NOT sufficient (the shell may not have connected by then), and
 * failing to register leaves the shell stuck on the
 * zero-permissions empty state. The boot path therefore registers
 * eagerly when the handle is already present, and otherwise binds
 * a one-shot ``pyc-site-shell-ready`` listener -- the shell emits
 * that event after ``connectedCallback`` -- so registration is
 * guaranteed regardless of load order.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    register_admin_sidebar(handle.sidebar)
    if (handle.palette !== undefined && handle.palette !== null) {
        register_admin_palette_provider(handle.palette)
    }
    mount_admin_view_if_active()
    return
}

function _boot(): void {
    define_admin_elements()

    const target = window as unknown as {
        pychestrateShell?: PycSiteShellRegistryHandle
    }

    const handle = target.pychestrateShell
    if (handle !== undefined && handle.sidebar !== undefined) {
        _register_against(handle)
        return
    }

    let registered = false
    const try_register = (): boolean => {
        if (registered === true) {
            return true
        }
        const current = target.pychestrateShell
        if (current !== undefined && current.sidebar !== undefined) {
            registered = true
            _register_against(current)
            return true
        }
        return false
    }

    // Fast path -- the shell handle frequently lands within a
    // microtask of the admin bundle's body running.
    queueMicrotask(() => {
        try_register()
    })

    // Reliable path -- the shell emits ``pyc-site-shell-ready``
    // once ``connectedCallback`` has published the handle. This
    // fires whether the shell connected before or after the admin
    // bundle's <script> body, closing the load-order race. Guard
    // ``addEventListener`` so a non-browser host (the node-based
    // bundle tests stub ``window`` as a bare object) degrades to
    // the microtask path instead of throwing at import time.
    if (typeof window.addEventListener === "function") {
        const on_shell_ready = (): void => {
            if (try_register() === true) {
                window.removeEventListener(
                    "pyc-site-shell-ready", on_shell_ready,
                )
            }
        }
        window.addEventListener("pyc-site-shell-ready", on_shell_ready)
    }
    return
}

export const ADMIN_SIDEBAR_ENTRIES: readonly SidebarEntryDescriptor[] =
    ADMIN_ENTRIES

export { PycAdminOverview } from "./admin-overview-view.js"
export { PycFeatureFlags } from "./feature-flags-view.js"
export { PycExtensionRegistry } from "./extension-registry-view.js"
export { PycSystemHealth } from "./system-health-view.js"
export {
    fetch_system_health,
    health_status_tone,
} from "./system-health-view.js"
export type {
    SystemHealthDocument,
    SystemHealthSubsystem,
    SystemHealthBackend,
} from "./system-health-view.js"
export {
    FLAGS_PATH,
    build_flag_url,
    flag_state_tone,
    next_flag_state,
    toggle_message_for_status,
} from "./feature-flags-view.js"
export type {
    FeatureFlagEntry,
    FlagToggleOutcome,
} from "./feature-flags-view.js"
export {
    EXT_LISTING_PATH,
    group_routes_by_extension,
    mount_state_tone,
} from "./extension-registry-view.js"
export type {
    ExtensionRouteEntry,
    ExtensionListingResponse,
    LoadedExtension,
} from "./extension-registry-view.js"

if (typeof window !== "undefined") {
    _boot()
}
