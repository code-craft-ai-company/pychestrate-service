/**
 * pyc-builds-bundle -- builds list sidebar registration + view
 * mount.
 *
 * This bundle does two things on load:
 *
 * 1. Registers the "Builds" sidebar entry (under the shared
 *    "Orchestration" group the runs / catalog bundles use)
 *    against the site shell's sidebar registry. The entry is
 *    gated on the ``system:builds.read`` permission key -- the
 *    same key the ``GET …/builds`` REST endpoint requires.
 * 2. When the shell-served path is ``/builds`` it mounts the
 *    ``<pyc-builds-list>`` Custom Element; ``/builds/{build_id}``
 *    mounts ``<pyc-build-detail>``. The element is mounted into
 *    the shell's ``<main>`` region.
 *
 * The shell document loads this bundle only for paths under
 * ``/builds`` (see the server-side ``bundle_registry.py``
 * mapping), so the registration runs at most once per shell-
 * served builds page.
 *
 * Per ``9-site-shell`` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it.
 */

import { PycBuildsList } from "./builds-list-view.js"
import { PycBuildDetail, build_id_from_path } from "./build-detail-view.js"

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
 * Group id for the shared orchestration sidebar group.
 */
const ORCHESTRATION_GROUP_ID: string = "orchestration"

/**
 * Permission key the ``GET …/builds`` endpoint requires.
 */
const BUILDS_READ_PERMISSION: string = "system:builds.read"

/**
 * Route prefix the builds list view owns.
 */
const BUILDS_ROUTE: string = "/builds"

/**
 * Custom Element tag name for the builds list view.
 */
const BUILDS_LIST_TAG: string = "pyc-builds-list"

/**
 * Custom Element tag name for the build detail view.
 */
const BUILD_DETAIL_TAG: string = "pyc-build-detail"

/**
 * Dist URL of the builds bundle stylesheet (copied by
 * ``build.mjs``).
 */
const BUILDS_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-builds-bundle.css"

/**
 * Inject the builds bundle stylesheet ``<link>`` into the document
 * head exactly once. The build copies ``builds.css`` to a stable
 * dist URL; the bundle owns loading it because the shell document
 * only references the shell's own stylesheet.
 */
export function ensure_builds_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-builds-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = BUILDS_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-builds-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The single sidebar entry this bundle contributes.
 */
const BUILDS_ENTRY: SidebarEntryDescriptor = {
    entryId: "orchestration.builds",
    label: "Builds",
    route: BUILDS_ROUTE,
    requiredPermissions: [BUILDS_READ_PERMISSION],
    group: ORCHESTRATION_GROUP_ID,
}

/**
 * Register the orchestration sidebar group and the builds entry
 * against the shell. Exported so unit tests can drive registration
 * against a stub registry without going through the global window
 * handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_builds_sidebar(sidebar: SidebarRegistryApi): void {
    sidebar.registerGroup({
        groupId: ORCHESTRATION_GROUP_ID,
        label: "Orchestration",
        requiredPermissions: [BUILDS_READ_PERMISSION],
    })
    sidebar.registerEntry(BUILDS_ENTRY)
    return
}

/**
 * Define the ``<pyc-builds-list>`` and ``<pyc-build-detail>``
 * Custom Elements when running in a browser context. Idempotent --
 * a second call is a no-op for an already-defined tag.
 */
export function define_builds_elements(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(BUILDS_LIST_TAG) === undefined) {
        customElements.define(BUILDS_LIST_TAG, PycBuildsList)
    }
    if (customElements.get(BUILD_DETAIL_TAG) === undefined) {
        customElements.define(BUILD_DETAIL_TAG, PycBuildDetail)
    }
    return
}

/**
 * Classify a shell-served path against the routes this bundle
 * owns. ``/builds`` (exact) maps to the list view;
 * ``/builds/{id}`` maps to the detail view. Any other path is
 * unowned.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns ``"list"`` | ``"detail"`` | ``"none"``.
 */
export function classify_builds_route(path: string): string {
    if (typeof path !== "string") {
        const rtnval = "none"
        return rtnval
    }
    let working = path
    const query_index = working.indexOf("?")
    if (query_index >= 0) {
        working = working.slice(0, query_index)
    }
    if (working === BUILDS_ROUTE || working === BUILDS_ROUTE + "/") {
        const rtnval = "list"
        return rtnval
    }
    const detail_id = build_id_from_path(working)
    if (detail_id.length > 0) {
        const rtnval = "detail"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Mount the route-appropriate builds view into the shell's
 * ``<main>`` region. ``/builds`` (exact) mounts
 * ``<pyc-builds-list>``; ``/builds/{build_id}`` mounts
 * ``<pyc-build-detail>``. The shell leaves ``<main>`` empty
 * whenever at least one sidebar entry is visible, so this bundle
 * owns the main-region content for its own routes.
 *
 * A no-op when the path is not a builds route or the main region
 * is not yet in the document. Idempotent -- when the correct view
 * is already mounted nothing is replaced.
 */
export function mount_builds_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_builds_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main")
    if (main === null) {
        return
    }
    const target_tag = route === "detail" ? BUILD_DETAIL_TAG : BUILDS_LIST_TAG
    const existing = main.querySelector(target_tag)
    if (existing !== null) {
        return
    }
    define_builds_elements()
    ensure_builds_stylesheet()
    const view = document.createElement(target_tag)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * builds sidebar, then mounts the view. When the shell handle is
 * not yet on the window -- which happens when this bundle's
 * ``<script>`` tag is parsed before the shell bundle finishes
 * connecting -- it queues a single microtask retry.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    register_builds_sidebar(handle.sidebar)
    mount_builds_view_if_active()
    return
}

function _boot(): void {
    define_builds_elements()

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
            "pychestrate.ui.builds.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycBuildsList } from "./builds-list-view.js"
export type {
    BuildRun,
    BuildRunPage,
    BuildToolchainSnapshot,
    SourceIntegrationOption,
    ProjectOption,
    TriggerOutcome,
    PageMeta,
    BuildsListState,
} from "./builds-list-view.js"
export {
    build_builds_query_url,
    build_builds_collection_url,
    build_source_integrations_url,
    short_id,
    format_timestamp,
    build_state_tone,
    is_terminal_build_state,
    has_next_page,
    has_previous_page,
    trigger_message_for_status,
    parse_runner_inputs,
    BUILD_STATES,
    TERMINAL_BUILD_STATES,
} from "./builds-list-view.js"
export {
    PycBuildDetail,
    build_id_from_path,
    is_valid_build_id,
    build_detail_url,
    build_artifacts_url,
} from "./build-detail-view.js"
export type {
    BuildArtifact,
    BuildArtifactPage,
    PollStatus,
    BuildDetailState,
} from "./build-detail-view.js"

if (typeof window !== "undefined") {
    _boot()
}
