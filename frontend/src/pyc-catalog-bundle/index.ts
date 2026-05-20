/**
 * pyc-catalog-bundle -- test-catalog sidebar registration + view
 * mount.
 *
 * This bundle does two things on load:
 *
 * 1. Registers the "Test Catalog" sidebar entry under the
 *    "Orchestration" group (the same group ``pyc-runs-bundle``
 *    creates -- registering a group is idempotent on its id). The
 *    entry is gated on the ``system:test_catalog.read`` permission
 *    key -- the same key the ``GET /api/v1/projects/{id}/
 *    test-catalog`` REST endpoint requires.
 * 2. When the shell-served path is ``/test-catalog`` it mounts the
 *    ``<pyc-test-catalog>`` Custom Element into the shell's
 *    ``<main>`` region. The element renders a project selector and
 *    a paginated catalog table with import + trigger-run actions.
 *
 * The shell document loads this bundle only for paths under
 * ``/test-catalog`` (see the server-side ``bundle_registry.py``
 * mapping), so the registration runs at most once per shell-served
 * catalog page.
 */

import { PycTestCatalog } from "./catalog-view.js"

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
 * Group id for the orchestration sidebar group. Matches the id
 * ``pyc-runs-bundle`` registers so the catalog entry joins the
 * same group rather than spawning a duplicate.
 */
const ORCHESTRATION_GROUP_ID: string = "orchestration"

/**
 * Permission key the ``GET …/test-catalog`` endpoint requires.
 */
const CATALOG_READ_PERMISSION: string = "system:test_catalog.read"

/**
 * Route prefix the test-catalog view owns.
 */
const CATALOG_ROUTE: string = "/test-catalog"

/**
 * Custom Element tag name for the test-catalog view.
 */
const CATALOG_TAG: string = "pyc-test-catalog"

/**
 * Dist URL of the catalog bundle stylesheet (copied by
 * ``build.mjs``).
 */
const CATALOG_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-catalog-bundle.css"

/**
 * Inject the catalog bundle stylesheet ``<link>`` into the document
 * head exactly once. The build copies ``catalog.css`` to a stable
 * dist URL; the bundle owns loading it because the shell document
 * only references the shell's own stylesheet.
 */
export function ensure_catalog_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-catalog-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = CATALOG_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-catalog-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The single sidebar entry this bundle contributes.
 */
const CATALOG_ENTRY: SidebarEntryDescriptor = {
    entryId: "orchestration.test-catalog",
    label: "Test Catalog",
    route: CATALOG_ROUTE,
    requiredPermissions: [CATALOG_READ_PERMISSION],
    group: ORCHESTRATION_GROUP_ID,
}

/**
 * Register the orchestration sidebar group and the catalog entry
 * against the shell. Registering the group is idempotent on its
 * id, so it is safe even when ``pyc-runs-bundle`` already created
 * it. Exported so unit tests can drive registration against a stub
 * registry without going through the global window handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_catalog_sidebar(sidebar: SidebarRegistryApi): void {
    sidebar.registerGroup({
        groupId: ORCHESTRATION_GROUP_ID,
        label: "Orchestration",
        requiredPermissions: [CATALOG_READ_PERMISSION],
    })
    sidebar.registerEntry(CATALOG_ENTRY)
    return
}

/**
 * Define the ``<pyc-test-catalog>`` Custom Element when running in
 * a browser context. Idempotent -- a second call is a no-op for an
 * already-defined tag.
 */
export function define_catalog_element(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(CATALOG_TAG) === undefined) {
        customElements.define(CATALOG_TAG, PycTestCatalog)
    }
    return
}

/**
 * Classify a shell-served path against the route this bundle owns.
 * ``/test-catalog`` (exact, with or without a trailing slash) maps
 * to the catalog view; any other path is unowned.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns ``"catalog"`` | ``"none"``.
 */
export function classify_catalog_route(path: string): string {
    if (typeof path !== "string") {
        const rtnval = "none"
        return rtnval
    }
    let working = path
    const query_index = working.indexOf("?")
    if (query_index >= 0) {
        working = working.slice(0, query_index)
    }
    if (working === CATALOG_ROUTE || working === CATALOG_ROUTE + "/") {
        const rtnval = "catalog"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Mount the ``<pyc-test-catalog>`` view into the shell's
 * ``<main>`` region when the current path is the catalog route. A
 * no-op when the path is not the catalog route or the main region
 * is not yet in the document. Idempotent -- when the view is
 * already mounted nothing is replaced.
 */
export function mount_catalog_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_catalog_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const main = document.querySelector(
        "pyc-site-shell main.pyc-site-shell__main",
    )
    if (main === null) {
        return
    }
    const existing = main.querySelector(CATALOG_TAG)
    if (existing !== null) {
        return
    }
    define_catalog_element()
    ensure_catalog_stylesheet()
    const view = document.createElement(CATALOG_TAG)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * catalog sidebar, then mounts the view. When the shell handle is
 * not yet on the window it queues a single microtask retry; the
 * shell publishes the handle synchronously during
 * ``connectedCallback``, so a microtask suffices.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    register_catalog_sidebar(handle.sidebar)
    mount_catalog_view_if_active()
    return
}

function _boot(): void {
    define_catalog_element()

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
            "pychestrate.ui.catalog.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycTestCatalog } from "./catalog-view.js"
export type {
    TestCatalogEntry,
    CatalogPage,
    PageMeta,
    ProjectOption,
    TriggeredRun,
    TriggerOutcome,
    CatalogViewState,
} from "./catalog-view.js"
export {
    build_catalog_query_url,
    build_test_runs_url,
    build_catalog_import_url,
    selection_summary,
    format_timestamp,
    has_next_page,
    has_previous_page,
    trigger_message_for_status,
} from "./catalog-view.js"

if (typeof window !== "undefined") {
    _boot()
}
