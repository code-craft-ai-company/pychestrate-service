/**
 * pyc-secrets-bundle -- secrets sidebar registration + view mount.
 *
 * This bundle does two things on load:
 *
 * 1. Registers the "Secrets" sidebar entry (under a "System"
 *    group) against the site shell's sidebar registry. The entry
 *    is gated on the ``system:secrets.read`` permission key -- the
 *    same key the ``GET /api/v1/secrets`` REST endpoint requires.
 * 2. When the shell-served path is ``/secrets`` it mounts the
 *    ``<pyc-secrets>`` Custom Element into the shell's ``<main>``
 *    region. The element renders a scope-aware (Org / Project /
 *    User) table of secret METADATA, a create form, and per-secret
 *    reveal / rotate / delete actions.
 *
 * The shell document loads this bundle only for paths under
 * ``/secrets`` (see the server-side ``bundle_registry.py``
 * mapping), so the registration runs at most once per shell-served
 * secrets page.
 *
 * Per ``9-site-shell`` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it.
 */

import { PycSecrets } from "./secrets-view.js"

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
 * Group id for the system sidebar group.
 */
const SYSTEM_GROUP_ID: string = "system"

/**
 * Permission key the ``GET /api/v1/secrets`` endpoint requires.
 */
const SECRETS_READ_PERMISSION: string = "system:secrets.read"

/**
 * Route the secrets view owns.
 */
const SECRETS_ROUTE: string = "/secrets"

/**
 * Custom Element tag name for the secrets view.
 */
const SECRETS_TAG: string = "pyc-secrets"

/**
 * Dist URL of the secrets bundle stylesheet (copied by
 * ``build.mjs``).
 */
const SECRETS_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-secrets-bundle.css"

/**
 * Inject the secrets bundle stylesheet ``<link>`` into the
 * document head exactly once. The build copies ``secrets.css`` to
 * a stable dist URL; the bundle owns loading it because the shell
 * document only references the shell's own stylesheet.
 */
export function ensure_secrets_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-secrets-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = SECRETS_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-secrets-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The single sidebar entry this bundle contributes.
 */
const SECRETS_ENTRY: SidebarEntryDescriptor = {
    entryId: "system.secrets",
    label: "Secrets",
    route: SECRETS_ROUTE,
    requiredPermissions: [SECRETS_READ_PERMISSION],
    group: SYSTEM_GROUP_ID,
}

/**
 * Register the system sidebar group and the secrets entry against
 * the shell. Exported so unit tests can drive registration against
 * a stub registry without going through the global window handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_secrets_sidebar(sidebar: SidebarRegistryApi): void {
    sidebar.registerGroup({
        groupId: SYSTEM_GROUP_ID,
        label: "System",
        requiredPermissions: [SECRETS_READ_PERMISSION],
    })
    sidebar.registerEntry(SECRETS_ENTRY)
    return
}

/**
 * Define the ``<pyc-secrets>`` Custom Element when running in a
 * browser context. Idempotent -- a second call is a no-op for an
 * already-defined tag.
 */
export function define_secrets_element(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(SECRETS_TAG) === undefined) {
        customElements.define(SECRETS_TAG, PycSecrets)
    }
    return
}

/**
 * Classify a shell-served path against the route this bundle
 * owns. ``/secrets`` (exact) maps to the secrets view; any other
 * path is unowned.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns ``"view"`` | ``"none"``.
 */
export function classify_secrets_route(path: string): string {
    if (typeof path !== "string") {
        const rtnval = "none"
        return rtnval
    }
    let working = path
    const query_index = working.indexOf("?")
    if (query_index >= 0) {
        working = working.slice(0, query_index)
    }
    if (working === SECRETS_ROUTE || working === SECRETS_ROUTE + "/") {
        const rtnval = "view"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Mount the ``<pyc-secrets>`` view into the shell's ``<main>``
 * region when the path is ``/secrets``. The shell leaves
 * ``<main>`` empty whenever at least one sidebar entry is visible,
 * so this bundle owns the main-region content for its own route.
 *
 * A no-op when the path is not the secrets route or the main
 * region is not yet in the document. Idempotent -- when the view
 * is already mounted nothing is replaced.
 */
export function mount_secrets_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_secrets_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const main = document.querySelector("pyc-site-shell main.pyc-site-shell__main")
    if (main === null) {
        return
    }
    const existing = main.querySelector(SECRETS_TAG)
    if (existing !== null) {
        return
    }
    define_secrets_element()
    ensure_secrets_stylesheet()
    const view = document.createElement(SECRETS_TAG)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * secrets sidebar, then mounts the view. When the shell handle is
 * not yet on the window -- which happens when this bundle's
 * ``<script>`` tag is parsed before the shell bundle finishes
 * connecting -- it queues a single microtask retry; the shell
 * publishes the handle synchronously during ``connectedCallback``,
 * so a microtask suffices.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    // Sidebar nav entries are owned by the central navigation
    // manifest the shell fetches on boot (GET /api/v1/me/navigation)
    // -- see p22b. The shell no longer depends on per-bundle
    // sidebar registration, so this bundle only mounts its
    // route-scoped view. register_secrets_sidebar is kept exported
    // for back-compat / unit tests but is intentionally not called.
    mount_secrets_view_if_active()
    return
}

function _boot(): void {
    define_secrets_element()

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
            "pychestrate.ui.secrets.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycSecrets } from "./secrets-view.js"
export type {
    Secret,
    SecretValue,
    SecretsViewState,
} from "./secrets-view.js"
export {
    SECRET_SCOPE_KINDS,
    build_secrets_list_url,
    build_secret_value_url,
    build_secret_resource_url,
    format_timestamp,
    reveal_error_message,
} from "./secrets-view.js"

if (typeof window !== "undefined") {
    _boot()
}
