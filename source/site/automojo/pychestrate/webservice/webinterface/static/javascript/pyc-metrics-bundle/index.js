import { PycTestMetrics } from "./test-metrics-view.js";
import { PycTimeseriesExplorer } from "./timeseries-view.js";
import {
  PycDashboardsList,
  PycDashboardDetail,
  dashboard_id_from_path
} from "./dashboards-view.js";
import { PycSlos } from "./slos-view.js";
import { PycAlertRules, ALERT_RULES_ROUTE } from "./alert-rules-view.js";
import {
  PycDashboardEditor,
  dashboard_id_from_edit_path
} from "./dashboard-editor-view.js";
const INSIGHTS_GROUP_ID = "insights";
const METRICS_READ_PERMISSION = "system:metrics.read";
const TEST_METRICS_ROUTE = "/test-metrics";
const TIMESERIES_ROUTE = "/timeseries";
const DASHBOARDS_ROUTE = "/dashboards";
const SLOS_ROUTE = "/slos";
const TEST_METRICS_TAG = "pyc-test-metrics";
const TIMESERIES_TAG = "pyc-timeseries-explorer";
const DASHBOARDS_LIST_TAG = "pyc-dashboards-list";
const DASHBOARD_DETAIL_TAG = "pyc-dashboard-detail";
const SLOS_TAG = "pyc-slos";
const SLOS_READ_PERMISSION = "system:slos.read";
const ALERT_RULES_TAG = "pyc-alert-rules";
const ALERT_RULES_READ_PERMISSION = "system:metric_alerts.read";
const DASHBOARD_EDITOR_TAG = "pyc-dashboard-editor";
const METRICS_STYLESHEET_HREF = "/static/javascript/pyc-metrics-bundle/pyc-metrics-bundle.css";
function ensure_metrics_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-metrics-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = METRICS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-metrics-bundle");
  document.head.appendChild(link);
  return;
}
const TEST_METRICS_ENTRY = {
  entryId: "insights.test-metrics",
  label: "Test Metrics",
  route: TEST_METRICS_ROUTE,
  requiredPermissions: [METRICS_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
const TIMESERIES_ENTRY = {
  entryId: "insights.timeseries",
  label: "Timeseries",
  route: TIMESERIES_ROUTE,
  requiredPermissions: [METRICS_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
const DASHBOARDS_ENTRY = {
  entryId: "insights.dashboards",
  label: "Dashboards",
  route: DASHBOARDS_ROUTE,
  requiredPermissions: [METRICS_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
const SLOS_ENTRY = {
  entryId: "insights.slos",
  label: "SLOs",
  route: SLOS_ROUTE,
  requiredPermissions: [SLOS_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
const ALERT_RULES_ENTRY = {
  entryId: "insights.metric-alerts",
  label: "Alert Rules",
  route: ALERT_RULES_ROUTE,
  requiredPermissions: [ALERT_RULES_READ_PERMISSION],
  group: INSIGHTS_GROUP_ID
};
function register_metrics_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: INSIGHTS_GROUP_ID,
    label: "Insights",
    requiredPermissions: [METRICS_READ_PERMISSION]
  });
  sidebar.registerEntry(TEST_METRICS_ENTRY);
  sidebar.registerEntry(TIMESERIES_ENTRY);
  sidebar.registerEntry(DASHBOARDS_ENTRY);
  sidebar.registerEntry(SLOS_ENTRY);
  sidebar.registerEntry(ALERT_RULES_ENTRY);
  return;
}
function define_metrics_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(TEST_METRICS_TAG) === void 0) {
    customElements.define(TEST_METRICS_TAG, PycTestMetrics);
  }
  if (customElements.get(TIMESERIES_TAG) === void 0) {
    customElements.define(TIMESERIES_TAG, PycTimeseriesExplorer);
  }
  if (customElements.get(DASHBOARDS_LIST_TAG) === void 0) {
    customElements.define(DASHBOARDS_LIST_TAG, PycDashboardsList);
  }
  if (customElements.get(DASHBOARD_DETAIL_TAG) === void 0) {
    customElements.define(DASHBOARD_DETAIL_TAG, PycDashboardDetail);
  }
  if (customElements.get(SLOS_TAG) === void 0) {
    customElements.define(SLOS_TAG, PycSlos);
  }
  if (customElements.get(ALERT_RULES_TAG) === void 0) {
    customElements.define(ALERT_RULES_TAG, PycAlertRules);
  }
  if (customElements.get(DASHBOARD_EDITOR_TAG) === void 0) {
    customElements.define(DASHBOARD_EDITOR_TAG, PycDashboardEditor);
  }
  return;
}
function classify_metrics_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === TEST_METRICS_ROUTE || working === TEST_METRICS_ROUTE + "/") {
    const rtnval2 = "test-metrics";
    return rtnval2;
  }
  if (working === TIMESERIES_ROUTE || working === TIMESERIES_ROUTE + "/") {
    const rtnval2 = "timeseries";
    return rtnval2;
  }
  if (working === DASHBOARDS_ROUTE || working === DASHBOARDS_ROUTE + "/") {
    const rtnval2 = "dashboards-list";
    return rtnval2;
  }
  if (working === SLOS_ROUTE || working === SLOS_ROUTE + "/") {
    const rtnval2 = "slos";
    return rtnval2;
  }
  if (working === ALERT_RULES_ROUTE || working === ALERT_RULES_ROUTE + "/") {
    const rtnval2 = "metric-alerts";
    return rtnval2;
  }
  const editor_id = dashboard_id_from_edit_path(working);
  if (editor_id.length > 0) {
    const rtnval2 = "dashboard-editor";
    return rtnval2;
  }
  const detail_id = dashboard_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "dashboard-detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_metrics_route(route) {
  if (route === "test-metrics") {
    const rtnval2 = TEST_METRICS_TAG;
    return rtnval2;
  }
  if (route === "timeseries") {
    const rtnval2 = TIMESERIES_TAG;
    return rtnval2;
  }
  if (route === "dashboards-list") {
    const rtnval2 = DASHBOARDS_LIST_TAG;
    return rtnval2;
  }
  if (route === "dashboard-detail") {
    const rtnval2 = DASHBOARD_DETAIL_TAG;
    return rtnval2;
  }
  if (route === "slos") {
    const rtnval2 = SLOS_TAG;
    return rtnval2;
  }
  if (route === "metric-alerts") {
    const rtnval2 = ALERT_RULES_TAG;
    return rtnval2;
  }
  if (route === "dashboard-editor") {
    const rtnval2 = DASHBOARD_EDITOR_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_metrics_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_metrics_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_metrics_route(route);
  if (target_tag.length === 0) {
    return;
  }
  const main = document.querySelector(
    "pyc-site-shell main.pyc-site-shell__main"
  );
  if (main === null) {
    return;
  }
  const existing = main.querySelector(target_tag);
  if (existing !== null) {
    return;
  }
  define_metrics_elements();
  ensure_metrics_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_metrics_view_if_active();
  return;
}
function _boot() {
  define_metrics_elements();
  const target = window;
  const handle = target.pychestrateShell;
  if (handle !== void 0 && handle.sidebar !== void 0) {
    _register_against(handle);
    return;
  }
  queueMicrotask(() => {
    const retry = target.pychestrateShell;
    if (retry !== void 0 && retry.sidebar !== void 0) {
      _register_against(retry);
      return;
    }
    console.warn(
      "pychestrate.ui.metrics.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
import { PycTestMetrics as PycTestMetrics2 } from "./test-metrics-view.js";
import {
  build_test_metrics_url,
  format_rate,
  format_duration,
  compute_bar_fractions,
  short_metric_id,
  extract_projects
} from "./test-metrics-view.js";
import { PycTimeseriesExplorer as PycTimeseriesExplorer2 } from "./timeseries-view.js";
import {
  TIME_RANGE_PRESETS,
  resolve_range_preset,
  build_timeseries_url,
  build_catalog_url,
  project_points,
  build_line_path,
  build_area_path,
  build_chart_svg,
  extract_catalog
} from "./timeseries-view.js";
import { PycDashboardsList as PycDashboardsList2, PycDashboardDetail as PycDashboardDetail2 } from "./dashboards-view.js";
import {
  DASHBOARDS_ROUTE as DASHBOARDS_ROUTE2,
  build_dashboards_collection_url,
  build_dashboard_detail_url,
  dashboard_id_from_path as dashboard_id_from_path2,
  create_message_for_status,
  tile_metric_name,
  extract_dashboards
} from "./dashboards-view.js";
import { PycSlos as PycSlos2 } from "./slos-view.js";
import {
  build_slos_collection_url,
  build_slo_detail_url,
  format_ratio,
  format_window,
  slo_status_tone,
  slo_status_label,
  slo_create_message_for_status,
  parse_definition_config,
  extract_slo_projects
} from "./slos-view.js";
import { PycAlertRules as PycAlertRules2 } from "./alert-rules-view.js";
import {
  ALERT_RULES_ROUTE as ALERT_RULES_ROUTE2,
  ALERT_RULE_KIND,
  COMPARISON_OPTIONS,
  SEVERITY_OPTIONS,
  build_alert_rules_collection_url,
  alert_create_message_for_status,
  comparison_label,
  describe_alert_condition,
  format_alert_window,
  parse_notification_targets,
  extract_alert_rules
} from "./alert-rules-view.js";
import { PycDashboardEditor as PycDashboardEditor2 } from "./dashboard-editor-view.js";
import {
  TILE_KIND_OPTIONS,
  dashboard_id_from_edit_path as dashboard_id_from_edit_path2,
  is_dashboard_edit_path,
  generate_tile_id,
  build_tile,
  add_tile,
  remove_tile,
  move_tile_up,
  move_tile_down,
  reindex_tiles,
  editor_tile_metric,
  build_save_payload,
  save_message_for_status
} from "./dashboard-editor-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  ALERT_RULES_ROUTE2 as ALERT_RULES_ROUTE,
  ALERT_RULE_KIND,
  COMPARISON_OPTIONS,
  DASHBOARDS_ROUTE2 as DASHBOARDS_ROUTE,
  PycAlertRules2 as PycAlertRules,
  PycDashboardDetail2 as PycDashboardDetail,
  PycDashboardEditor2 as PycDashboardEditor,
  PycDashboardsList2 as PycDashboardsList,
  PycSlos2 as PycSlos,
  PycTestMetrics2 as PycTestMetrics,
  PycTimeseriesExplorer2 as PycTimeseriesExplorer,
  SEVERITY_OPTIONS,
  TILE_KIND_OPTIONS,
  TIME_RANGE_PRESETS,
  add_tile,
  alert_create_message_for_status,
  build_alert_rules_collection_url,
  build_area_path,
  build_catalog_url,
  build_chart_svg,
  build_dashboard_detail_url,
  build_dashboards_collection_url,
  build_line_path,
  build_save_payload,
  build_slo_detail_url,
  build_slos_collection_url,
  build_test_metrics_url,
  build_tile,
  build_timeseries_url,
  classify_metrics_route,
  comparison_label,
  compute_bar_fractions,
  create_message_for_status,
  dashboard_id_from_edit_path2 as dashboard_id_from_edit_path,
  dashboard_id_from_path2 as dashboard_id_from_path,
  define_metrics_elements,
  describe_alert_condition,
  editor_tile_metric,
  ensure_metrics_stylesheet,
  extract_alert_rules,
  extract_catalog,
  extract_dashboards,
  extract_projects,
  extract_slo_projects,
  format_alert_window,
  format_duration,
  format_rate,
  format_ratio,
  format_window,
  generate_tile_id,
  is_dashboard_edit_path,
  mount_metrics_view_if_active,
  move_tile_down,
  move_tile_up,
  parse_definition_config,
  parse_notification_targets,
  project_points,
  register_metrics_sidebar,
  reindex_tiles,
  remove_tile,
  resolve_range_preset,
  save_message_for_status,
  short_metric_id,
  slo_create_message_for_status,
  slo_status_label,
  slo_status_tone,
  tag_for_metrics_route,
  tile_metric_name
};
