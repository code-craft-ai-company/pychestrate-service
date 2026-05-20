/**
 * pyc-ops-bundle -- operations UI sidebar registration + view
 * mount.
 *
 * This bundle covers the operator-facing surfaces that landed as
 * REST endpoints without a shell UI: inbound / outbound webhooks
 * and release channels. It does two things on load:
 *
 * 1. Registers the "Webhooks" and "Release Channels" sidebar
 *    entries under a new "Operations" group. The webhooks entry is
 *    gated on the ``system:webhooks.read`` permission key; the
 *    release-channels entry on ``system:release_channels.read`` --
 *    the same keys the corresponding REST endpoints require.
 * 2. Mounts the route-appropriate Custom Element into the shell's
 *    ``<main>`` region. ``/webhooks`` mounts ``<pyc-webhooks>``;
 *    ``/release-channels`` mounts ``<pyc-release-channels>``.
 *
 * The shell document loads this bundle for paths under
 * ``/webhooks`` and ``/release-channels`` (see the server-side
 * ``bundle_registry.py`` mapping), so the registration runs at
 * most once per shell-served operations page.
 *
 * Per ``9-site-shell`` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it.
 */

import { PycWebhooks } from "./webhooks-view.js"
import { PycReleaseChannels } from "./release-channels-view.js"

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
 * Group id for the Operations sidebar group this bundle
 * introduces.
 */
const OPERATIONS_GROUP_ID: string = "operations"

/**
 * Permission key the webhooks REST endpoints require.
 */
const WEBHOOKS_READ_PERMISSION: string = "system:webhooks.read"

/**
 * Permission key the release-channels REST endpoints require.
 */
const RELEASE_CHANNELS_READ_PERMISSION: string =
    "system:release_channels.read"

/**
 * Route prefix the webhooks view owns.
 */
const WEBHOOKS_ROUTE: string = "/webhooks"

/**
 * Route prefix the release-channels view owns.
 */
const RELEASE_CHANNELS_ROUTE: string = "/release-channels"

/**
 * Custom Element tag name for the webhooks view.
 */
const WEBHOOKS_TAG: string = "pyc-webhooks"

/**
 * Custom Element tag name for the release-channels view.
 */
const RELEASE_CHANNELS_TAG: string = "pyc-release-channels"

/**
 * Dist URL of the ops bundle stylesheet (copied by ``build.mjs``).
 */
const OPS_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-ops-bundle.css"

/**
 * Inject the ops bundle stylesheet ``<link>`` into the document
 * head exactly once. The build copies ``ops.css`` to a stable
 * dist URL; the bundle owns loading it because the shell document
 * only references the shell's own stylesheet.
 */
export function ensure_ops_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-ops-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = OPS_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-ops-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The "Webhooks" sidebar entry this bundle contributes.
 */
const WEBHOOKS_ENTRY: SidebarEntryDescriptor = {
    entryId: "operations.webhooks",
    label: "Webhooks",
    route: WEBHOOKS_ROUTE,
    requiredPermissions: [WEBHOOKS_READ_PERMISSION],
    group: OPERATIONS_GROUP_ID,
}

/**
 * The "Release Channels" sidebar entry this bundle contributes.
 */
const RELEASE_CHANNELS_ENTRY: SidebarEntryDescriptor = {
    entryId: "operations.release-channels",
    label: "Release Channels",
    route: RELEASE_CHANNELS_ROUTE,
    requiredPermissions: [RELEASE_CHANNELS_READ_PERMISSION],
    group: OPERATIONS_GROUP_ID,
}

/**
 * Register the Operations sidebar group and the ops entries
 * against the shell. Exported so unit tests can drive registration
 * against a stub registry without going through the global window
 * handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_ops_sidebar(sidebar: SidebarRegistryApi): void {
    sidebar.registerGroup({
        groupId: OPERATIONS_GROUP_ID,
        label: "Operations",
        requiredPermissions: [WEBHOOKS_READ_PERMISSION],
    })
    sidebar.registerEntry(WEBHOOKS_ENTRY)
    sidebar.registerEntry(RELEASE_CHANNELS_ENTRY)
    return
}

/**
 * Define the ops Custom Elements when running in a browser
 * context. Idempotent -- a second call is a no-op for an already-
 * defined tag.
 */
export function define_ops_elements(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(WEBHOOKS_TAG) === undefined) {
        customElements.define(WEBHOOKS_TAG, PycWebhooks)
    }
    if (customElements.get(RELEASE_CHANNELS_TAG) === undefined) {
        customElements.define(RELEASE_CHANNELS_TAG, PycReleaseChannels)
    }
    return
}

/**
 * Classify a shell-served path against the routes this bundle
 * owns. ``/webhooks`` maps to the webhooks view;
 * ``/release-channels`` maps to the release-channels view. Any
 * other path is unowned.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns ``"webhooks"`` | ``"release-channels"`` | ``"none"``.
 */
export function classify_ops_route(path: string): string {
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
        working === WEBHOOKS_ROUTE ||
        working.startsWith(WEBHOOKS_ROUTE + "/") === true
    ) {
        const rtnval = "webhooks"
        return rtnval
    }
    if (
        working === RELEASE_CHANNELS_ROUTE ||
        working.startsWith(RELEASE_CHANNELS_ROUTE + "/") === true
    ) {
        const rtnval = "release-channels"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Resolve the route classification to its Custom Element tag.
 *
 * @param route A route classification from ``classify_ops_route``.
 *
 * @returns The matching tag name, or ``""`` for an unowned route.
 */
export function tag_for_ops_route(route: string): string {
    if (route === "webhooks") {
        const rtnval = WEBHOOKS_TAG
        return rtnval
    }
    if (route === "release-channels") {
        const rtnval = RELEASE_CHANNELS_TAG
        return rtnval
    }
    const rtnval = ""
    return rtnval
}

/**
 * Mount the route-appropriate ops view into the shell's
 * ``<main>`` region. A no-op when the path is not an ops route or
 * the main region is not yet in the document. Idempotent -- when
 * the correct view is already mounted nothing is replaced.
 */
export function mount_ops_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_ops_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const target_tag = tag_for_ops_route(route)
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
    define_ops_elements()
    ensure_ops_stylesheet()
    const view = document.createElement(target_tag)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * ops sidebar, then mounts the view. When the shell handle is not
 * yet on the window it queues a single microtask retry.
 *
 * @param handle The resolved shell registry handle.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    register_ops_sidebar(handle.sidebar)
    mount_ops_view_if_active()
    return
}

function _boot(): void {
    define_ops_elements()

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
            "pychestrate.ui.ops.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycWebhooks } from "./webhooks-view.js"
export type {
    WebhookInIntegration,
    WebhookInDelivery,
    WebhookOutSubscription,
    WebhookOutDelivery,
    WebhookPage,
    WebhookOutcome,
} from "./webhooks-view.js"
export {
    build_integrations_url,
    build_integrations_collection_url,
    build_in_deliveries_url,
    build_subscriptions_url,
    build_subscription_deliveries_url,
    build_subscription_test_url,
    format_webhook_timestamp,
    delivery_outcome_tone,
    create_message_for_status,
    test_message_for_status,
    parse_topic_filters,
} from "./webhooks-view.js"
export { PycReleaseChannels } from "./release-channels-view.js"
export type {
    ReleaseChannelEntry,
    ReleaseChannelPage,
    PublishOutcome,
} from "./release-channels-view.js"
export {
    RELEASE_CHANNEL_VALUES,
    build_release_channel_url,
    format_release_timestamp,
    format_rollout,
    release_status_tone,
    publish_message_for_status,
} from "./release-channels-view.js"

if (typeof window !== "undefined") {
    _boot()
}
