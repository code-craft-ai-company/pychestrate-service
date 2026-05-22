/**
 * pyc-resources-bundle -- resource-pools & resources UI sidebar
 * registration + view mount.
 *
 * This bundle does two things on load:
 *
 * 1. Registers a "Resources" sidebar entry under the shared
 *    "Fleet" sidebar group. The entry is gated on the
 *    ``system:resources.read`` permission key.
 * 2. Mounts the route-appropriate Custom Element into the shell's
 *    ``<main>`` region. ``/resource-pools`` (exact) mounts
 *    ``<pyc-resource-pools>``; ``/resource-pools/{pool_id}`` mounts
 *    ``<pyc-pool-detail>``;
 *    ``/resource-pools/resources/{resource_id}`` mounts
 *    ``<pyc-resource-detail>``. The resource-detail route nests
 *    under ``/resource-pools`` because the top-level ``/resources``
 *    prefix is already claimed by the legacy resources blueprint.
 *
 * The shell document loads this bundle for paths under
 * ``/resource-pools`` (see the server-side ``bundle_registry.py``
 * mapping), so the registration runs at most once per shell-served
 * resources page.
 *
 * Per ``9-site-shell`` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it.
 */

import { PycResourcePools } from "./resource-pools-view.js"
import { PycPoolDetail, pool_id_from_path } from "./pool-detail-view.js"
import {
    PycResourceDetail,
    resource_id_from_path,
} from "./resource-detail-view.js"

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
 * Group id for the Fleet sidebar group -- the group the resources
 * entry joins (matching the pods bundle).
 */
const FLEET_GROUP_ID: string = "fleet"

/**
 * Permission key the resource read endpoints require.
 */
const RESOURCES_READ_PERMISSION: string = "system:resources.read"

/**
 * Route prefix the resource-pools bundle owns -- the pools list,
 * the pool detail and the nested resource-detail route all live
 * under this prefix.
 */
const RESOURCE_POOLS_ROUTE: string = "/resource-pools"

/**
 * Custom Element tag name for the resource-pools list view.
 */
const RESOURCE_POOLS_TAG: string = "pyc-resource-pools"

/**
 * Custom Element tag name for the resource-pool detail view.
 */
const POOL_DETAIL_TAG: string = "pyc-pool-detail"

/**
 * Custom Element tag name for the resource detail view.
 */
const RESOURCE_DETAIL_TAG: string = "pyc-resource-detail"

/**
 * Dist URL of the resources bundle stylesheet (copied by
 * ``build.mjs``).
 */
const RESOURCES_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-resources-bundle.css"

/**
 * Inject the resources bundle stylesheet ``<link>`` into the
 * document head exactly once.
 */
export function ensure_resources_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-resources-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = RESOURCES_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-resources-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The "Resources" sidebar entry this bundle contributes.
 */
const RESOURCES_ENTRY: SidebarEntryDescriptor = {
    entryId: "fleet.resources",
    label: "Resources",
    route: RESOURCE_POOLS_ROUTE,
    requiredPermissions: [RESOURCES_READ_PERMISSION],
    group: FLEET_GROUP_ID,
}

/**
 * Register the Fleet sidebar group and the resources entry against
 * the shell. Exported so unit tests can drive registration against
 * a stub registry without going through the global window handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_resources_sidebar(
        sidebar: SidebarRegistryApi,
    ): void {
    sidebar.registerGroup({
        groupId: FLEET_GROUP_ID,
        label: "Fleet",
        requiredPermissions: [RESOURCES_READ_PERMISSION],
    })
    sidebar.registerEntry(RESOURCES_ENTRY)
    return
}

/**
 * Define the resources Custom Elements when running in a browser
 * context. Idempotent -- a second call is a no-op for an
 * already-defined tag.
 */
export function define_resources_elements(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(RESOURCE_POOLS_TAG) === undefined) {
        customElements.define(RESOURCE_POOLS_TAG, PycResourcePools)
    }
    if (customElements.get(POOL_DETAIL_TAG) === undefined) {
        customElements.define(POOL_DETAIL_TAG, PycPoolDetail)
    }
    if (customElements.get(RESOURCE_DETAIL_TAG) === undefined) {
        customElements.define(RESOURCE_DETAIL_TAG, PycResourceDetail)
    }
    return
}

/**
 * Classify a shell-served path against the routes this bundle
 * owns. ``/resource-pools`` (exact) maps to the pools list;
 * ``/resource-pools/resources/{id}`` maps to the resource detail;
 * ``/resource-pools/{id}`` maps to the pool detail. Any other path
 * is unowned.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns ``"pools-list"`` | ``"pool-detail"`` |
 *          ``"resource-detail"`` | ``"none"``.
 */
export function classify_resources_route(path: string): string {
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
        working === RESOURCE_POOLS_ROUTE ||
        working === RESOURCE_POOLS_ROUTE + "/"
    ) {
        const rtnval = "pools-list"
        return rtnval
    }
    const resource_id = resource_id_from_path(working)
    if (resource_id.length > 0) {
        const rtnval = "resource-detail"
        return rtnval
    }
    const pool_id = pool_id_from_path(working)
    if (pool_id.length > 0 && pool_id !== "resources") {
        const rtnval = "pool-detail"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Resolve the route classification to its Custom Element tag.
 *
 * @param route A route classification from
 *              ``classify_resources_route``.
 *
 * @returns The matching tag name, or ``""`` for an unowned route.
 */
export function tag_for_resources_route(route: string): string {
    if (route === "pools-list") {
        const rtnval = RESOURCE_POOLS_TAG
        return rtnval
    }
    if (route === "pool-detail") {
        const rtnval = POOL_DETAIL_TAG
        return rtnval
    }
    if (route === "resource-detail") {
        const rtnval = RESOURCE_DETAIL_TAG
        return rtnval
    }
    const rtnval = ""
    return rtnval
}

/**
 * Mount the route-appropriate resources view into the shell's
 * ``<main>`` region. A no-op when the path is not a resources route
 * or the main region is not yet in the document. Idempotent -- when
 * the correct view is already mounted nothing is replaced.
 */
export function mount_resources_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_resources_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const target_tag = tag_for_resources_route(route)
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
    define_resources_elements()
    ensure_resources_stylesheet()
    const view = document.createElement(target_tag)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * resources sidebar, then mounts the view. When the shell handle is
 * not yet on the window it queues a single microtask retry.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    // Sidebar nav entries are owned by the central navigation
    // manifest the shell fetches on boot (GET /api/v1/me/navigation)
    // -- see p22b. The shell no longer depends on per-bundle
    // sidebar registration, so this bundle only mounts its
    // route-scoped view. register_resources_sidebar is kept exported
    // for back-compat / unit tests but is intentionally not called.
    mount_resources_view_if_active()
    return
}

function _boot(): void {
    define_resources_elements()

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
            "pychestrate.ui.resources.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycResourcePools } from "./resource-pools-view.js"
export type {
    ResourcePool,
    ResourcePoolPage,
    ResourcePoolsListState,
    PageMeta,
} from "./resource-pools-view.js"
export {
    build_resource_pools_url,
    parse_capability_tags,
    short_id,
    format_timestamp,
    has_next_page as pools_has_next_page,
    has_previous_page as pools_has_previous_page,
} from "./resource-pools-view.js"
export { PycPoolDetail } from "./pool-detail-view.js"
export type {
    ResourcePoolMember,
    ResourcePoolMemberPage,
    Reservation,
    ReservationPage,
    PoolDetailState,
} from "./pool-detail-view.js"
export {
    pool_id_from_path,
    project_id_from_search,
    is_valid_uuid,
    is_active_reservation,
    reservation_tone,
    build_pool_url,
    build_pool_resources_url,
    build_pool_reservations_url,
    build_reservation_url,
    ACTIVE_RESERVATION_STATES,
} from "./pool-detail-view.js"
export { PycResourceDetail } from "./resource-detail-view.js"
export type {
    Resource,
    ResourceHealth,
    UsageRecord,
    UsageRecordPage,
    ResourceDetailState,
} from "./resource-detail-view.js"
export {
    resource_id_from_path,
    health_tone,
    resource_state_tone,
    usage_event_tone,
    build_resource_url,
    build_resource_health_url,
    build_resource_usage_url,
} from "./resource-detail-view.js"

if (typeof window !== "undefined") {
    _boot()
}
