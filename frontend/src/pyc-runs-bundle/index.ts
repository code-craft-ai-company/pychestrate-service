/**
 * pyc-runs-bundle -- runs list sidebar registration + view mount.
 *
 * This bundle does two things on load:
 *
 * 1. Registers the "Runs" sidebar entry (under an "Orchestration"
 *    group) against the site shell's sidebar registry. The entry
 *    is gated on the ``system:runs.read`` permission key -- the
 *    same key the ``GET /api/v1/runs`` REST endpoint requires (see
 *    ``runs/restapi/v1/runs_routes.py``).
 * 2. When the shell-served path is ``/runs`` it mounts the
 *    ``<pyc-runs-list>`` Custom Element into the shell's ``<main>``
 *    region. The element fetches the first page of runs and renders
 *    a paginated, filterable table.
 *
 * The shell document loads this bundle only for paths under
 * ``/runs`` (see the server-side ``bundle_registry.py`` mapping),
 * so the registration runs at most once per shell-served runs page.
 *
 * Per ``9-site-shell`` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it.
 */

import { PycRunsList } from "./runs-list-view.js"

/**
 * Descriptor passed to ``SidebarRegistry.registerEntry``. Mirrors
 * the shape published by ``<pyc-site-shell>``.
 */
interface SidebarEntryDescriptor {
    entryId: string
    label: string
    route: string
    requiredPermissions: readonly string[]
    group?: string | null
}

/**
 * Descriptor passed to ``SidebarRegistry.registerGroup``.
 */
interface SidebarGroupDescriptor {
    groupId: string
    label: string
    requiredPermissions: readonly string[]
}

/**
 * The narrow slice of the shell's sidebar registry this bundle
 * drives.
 */
interface SidebarRegistryApi {
    registerGroup(group: SidebarGroupDescriptor): void
    registerEntry(entry: SidebarEntryDescriptor): void
}

/**
 * The shell handle published on ``window.pychestrateShell`` during
 * ``connectedCallback``.
 */
interface PycSiteShellRegistryHandle {
    sidebar: SidebarRegistryApi
}

/**
 * Group id for the orchestration sidebar group.
 */
const ORCHESTRATION_GROUP_ID: string = "orchestration"

/**
 * Permission key the ``GET /api/v1/runs`` endpoint requires.
 */
const RUNS_READ_PERMISSION: string = "system:runs.read"

/**
 * Route prefix the runs list view owns.
 */
const RUNS_ROUTE: string = "/runs"

/**
 * Custom Element tag name for the runs list view.
 */
const RUNS_LIST_TAG: string = "pyc-runs-list"

/**
 * Dist URL of the runs bundle stylesheet (copied by ``build.mjs``).
 */
const RUNS_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-runs-bundle.css"

/**
 * Inject the runs bundle stylesheet ``<link>`` into the document
 * head exactly once. The build copies ``runs-list.css`` to a
 * stable dist URL; the bundle owns loading it because the shell
 * document only references the shell's own stylesheet.
 */
export function ensure_runs_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-runs-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = RUNS_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-runs-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The single sidebar entry this bundle contributes.
 */
const RUNS_ENTRY: SidebarEntryDescriptor = {
    entryId: "orchestration.runs",
    label: "Runs",
    route: RUNS_ROUTE,
    requiredPermissions: [RUNS_READ_PERMISSION],
    group: ORCHESTRATION_GROUP_ID,
}

/**
 * Register the orchestration sidebar group and the runs entry
 * against the shell. Exported so unit tests can drive registration
 * against a stub registry without going through the global window
 * handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_runs_sidebar(sidebar: SidebarRegistryApi): void {
    sidebar.registerGroup({
        groupId: ORCHESTRATION_GROUP_ID,
        label: "Orchestration",
        requiredPermissions: [RUNS_READ_PERMISSION],
    })
    sidebar.registerEntry(RUNS_ENTRY)
    return
}

/**
 * Define the ``<pyc-runs-list>`` Custom Element when running in a
 * browser context. Idempotent -- a second call is a no-op.
 */
export function define_runs_list_element(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(RUNS_LIST_TAG) === undefined) {
        customElements.define(RUNS_LIST_TAG, PycRunsList)
    }
    return
}

/**
 * Mount the ``<pyc-runs-list>`` element into the shell's ``<main>``
 * region when the current path is ``/runs``. The shell leaves
 * ``<main>`` empty whenever at least one sidebar entry is visible,
 * so this bundle owns the main-region content for its own route.
 *
 * A no-op when the path is not ``/runs`` or the main region is not
 * yet in the document.
 */
export function mount_runs_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const path = window.location.pathname
    if (path !== RUNS_ROUTE) {
        return
    }
    const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main")
    if (main === null) {
        return
    }
    const existing = main.querySelector(RUNS_LIST_TAG)
    if (existing !== null) {
        return
    }
    define_runs_list_element()
    ensure_runs_stylesheet()
    const view = document.createElement(RUNS_LIST_TAG)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * runs sidebar, then mounts the view. When the shell handle is not
 * yet on the window -- which happens when this bundle's
 * ``<script>`` tag is parsed before the shell bundle finishes
 * connecting -- it queues a single microtask retry; the shell
 * publishes the handle synchronously during ``connectedCallback``,
 * so a microtask suffices.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    register_runs_sidebar(handle.sidebar)
    mount_runs_view_if_active()
    return
}

function _boot(): void {
    define_runs_list_element()

    const target = window as unknown as {
        pychestrateShell?: PycSiteShellRegistryHandle
    }

    const handle = target.pychestrateShell
    if (handle !== undefined && handle.sidebar !== undefined) {
        _register_against(handle)
        return
    }

    queueMicrotask(() => {
        const retry = target.pychestrateShell
        if (retry !== undefined && retry.sidebar !== undefined) {
            _register_against(retry)
            return
        }
        console.warn(
            "pychestrate.ui.runs.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycRunsList } from "./runs-list-view.js"
export type {
    Run,
    RunPage,
    PageMeta,
    RunsListState,
} from "./runs-list-view.js"

if (typeof window !== "undefined") {
    _boot()
}
