/**
 * pyc-pods-bundle -- pods & clients (fleet) UI sidebar registration
 * + view mount.
 *
 * This bundle does two things on load:
 *
 * 1. Registers the "Pods" and "Clients" sidebar entries under a
 *    "Fleet" sidebar group. The pods entry is gated on the
 *    ``system:pods.read`` permission key; the clients entry on
 *    ``system:clients.read``.
 * 2. Mounts the route-appropriate Custom Element into the shell's
 *    ``<main>`` region. ``/pods`` (exact) mounts
 *    ``<pyc-pods-list>``; ``/pods/{pod_id}`` mounts
 *    ``<pyc-pod-detail>``; ``/clients`` (exact) mounts
 *    ``<pyc-clients-list>``; ``/clients/{client_id}`` mounts
 *    ``<pyc-client-detail>``.
 *
 * The shell document loads this bundle for paths under ``/pods``
 * and ``/clients`` (see the server-side ``bundle_registry.py``
 * mapping), so the registration runs at most once per shell-served
 * fleet page.
 *
 * Per ``9-site-shell`` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it.
 */

import { PycPodsList } from "./pods-list-view.js"
import { PycPodDetail, pod_id_from_path } from "./pod-detail-view.js"
import { PycClientsList } from "./clients-list-view.js"
import {
    PycClientDetail,
    client_id_from_path,
} from "./client-detail-view.js"

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
 * Group id for the Fleet sidebar group -- the group the pods and
 * clients entries join.
 */
const FLEET_GROUP_ID: string = "fleet"

/**
 * Permission key the pod read endpoints require.
 */
const PODS_READ_PERMISSION: string = "system:pods.read"

/**
 * Permission key the client read endpoints require.
 */
const CLIENTS_READ_PERMISSION: string = "system:clients.read"

/**
 * Route prefix the pods list / detail views own.
 */
const PODS_ROUTE: string = "/pods"

/**
 * Route prefix the clients list / detail views own.
 */
const CLIENTS_ROUTE: string = "/clients"

/**
 * Custom Element tag name for the pods list view.
 */
const PODS_LIST_TAG: string = "pyc-pods-list"

/**
 * Custom Element tag name for the pod detail view.
 */
const POD_DETAIL_TAG: string = "pyc-pod-detail"

/**
 * Custom Element tag name for the clients list view.
 */
const CLIENTS_LIST_TAG: string = "pyc-clients-list"

/**
 * Custom Element tag name for the client detail view.
 */
const CLIENT_DETAIL_TAG: string = "pyc-client-detail"

/**
 * Dist URL of the pods bundle stylesheet (copied by ``build.mjs``).
 */
const PODS_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-pods-bundle.css"

/**
 * Inject the pods bundle stylesheet ``<link>`` into the document
 * head exactly once.
 */
export function ensure_pods_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-pods-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = PODS_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-pods-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The "Pods" sidebar entry this bundle contributes.
 */
const PODS_ENTRY: SidebarEntryDescriptor = {
    entryId: "fleet.pods",
    label: "Pods",
    route: PODS_ROUTE,
    requiredPermissions: [PODS_READ_PERMISSION],
    group: FLEET_GROUP_ID,
}

/**
 * The "Clients" sidebar entry this bundle contributes.
 */
const CLIENTS_ENTRY: SidebarEntryDescriptor = {
    entryId: "fleet.clients",
    label: "Clients",
    route: CLIENTS_ROUTE,
    requiredPermissions: [CLIENTS_READ_PERMISSION],
    group: FLEET_GROUP_ID,
}

/**
 * Register the Fleet sidebar group and the pods / clients entries
 * against the shell. Exported so unit tests can drive registration
 * against a stub registry without going through the global window
 * handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_pods_sidebar(sidebar: SidebarRegistryApi): void {
    sidebar.registerGroup({
        groupId: FLEET_GROUP_ID,
        label: "Fleet",
        requiredPermissions: [PODS_READ_PERMISSION],
    })
    sidebar.registerEntry(PODS_ENTRY)
    sidebar.registerEntry(CLIENTS_ENTRY)
    return
}

/**
 * Define the pods / clients Custom Elements when running in a
 * browser context. Idempotent -- a second call is a no-op for an
 * already-defined tag.
 */
export function define_pods_elements(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(PODS_LIST_TAG) === undefined) {
        customElements.define(PODS_LIST_TAG, PycPodsList)
    }
    if (customElements.get(POD_DETAIL_TAG) === undefined) {
        customElements.define(POD_DETAIL_TAG, PycPodDetail)
    }
    if (customElements.get(CLIENTS_LIST_TAG) === undefined) {
        customElements.define(CLIENTS_LIST_TAG, PycClientsList)
    }
    if (customElements.get(CLIENT_DETAIL_TAG) === undefined) {
        customElements.define(CLIENT_DETAIL_TAG, PycClientDetail)
    }
    return
}

/**
 * Classify a shell-served path against the routes this bundle
 * owns. ``/pods`` (exact) maps to the pods list; ``/pods/{id}``
 * maps to the pod detail; ``/clients`` (exact) maps to the clients
 * list; ``/clients/{id}`` maps to the client detail. Any other
 * path is unowned.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns ``"pods-list"`` | ``"pod-detail"`` | ``"clients-list"``
 *          | ``"client-detail"`` | ``"none"``.
 */
export function classify_pods_route(path: string): string {
    if (typeof path !== "string") {
        const rtnval = "none"
        return rtnval
    }
    let working = path
    const query_index = working.indexOf("?")
    if (query_index >= 0) {
        working = working.slice(0, query_index)
    }
    if (working === PODS_ROUTE || working === PODS_ROUTE + "/") {
        const rtnval = "pods-list"
        return rtnval
    }
    if (working === CLIENTS_ROUTE || working === CLIENTS_ROUTE + "/") {
        const rtnval = "clients-list"
        return rtnval
    }
    const pod_id = pod_id_from_path(working)
    if (pod_id.length > 0) {
        const rtnval = "pod-detail"
        return rtnval
    }
    const client_id = client_id_from_path(working)
    if (client_id.length > 0) {
        const rtnval = "client-detail"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Resolve the route classification to its Custom Element tag.
 *
 * @param route A route classification from ``classify_pods_route``.
 *
 * @returns The matching tag name, or ``""`` for an unowned route.
 */
export function tag_for_pods_route(route: string): string {
    if (route === "pods-list") {
        const rtnval = PODS_LIST_TAG
        return rtnval
    }
    if (route === "pod-detail") {
        const rtnval = POD_DETAIL_TAG
        return rtnval
    }
    if (route === "clients-list") {
        const rtnval = CLIENTS_LIST_TAG
        return rtnval
    }
    if (route === "client-detail") {
        const rtnval = CLIENT_DETAIL_TAG
        return rtnval
    }
    const rtnval = ""
    return rtnval
}

/**
 * Mount the route-appropriate fleet view into the shell's
 * ``<main>`` region. A no-op when the path is not a fleet route or
 * the main region is not yet in the document. Idempotent -- when
 * the correct view is already mounted nothing is replaced.
 */
export function mount_pods_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_pods_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const target_tag = tag_for_pods_route(route)
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
    define_pods_elements()
    ensure_pods_stylesheet()
    const view = document.createElement(target_tag)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * fleet sidebar, then mounts the view. When the shell handle is
 * not yet on the window it queues a single microtask retry.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    register_pods_sidebar(handle.sidebar)
    mount_pods_view_if_active()
    return
}

function _boot(): void {
    define_pods_elements()

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
            "pychestrate.ui.pods.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycPodsList } from "./pods-list-view.js"
export type { PodDefinition, PodsListState } from "./pods-list-view.js"
export {
    build_pod_definitions_url,
    build_pod_definition_url,
    member_count,
    short_id as pod_short_id,
    format_timestamp as pod_format_timestamp,
    has_next_page as pods_has_next_page,
    has_previous_page as pods_has_previous_page,
} from "./pods-list-view.js"
export { PycPodDetail } from "./pod-detail-view.js"
export type {
    PodStateRow,
    PodRegistration,
    PodRegistrationHistoryRow,
    PodStateHistoryRow,
    PollStatus,
    PodDetailState,
} from "./pod-detail-view.js"
export {
    pod_id_from_path,
    project_id_from_search,
    is_valid_pod_id,
    is_transient_pod_state,
    pod_state_tone,
    build_pod_state_url,
    build_pod_state_history_url,
    build_pod_registration_url,
    build_pod_registrations_url,
    POD_STATES,
    TRANSIENT_POD_STATES,
} from "./pod-detail-view.js"
export { PycClientsList } from "./clients-list-view.js"
export type { Client, ClientsListState } from "./clients-list-view.js"
export {
    build_clients_query_url,
    build_client_detail_url,
    capability_tags,
    status_tone,
    liveness_tone,
    short_id as client_short_id,
    format_timestamp as client_format_timestamp,
    has_next_page as clients_has_next_page,
    has_previous_page as clients_has_previous_page,
    CLIENT_STATUSES,
    LIVENESS_STATES,
} from "./clients-list-view.js"
export { PycClientDetail } from "./client-detail-view.js"
export type { ClientDetailState } from "./client-detail-view.js"
export {
    client_id_from_path,
    is_valid_client_id,
} from "./client-detail-view.js"

if (typeof window !== "undefined") {
    _boot()
}
