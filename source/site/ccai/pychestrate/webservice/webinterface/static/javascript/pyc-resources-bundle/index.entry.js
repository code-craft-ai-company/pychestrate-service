import {
  PycResourcePools,
  RESOURCE_POOLS_WRITE_PERMISSION,
  RESOURCES_WRITE_PERMISSION,
  build_resource_pools_url,
  extract_projects,
  format_timestamp,
  health_tone,
  parse_capability_tags,
  read_problem,
  resource_state_tone,
  shell_write_allowed,
  short_id,
  total_pages_for
} from "./resource-pools-view.js";
import {
  ACTIVE_RESERVATION_STATES,
  PycPoolDetail,
  build_pool_member_url,
  build_pool_reservations_url,
  build_pool_resources_url,
  build_pool_url,
  build_reservation_url,
  is_active_reservation,
  is_valid_uuid,
  member_display_label,
  pool_id_from_path,
  project_id_from_search,
  reservation_tone,
  reserve_failure_message,
  section_error_message
} from "./pool-detail-view.js";
import {
  PycResourceDetail,
  STATE_ACTIONS,
  build_resource_health_url,
  build_resource_state_url,
  build_resource_url,
  build_resource_usage_url,
  legal_state_actions,
  pool_id_from_search,
  resource_id_from_path,
  usage_event_tone
} from "./resource-detail-view.js";
const RESOURCE_POOLS_ROUTE = "/resource-pools";
const RESOURCE_POOLS_TAG = "pyc-resource-pools";
const POOL_DETAIL_TAG = "pyc-pool-detail";
const RESOURCE_DETAIL_TAG = "pyc-resource-detail";
const RESOURCES_STYLESHEET_HREF = "/static/javascript/pyc-resources-bundle/pyc-resources-bundle.css";
function ensure_resources_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-resources-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = RESOURCES_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-resources-bundle");
  document.head.appendChild(link);
  return;
}
function define_resources_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(RESOURCE_POOLS_TAG) === void 0) {
    customElements.define(RESOURCE_POOLS_TAG, PycResourcePools);
  }
  if (customElements.get(POOL_DETAIL_TAG) === void 0) {
    customElements.define(POOL_DETAIL_TAG, PycPoolDetail);
  }
  if (customElements.get(RESOURCE_DETAIL_TAG) === void 0) {
    customElements.define(RESOURCE_DETAIL_TAG, PycResourceDetail);
  }
  return;
}
function classify_resources_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working !== RESOURCE_POOLS_ROUTE && working.startsWith(RESOURCE_POOLS_ROUTE + "/") === false) {
    const rtnval2 = "none";
    return rtnval2;
  }
  const resource_id = resource_id_from_path(working);
  if (resource_id.length > 0) {
    const rtnval2 = "resource-detail";
    return rtnval2;
  }
  const pool_id = pool_id_from_path(working);
  if (pool_id.length > 0 && pool_id !== "resources") {
    const rtnval2 = "pool-detail";
    return rtnval2;
  }
  // Anything else under the prefix (the bare list route, a
  // trailing slash, or /resource-pools/resources without an id)
  // falls back to the pools list instead of rendering blank.
  const rtnval = "pools-list";
  return rtnval;
}
function tag_for_resources_route(route) {
  if (route === "pools-list") {
    const rtnval2 = RESOURCE_POOLS_TAG;
    return rtnval2;
  }
  if (route === "pool-detail") {
    const rtnval2 = POOL_DETAIL_TAG;
    return rtnval2;
  }
  if (route === "resource-detail") {
    const rtnval2 = RESOURCE_DETAIL_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_resources_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_resources_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_resources_route(route);
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
  define_resources_elements();
  ensure_resources_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_resources_view_if_active();
  return;
}
function _boot() {
  define_resources_elements();
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
      "pychestrate.ui.resources.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
if (typeof window !== "undefined") {
  _boot();
}
export {
  ACTIVE_RESERVATION_STATES,
  PycPoolDetail,
  PycResourceDetail,
  PycResourcePools,
  RESOURCE_POOLS_WRITE_PERMISSION,
  RESOURCES_WRITE_PERMISSION,
  STATE_ACTIONS,
  build_pool_member_url,
  build_pool_reservations_url,
  build_pool_resources_url,
  build_pool_url,
  build_reservation_url,
  build_resource_health_url,
  build_resource_pools_url,
  build_resource_state_url,
  build_resource_url,
  build_resource_usage_url,
  classify_resources_route,
  define_resources_elements,
  ensure_resources_stylesheet,
  extract_projects,
  format_timestamp,
  health_tone,
  is_active_reservation,
  is_valid_uuid,
  legal_state_actions,
  member_display_label,
  mount_resources_view_if_active,
  parse_capability_tags,
  pool_id_from_path,
  pool_id_from_search,
  project_id_from_search,
  read_problem,
  reservation_tone,
  reserve_failure_message,
  resource_id_from_path,
  resource_state_tone,
  section_error_message,
  shell_write_allowed,
  short_id,
  tag_for_resources_route,
  total_pages_for,
  usage_event_tone
};
