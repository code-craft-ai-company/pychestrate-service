/**
 * pyc-metrics-bundle -- metrics & dashboards UI sidebar
 * registration + view mount.
 *
 * This bundle does two things on load:
 *
 * 1. Registers the "Test Metrics", "Timeseries" and "Dashboards"
 *    sidebar entries under a new "Insights" group. The entries are
 *    gated on the ``system:metrics.read`` permission key -- the
 *    same key the metrics REST endpoints require.
 * 2. Mounts the route-appropriate Custom Element into the shell's
 *    ``<main>`` region. ``/test-metrics`` mounts
 *    ``<pyc-test-metrics>``; ``/timeseries`` mounts
 *    ``<pyc-timeseries-explorer>``; ``/dashboards`` (exact) mounts
 *    ``<pyc-dashboards-list>``; ``/dashboards/{dashboard_id}``
 *    mounts ``<pyc-dashboard-detail>``.
 *
 * The shell document loads this bundle for paths under
 * ``/test-metrics``, ``/timeseries`` and ``/dashboards`` (see the
 * server-side ``bundle_registry.py`` mapping), so the registration
 * runs at most once per shell-served metrics page.
 *
 * Per ``9-site-shell`` Requirement 2.4: the group's required
 * permission hides the whole group when the caller lacks it.
 */

import { PycTestMetrics } from "./test-metrics-view.js"
import { PycTimeseriesExplorer } from "./timeseries-view.js"
import {
    PycDashboardsList,
    PycDashboardDetail,
    dashboard_id_from_path,
} from "./dashboards-view.js"
import { PycSlos } from "./slos-view.js"

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
 * Group id for the Insights sidebar group this bundle introduces.
 */
const INSIGHTS_GROUP_ID: string = "insights"

/**
 * Permission key the metrics / dashboards REST endpoints require.
 */
const METRICS_READ_PERMISSION: string = "system:metrics.read"

/**
 * Route prefix the test-metrics view owns.
 */
const TEST_METRICS_ROUTE: string = "/test-metrics"

/**
 * Route prefix the timeseries explorer view owns.
 */
const TIMESERIES_ROUTE: string = "/timeseries"

/**
 * Route prefix the dashboards list / detail views own.
 */
const DASHBOARDS_ROUTE: string = "/dashboards"

/**
 * Route prefix the SLO list view owns.
 */
const SLOS_ROUTE: string = "/slos"

/**
 * Custom Element tag name for the test-metrics view.
 */
const TEST_METRICS_TAG: string = "pyc-test-metrics"

/**
 * Custom Element tag name for the timeseries explorer view.
 */
const TIMESERIES_TAG: string = "pyc-timeseries-explorer"

/**
 * Custom Element tag name for the dashboards list view.
 */
const DASHBOARDS_LIST_TAG: string = "pyc-dashboards-list"

/**
 * Custom Element tag name for the dashboard detail view.
 */
const DASHBOARD_DETAIL_TAG: string = "pyc-dashboard-detail"

/**
 * Custom Element tag name for the SLO list view.
 */
const SLOS_TAG: string = "pyc-slos"

/**
 * Permission key the SLO REST endpoints require.
 */
const SLOS_READ_PERMISSION: string = "system:slos.read"

/**
 * Dist URL of the metrics bundle stylesheet (copied by
 * ``build.mjs``).
 */
const METRICS_STYLESHEET_HREF: string =
    "/static/javascript/dist/pyc-metrics-bundle.css"

/**
 * Inject the metrics bundle stylesheet ``<link>`` into the document
 * head exactly once. The build copies ``metrics.css`` to a stable
 * dist URL; the bundle owns loading it because the shell document
 * only references the shell's own stylesheet.
 */
export function ensure_metrics_stylesheet(): void {
    if (typeof document === "undefined") {
        return
    }
    const selector = 'link[data-pyc-bundle="pyc-metrics-bundle"]'
    if (document.head.querySelector(selector) !== null) {
        return
    }
    const link = document.createElement("link")
    link.rel = "stylesheet"
    link.href = METRICS_STYLESHEET_HREF
    link.setAttribute("data-pyc-bundle", "pyc-metrics-bundle")
    document.head.appendChild(link)
    return
}

/**
 * The "Test Metrics" sidebar entry this bundle contributes.
 */
const TEST_METRICS_ENTRY: SidebarEntryDescriptor = {
    entryId: "insights.test-metrics",
    label: "Test Metrics",
    route: TEST_METRICS_ROUTE,
    requiredPermissions: [METRICS_READ_PERMISSION],
    group: INSIGHTS_GROUP_ID,
}

/**
 * The "Timeseries" sidebar entry this bundle contributes.
 */
const TIMESERIES_ENTRY: SidebarEntryDescriptor = {
    entryId: "insights.timeseries",
    label: "Timeseries",
    route: TIMESERIES_ROUTE,
    requiredPermissions: [METRICS_READ_PERMISSION],
    group: INSIGHTS_GROUP_ID,
}

/**
 * The "Dashboards" sidebar entry this bundle contributes.
 */
const DASHBOARDS_ENTRY: SidebarEntryDescriptor = {
    entryId: "insights.dashboards",
    label: "Dashboards",
    route: DASHBOARDS_ROUTE,
    requiredPermissions: [METRICS_READ_PERMISSION],
    group: INSIGHTS_GROUP_ID,
}

/**
 * The "SLOs" sidebar entry this bundle contributes. Gated on the
 * ``system:slos.read`` permission -- the key the SLO REST
 * endpoints require.
 */
const SLOS_ENTRY: SidebarEntryDescriptor = {
    entryId: "insights.slos",
    label: "SLOs",
    route: SLOS_ROUTE,
    requiredPermissions: [SLOS_READ_PERMISSION],
    group: INSIGHTS_GROUP_ID,
}

/**
 * Register the Insights sidebar group and the metrics entries
 * against the shell. Exported so unit tests can drive registration
 * against a stub registry without going through the global window
 * handle.
 *
 * @param sidebar Sidebar-registry API exposed by ``<pyc-site-shell>``.
 */
export function register_metrics_sidebar(
    sidebar: SidebarRegistryApi,
): void {
    sidebar.registerGroup({
        groupId: INSIGHTS_GROUP_ID,
        label: "Insights",
        requiredPermissions: [METRICS_READ_PERMISSION],
    })
    sidebar.registerEntry(TEST_METRICS_ENTRY)
    sidebar.registerEntry(TIMESERIES_ENTRY)
    sidebar.registerEntry(DASHBOARDS_ENTRY)
    sidebar.registerEntry(SLOS_ENTRY)
    return
}

/**
 * Define the metrics Custom Elements when running in a browser
 * context. Idempotent -- a second call is a no-op for an already-
 * defined tag.
 */
export function define_metrics_elements(): void {
    if (typeof customElements === "undefined") {
        return
    }
    if (customElements.get(TEST_METRICS_TAG) === undefined) {
        customElements.define(TEST_METRICS_TAG, PycTestMetrics)
    }
    if (customElements.get(TIMESERIES_TAG) === undefined) {
        customElements.define(TIMESERIES_TAG, PycTimeseriesExplorer)
    }
    if (customElements.get(DASHBOARDS_LIST_TAG) === undefined) {
        customElements.define(DASHBOARDS_LIST_TAG, PycDashboardsList)
    }
    if (customElements.get(DASHBOARD_DETAIL_TAG) === undefined) {
        customElements.define(DASHBOARD_DETAIL_TAG, PycDashboardDetail)
    }
    if (customElements.get(SLOS_TAG) === undefined) {
        customElements.define(SLOS_TAG, PycSlos)
    }
    return
}

/**
 * Classify a shell-served path against the routes this bundle
 * owns. ``/test-metrics`` maps to the test-metrics view;
 * ``/timeseries`` maps to the timeseries explorer; ``/dashboards``
 * (exact) maps to the dashboards list view;
 * ``/dashboards/{dashboard_id}`` maps to the dashboard detail
 * view. Any other path is unowned.
 *
 * @param path A request path (typically ``window.location.pathname``).
 *
 * @returns ``"test-metrics"`` | ``"timeseries"`` |
 *          ``"dashboards-list"`` | ``"dashboard-detail"`` |
 *          ``"none"``.
 */
export function classify_metrics_route(path: string): string {
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
        working === TEST_METRICS_ROUTE ||
        working === TEST_METRICS_ROUTE + "/"
    ) {
        const rtnval = "test-metrics"
        return rtnval
    }
    if (
        working === TIMESERIES_ROUTE ||
        working === TIMESERIES_ROUTE + "/"
    ) {
        const rtnval = "timeseries"
        return rtnval
    }
    if (
        working === DASHBOARDS_ROUTE ||
        working === DASHBOARDS_ROUTE + "/"
    ) {
        const rtnval = "dashboards-list"
        return rtnval
    }
    if (
        working === SLOS_ROUTE ||
        working === SLOS_ROUTE + "/"
    ) {
        const rtnval = "slos"
        return rtnval
    }
    const detail_id = dashboard_id_from_path(working)
    if (detail_id.length > 0) {
        const rtnval = "dashboard-detail"
        return rtnval
    }
    const rtnval = "none"
    return rtnval
}

/**
 * Resolve the route classification to its Custom Element tag.
 *
 * @param route A route classification from
 *              ``classify_metrics_route``.
 *
 * @returns The matching tag name, or ``""`` for an unowned route.
 */
export function tag_for_metrics_route(route: string): string {
    if (route === "test-metrics") {
        const rtnval = TEST_METRICS_TAG
        return rtnval
    }
    if (route === "timeseries") {
        const rtnval = TIMESERIES_TAG
        return rtnval
    }
    if (route === "dashboards-list") {
        const rtnval = DASHBOARDS_LIST_TAG
        return rtnval
    }
    if (route === "dashboard-detail") {
        const rtnval = DASHBOARD_DETAIL_TAG
        return rtnval
    }
    if (route === "slos") {
        const rtnval = SLOS_TAG
        return rtnval
    }
    const rtnval = ""
    return rtnval
}

/**
 * Mount the route-appropriate metrics view into the shell's
 * ``<main>`` region. A no-op when the path is not a metrics route
 * or the main region is not yet in the document. Idempotent --
 * when the correct view is already mounted nothing is replaced.
 */
export function mount_metrics_view_if_active(): void {
    if (typeof document === "undefined") {
        return
    }
    const route = classify_metrics_route(window.location.pathname)
    if (route === "none") {
        return
    }
    const target_tag = tag_for_metrics_route(route)
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
    define_metrics_elements()
    ensure_metrics_stylesheet()
    const view = document.createElement(target_tag)
    main.replaceChildren(view)
    return
}

/**
 * Bundle-load entry point. Looks up ``window.pychestrateShell``
 * (published by the shell bundle on connect) and registers the
 * metrics sidebar, then mounts the view. When the shell handle is
 * not yet on the window -- which happens when this bundle's
 * ``<script>`` tag is parsed before the shell bundle finishes
 * connecting -- it queues a single microtask retry.
 */
function _register_against(handle: PycSiteShellRegistryHandle): void {
    register_metrics_sidebar(handle.sidebar)
    mount_metrics_view_if_active()
    return
}

function _boot(): void {
    define_metrics_elements()

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
            "pychestrate.ui.metrics.bundle_no_shell_handle",
            {
                reason:
                    "window.pychestrateShell missing after microtask retry",
            },
        )
    })
    return
}

export { PycTestMetrics } from "./test-metrics-view.js"
export type {
    MetricsProjectOption,
    TestMetricsRollup,
    TestMetricsRunEntry,
    TestMetricsSummary,
    TestMetricsState,
} from "./test-metrics-view.js"
export {
    build_test_metrics_url,
    format_rate,
    format_duration,
    compute_bar_fractions,
    short_metric_id,
    extract_projects,
} from "./test-metrics-view.js"
export { PycTimeseriesExplorer } from "./timeseries-view.js"
export type {
    MetricCatalogEntry,
    TimeseriesPoint,
    TimeseriesQuery,
    TimeRangePreset,
    TimeseriesState,
    ChartCoordinate,
} from "./timeseries-view.js"
export {
    TIME_RANGE_PRESETS,
    resolve_range_preset,
    build_timeseries_url,
    build_catalog_url,
    project_points,
    build_line_path,
    build_area_path,
    build_chart_svg,
    extract_catalog,
} from "./timeseries-view.js"
export { PycDashboardsList, PycDashboardDetail } from "./dashboards-view.js"
export type {
    DashboardTile,
    Dashboard,
    DashboardsListState,
    DashboardCreateOutcome,
} from "./dashboards-view.js"
export {
    DASHBOARDS_ROUTE,
    build_dashboards_collection_url,
    build_dashboard_detail_url,
    dashboard_id_from_path,
    create_message_for_status,
    tile_metric_name,
    extract_dashboards,
} from "./dashboards-view.js"
export { PycSlos } from "./slos-view.js"
export type {
    Slo,
    SloStatus,
    SloDetail,
    SloPage,
    SloPageMeta,
    SloProjectOption,
    SloCreateOutcome,
    SloStatusOutcome,
    SlosListState,
} from "./slos-view.js"
export {
    build_slos_collection_url,
    build_slo_detail_url,
    format_ratio,
    format_window,
    slo_status_tone,
    slo_status_label,
    slo_create_message_for_status,
    parse_definition_config,
    extract_slo_projects,
} from "./slos-view.js"

if (typeof window !== "undefined") {
    _boot()
}
