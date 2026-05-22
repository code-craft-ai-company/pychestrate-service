/**
 * pyc-infra-bundle -- infrastructure / provisioning UI sidebar
 * registration + view mount.
 *
 * This bundle does two things on load:
 *
 * 1. Registers the "Environments" and "Provisioning" sidebar
 *    entries under the shared "Orchestration" group the runs /
 *    catalog / builds bundles use (registering a group is
 *    idempotent on its id). The environments entry is gated on the
 *    ``system:environments.read`` permission key; the provisioning
 *    entry on ``system:provisioning.read`` -- the same keys the
 *    corresponding REST endpoints require.
 * 2. Mounts the route-appropriate Custom Element into the shell's
 *    ``<main>`` region. ``/environments`` mounts
 *    ``<pyc-environments>``; ``/provisioning-runs`` (exact) mounts
 *    ``<pyc-provisioning-list>``; ``/provisioning-runs/{run_id}``
 *    mounts ``<pyc-provisioning-detail>``.
 *
 * The shell document loads this bundle for paths under
 * ``/environments`` and ``/provisioning-runs`` (see the server-
 * side ``bundle_registry.py`` mapping), so the registration runs
 * at most once per shell-served infra page.
 *
 * Per ``9-site-shell`` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it.
 */

import { PycEnvironments } from "./environments-view.js"
import { PycProvisioningList } from "./provisioning-list-view.js"
import {
    PycProvisioningDetail,
    run_id_from_path,
} from "./provisioning-detail-view.js"
import { PycGuards } from "./guards-view.js"

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
 * Group id for the shared orchestration sidebar group. Matches the
 * id the runs / catalog / builds bundles register so the infra
 * entries join the same group rather than spawning a duplicate.
 */
const ORCHESTRATION_GROUP_ID: string = "orchestration"

/**
 * Permission key the ``GET …/environments`` endpoint requires.
 */
const ENVIRONMENTS_READ_PERMISSION: string = "system:environments.read"

/**
 * Permission key the ``GET …/provisioning-runs`` endpoint
 * requires.
 */
const PROVISIONING_READ_PERMISSION: string = "system:provisioning.read"

/**
 * Permission key the blast-radius-guard REST endpoints require.
 */
const GUARDS_READ_PERMISSION: string = "system:guards.read"

/**
 * Route prefix the environments list view owns.
 */
const ENVIRONMENTS_ROUTE: string = "/environments"

/**
 * Route prefix the provisioning list / detail views own.
 */
const PROVISIONING_ROUTE: string = "/provisioning-runs"

/**
 * Route prefix the blast-radius-guards list view owns.
 */
const GUARDS_ROUTE: string = "/blast-radius-guards"

/**
 * Custom Element tag name for the environments list view.
 */
const ENVIRONMENTS_TAG: string = "pyc-environments"

/**
 * Custom Element tag name for the provisioning list view.
 */
const PROVISIONING_LIST_TAG: string = "pyc-provisioning-list"

/**
 * Custom Element tag name for the provisioning detail view.
 */
const PROVISIONING_DETAIL_TAG: string = "pyc-provisioning-detail"

/**
 * Custom Element tag name for the blast-radius-guards list view.
 */
const GUARDS_TAG: string = "pyc-guards"

/**
 * Dist URL of the infra bundle stylesheet (copied by
 * ``build.mjs``).
 */
const INFRA_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-infra-bundle.css"

/**
 * Inject the infra bundle stylesheet ``<link>`` into the document
 * head exactly once. The build copies ``infra.css`` to a stable
 * dist URL; the bundle owns loading it because the shell document
 * only references the shell's own stylesheet.
 */
export function ensure_infra_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-infra-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = INFRA_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-infra-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The "Environments" sidebar entry this bundle contributes.
 */
const ENVIRONMENTS_ENTRY: SidebarEntryDescriptor = {
    entryId: "orchestration.environments",
    label: "Environments",
    route: ENVIRONMENTS_ROUTE,
    requiredPermissions: [ENVIRONMENTS_READ_PERMISSION],
    group: ORCHESTRATION_GROUP_ID,
}

/**
 * The "Provisioning" sidebar entry this bundle contributes.
 */
const PROVISIONING_ENTRY: SidebarEntryDescriptor = {
    entryId: "orchestration.provisioning",
    label: "Provisioning",
    route: PROVISIONING_ROUTE,
    requiredPermissions: [PROVISIONING_READ_PERMISSION],
    group: ORCHESTRATION_GROUP_ID,
}

/**
 * The "Blast-Radius Guards" sidebar entry this bundle contributes.
 * Gated on ``system:guards.read`` -- the key the guard REST
 * endpoints require.
 */
const GUARDS_ENTRY: SidebarEntryDescriptor = {
    entryId: "orchestration.guards",
    label: "Blast-Radius Guards",
    route: GUARDS_ROUTE,
    requiredPermissions: [GUARDS_READ_PERMISSION],
    group: ORCHESTRATION_GROUP_ID,
}

/**
 * Register the orchestration sidebar group and the infra entries
 * against the shell. Exported so unit tests can drive registration
 * against a stub registry without going through the global window
 * handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_infra_sidebar(sidebar: SidebarRegistryApi): void {
    sidebar.registerGroup({
        groupId: ORCHESTRATION_GROUP_ID,
        label: "Orchestration",
        requiredPermissions: [ENVIRONMENTS_READ_PERMISSION],
    })
    sidebar.registerEntry(ENVIRONMENTS_ENTRY)
    sidebar.registerEntry(PROVISIONING_ENTRY)
    sidebar.registerEntry(GUARDS_ENTRY)
    return
}

/**
 * Define the infra Custom Elements when running in a browser
 * context. Idempotent -- a second call is a no-op for an already-
 * defined tag.
 */
export function define_infra_elements(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(ENVIRONMENTS_TAG) === undefined) {
        customElements.define(ENVIRONMENTS_TAG, PycEnvironments)
    }
    if (customElements.get(PROVISIONING_LIST_TAG) === undefined) {
        customElements.define(PROVISIONING_LIST_TAG, PycProvisioningList)
    }
    if (customElements.get(PROVISIONING_DETAIL_TAG) === undefined) {
        customElements.define(PROVISIONING_DETAIL_TAG, PycProvisioningDetail)
    }
    if (customElements.get(GUARDS_TAG) === undefined) {
        customElements.define(GUARDS_TAG, PycGuards)
    }
    return
}

/**
 * Classify a shell-served path against the routes this bundle
 * owns. ``/environments`` maps to the environments view;
 * ``/provisioning-runs`` (exact) maps to the provisioning list
 * view; ``/provisioning-runs/{run_id}`` maps to the provisioning
 * detail view. Any other path is unowned.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns ``"environments"`` | ``"provisioning-list"`` |
 *          ``"provisioning-detail"`` | ``"none"``.
 */
export function classify_infra_route(path: string): string {
    if (typeof path !== "string") {
        const rtnval = "none"
        return rtnval
    }
    let working = path
    const query_index = working.indexOf("?")
    if (query_index >= 0) {
        working = working.slice(0, query_index)
    }
    if (
        working === ENVIRONMENTS_ROUTE ||
        working.startsWith(ENVIRONMENTS_ROUTE + "/") === true
    ) {
        const rtnval = "environments"
        return rtnval
    }
    if (
        working === PROVISIONING_ROUTE ||
        working === PROVISIONING_ROUTE + "/"
    ) {
        const rtnval = "provisioning-list"
        return rtnval
    }
    if (
        working === GUARDS_ROUTE ||
        working === GUARDS_ROUTE + "/"
    ) {
        const rtnval = "guards"
        return rtnval
    }
    const detail_id = run_id_from_path(working)
    if (detail_id.length > 0) {
        const rtnval = "provisioning-detail"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Resolve the route classification to its Custom Element tag.
 *
 * @param route A route classification from ``classify_infra_route``.
 *
 * @returns The matching tag name, or ``""`` for an unowned route.
 */
export function tag_for_infra_route(route: string): string {
    if (route === "environments") {
        const rtnval = ENVIRONMENTS_TAG
        return rtnval
    }
    if (route === "provisioning-list") {
        const rtnval = PROVISIONING_LIST_TAG
        return rtnval
    }
    if (route === "provisioning-detail") {
        const rtnval = PROVISIONING_DETAIL_TAG
        return rtnval
    }
    if (route === "guards") {
        const rtnval = GUARDS_TAG
        return rtnval
    }
    const rtnval = ""
    return rtnval
}

/**
 * Mount the route-appropriate infra view into the shell's
 * ``<main>`` region. A no-op when the path is not an infra route
 * or the main region is not yet in the document. Idempotent --
 * when the correct view is already mounted nothing is replaced.
 */
export function mount_infra_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_infra_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const target_tag = tag_for_infra_route(route)
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
    define_infra_elements()
    ensure_infra_stylesheet()
    const view = document.createElement(target_tag)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * infra sidebar, then mounts the view. When the shell handle is
 * not yet on the window -- which happens when this bundle's
 * ``<script>`` tag is parsed before the shell bundle finishes
 * connecting -- it queues a single microtask retry.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    // Sidebar nav entries are owned by the central navigation
    // manifest the shell fetches on boot (GET /api/v1/me/navigation)
    // -- see p22b. The shell no longer depends on per-bundle
    // sidebar registration, so this bundle only mounts its
    // route-scoped view. register_infra_sidebar is kept exported
    // for back-compat / unit tests but is intentionally not called.
    mount_infra_view_if_active()
    return
}

function _boot(): void {
    define_infra_elements()

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
            "pychestrate.ui.infra.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycEnvironments } from "./environments-view.js"
export type {
    Environment,
    EnvironmentPage,
    DriftReport,
    DriftStatus,
    ProjectOption,
    RegisterOutcome,
    DriftCheckOutcome,
    EnvironmentsListState,
    PageMeta,
} from "./environments-view.js"
export {
    build_environments_query_url,
    build_environments_collection_url,
    build_drift_status_url,
    build_drift_check_url,
    short_id,
    format_timestamp,
    environment_state_tone,
    drift_status_tone,
    drift_status_label,
    register_message_for_status,
    drift_check_message_for_status,
    parse_environment_attrs,
    has_next_page,
    has_previous_page,
    ENVIRONMENT_STATES,
    DRIFT_STATES,
} from "./environments-view.js"
export { PycProvisioningList } from "./provisioning-list-view.js"
export type {
    ProvisioningRun,
    ProvisioningRunPage,
    ProvisioningPlanSummary,
    ProvisioningResourceOp,
    TriggerOutcome,
    ProvisioningListState,
} from "./provisioning-list-view.js"
export {
    build_provisioning_query_url,
    build_provisioning_collection_url,
    build_provisioning_detail_link,
    provisioning_state_tone,
    is_terminal_provisioning_state,
    trigger_message_for_status,
    parse_driver_inputs,
    PROVISIONING_STATES,
    TERMINAL_PROVISIONING_STATES,
    PROVISIONING_ACTIONS,
} from "./provisioning-list-view.js"
export { PycProvisioningDetail } from "./provisioning-detail-view.js"
export type { PollStatus, ProvisioningDetailState } from "./provisioning-detail-view.js"
export {
    run_id_from_path,
    project_id_from_search,
    is_valid_run_id,
    build_provisioning_detail_url,
} from "./provisioning-detail-view.js"
export { PycGuards } from "./guards-view.js"
export type {
    Guard,
    GuardPage,
    GuardPageMeta,
    GuardTraceEntry,
    GuardEvaluation,
    GuardProjectOption,
    GuardAttachOutcome,
    GuardToggleOutcome,
    GuardEvaluateOutcome,
    GuardsListState,
} from "./guards-view.js"
export {
    build_guards_collection_url,
    build_guard_item_url,
    build_guards_evaluate_url,
    format_guard_timestamp,
    guard_enabled_tone,
    verdict_tone,
    attach_message_for_status,
    toggle_message_for_status,
    parse_actor_roles,
    extract_guard_projects,
} from "./guards-view.js"

if (typeof window !== "undefined") {
    _boot()
}
