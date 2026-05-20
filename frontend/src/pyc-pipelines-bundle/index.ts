/**
 * pyc-pipelines-bundle -- pipelines list sidebar registration +
 * view mount.
 *
 * This bundle does two things on load:
 *
 * 1. Registers the "Pipelines" sidebar entry (under the shared
 *    "Orchestration" group the builds / runs / catalog bundles
 *    use) against the site shell's sidebar registry. The entry is
 *    gated on the ``system:pipelines.read`` permission key -- the
 *    same key the ``GET …/pipelines`` REST endpoint requires.
 * 2. When the shell-served path is ``/pipelines`` it mounts the
 *    ``<pyc-pipelines-list>`` Custom Element;
 *    ``/pipelines/{pipeline_id}`` mounts ``<pyc-pipeline-detail>``.
 *    The element is mounted into the shell's ``<main>`` region.
 *
 * The shell document loads this bundle only for paths under
 * ``/pipelines`` (see the server-side ``bundle_registry.py``
 * mapping), so the registration runs at most once per shell-served
 * pipelines page.
 */

import { PycPipelinesList } from "./pipelines-list-view.js"
import { PycPipelineDetail, pipeline_id_from_path } from "./pipeline-detail-view.js"

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
 * Permission key the ``GET …/pipelines`` endpoint requires.
 */
const PIPELINES_READ_PERMISSION: string = "system:pipelines.read"

/**
 * Route prefix the pipelines list view owns.
 */
const PIPELINES_ROUTE: string = "/pipelines"

/**
 * Custom Element tag name for the pipelines list view.
 */
const PIPELINES_LIST_TAG: string = "pyc-pipelines-list"

/**
 * Custom Element tag name for the pipeline detail view.
 */
const PIPELINE_DETAIL_TAG: string = "pyc-pipeline-detail"

/**
 * Dist URL of the pipelines bundle stylesheet (copied by
 * ``build.mjs``).
 */
const PIPELINES_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-pipelines-bundle.css"

/**
 * Inject the pipelines bundle stylesheet ``<link>`` into the
 * document head exactly once. The build copies ``pipelines.css``
 * to a stable dist URL; the bundle owns loading it because the
 * shell document only references the shell's own stylesheet.
 */
export function ensure_pipelines_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-pipelines-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = PIPELINES_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-pipelines-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The single sidebar entry this bundle contributes.
 */
const PIPELINES_ENTRY: SidebarEntryDescriptor = {
    entryId: "orchestration.pipelines",
    label: "Pipelines",
    route: PIPELINES_ROUTE,
    requiredPermissions: [PIPELINES_READ_PERMISSION],
    group: ORCHESTRATION_GROUP_ID,
}

/**
 * Register the orchestration sidebar group and the pipelines entry
 * against the shell. Exported so unit tests can drive registration
 * against a stub registry without going through the global window
 * handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_pipelines_sidebar(sidebar: SidebarRegistryApi): void {
    sidebar.registerGroup({
        groupId: ORCHESTRATION_GROUP_ID,
        label: "Orchestration",
        requiredPermissions: [PIPELINES_READ_PERMISSION],
    })
    sidebar.registerEntry(PIPELINES_ENTRY)
    return
}

/**
 * Define the ``<pyc-pipelines-list>`` and ``<pyc-pipeline-detail>``
 * Custom Elements when running in a browser context. Idempotent --
 * a second call is a no-op for an already-defined tag.
 */
export function define_pipelines_elements(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(PIPELINES_LIST_TAG) === undefined) {
        customElements.define(PIPELINES_LIST_TAG, PycPipelinesList)
    }
    if (customElements.get(PIPELINE_DETAIL_TAG) === undefined) {
        customElements.define(PIPELINE_DETAIL_TAG, PycPipelineDetail)
    }
    return
}

/**
 * Classify a shell-served path against the routes this bundle
 * owns. ``/pipelines`` (exact) maps to the list view;
 * ``/pipelines/{id}`` maps to the detail view. Any other path is
 * unowned.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns ``"list"`` | ``"detail"`` | ``"none"``.
 */
export function classify_pipelines_route(path: string): string {
    if (typeof path !== "string") {
        const rtnval = "none"
        return rtnval
    }
    let working = path
    const query_index = working.indexOf("?")
    if (query_index >= 0) {
        working = working.slice(0, query_index)
    }
    if (working === PIPELINES_ROUTE || working === PIPELINES_ROUTE + "/") {
        const rtnval = "list"
        return rtnval
    }
    const detail_id = pipeline_id_from_path(working)
    if (detail_id.length > 0) {
        const rtnval = "detail"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Mount the route-appropriate pipelines view into the shell's
 * ``<main>`` region. ``/pipelines`` (exact) mounts
 * ``<pyc-pipelines-list>``; ``/pipelines/{pipeline_id}`` mounts
 * ``<pyc-pipeline-detail>``.
 *
 * A no-op when the path is not a pipelines route or the main
 * region is not yet in the document. Idempotent -- when the
 * correct view is already mounted nothing is replaced.
 */
export function mount_pipelines_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_pipelines_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main")
    if (main === null) {
        return
    }
    const target_tag = route === "detail" ? PIPELINE_DETAIL_TAG : PIPELINES_LIST_TAG
    const existing = main.querySelector(target_tag)
    if (existing !== null) {
        return
    }
    define_pipelines_elements()
    ensure_pipelines_stylesheet()
    const view = document.createElement(target_tag)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * pipelines sidebar, then mounts the view. When the shell handle
 * is not yet on the window it queues a single microtask retry.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    register_pipelines_sidebar(handle.sidebar)
    mount_pipelines_view_if_active()
    return
}

function _boot(): void {
    define_pipelines_elements()

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
            "pychestrate.ui.pipelines.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycPipelinesList } from "./pipelines-list-view.js"
export type {
    PipelineDefinition,
    PipelineDefinitionPage,
    PipelineStage,
    PipelineStep,
    ProjectOption,
    PageMeta,
    ValidateOutcome,
    UpsertOutcome,
    ExpansionShard,
    MatrixExpandOutcome,
    PipelinesListState,
} from "./pipelines-list-view.js"
export {
    build_pipelines_query_url,
    build_pipelines_collection_url,
    build_pipelines_validate_url,
    build_pipelines_expand_matrix_url,
    short_id,
    format_timestamp,
    has_next_page,
    has_previous_page,
    parse_matrix_spec,
    validate_message_for_status,
} from "./pipelines-list-view.js"
export {
    PycPipelineDetail,
    pipeline_id_from_path,
    pipeline_detail_url,
    compute_dag_columns,
    compute_dag_layout,
} from "./pipeline-detail-view.js"
export type {
    DagColumnAssignment,
    DagColumns,
    DagNode,
    DagEdge,
    DagLayout,
    PipelineDetailState,
} from "./pipeline-detail-view.js"

if (typeof window !== "undefined") {
    _boot()
}
