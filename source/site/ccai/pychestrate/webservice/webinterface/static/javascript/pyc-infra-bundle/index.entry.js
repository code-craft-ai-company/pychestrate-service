import { PycEnvironments } from "./environments-view.js";
import { PycProvisioningList } from "./provisioning-list-view.js";
import {
  PycProvisioningDetail,
  run_id_from_path
} from "./provisioning-detail-view.js";
import { PycGuards } from "./guards-view.js";
const ORCHESTRATION_GROUP_ID = "orchestration";
const ENVIRONMENTS_READ_PERMISSION = "system:environments.read";
const PROVISIONING_READ_PERMISSION = "system:provisioning.read";
const GUARDS_READ_PERMISSION = "system:guards.read";
const ENVIRONMENTS_ROUTE = "/environments";
const PROVISIONING_ROUTE = "/provisioning-runs";
const GUARDS_ROUTE = "/blast-radius-guards";
const ENVIRONMENTS_TAG = "pyc-environments";
const PROVISIONING_LIST_TAG = "pyc-provisioning-list";
const PROVISIONING_DETAIL_TAG = "pyc-provisioning-detail";
const GUARDS_TAG = "pyc-guards";
const INFRA_STYLESHEET_HREF = "/static/javascript/pyc-infra-bundle/pyc-infra-bundle.css";
function ensure_infra_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-infra-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = INFRA_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-infra-bundle");
  document.head.appendChild(link);
  return;
}
const ENVIRONMENTS_ENTRY = {
  entryId: "orchestration.environments",
  label: "Environments",
  route: ENVIRONMENTS_ROUTE,
  requiredPermissions: [ENVIRONMENTS_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
const PROVISIONING_ENTRY = {
  entryId: "orchestration.provisioning",
  label: "Provisioning",
  route: PROVISIONING_ROUTE,
  requiredPermissions: [PROVISIONING_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
const GUARDS_ENTRY = {
  entryId: "orchestration.guards",
  label: "Blast-Radius Guards",
  route: GUARDS_ROUTE,
  requiredPermissions: [GUARDS_READ_PERMISSION],
  group: ORCHESTRATION_GROUP_ID
};
function register_infra_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: ORCHESTRATION_GROUP_ID,
    label: "Orchestration",
    requiredPermissions: [ENVIRONMENTS_READ_PERMISSION]
  });
  sidebar.registerEntry(ENVIRONMENTS_ENTRY);
  sidebar.registerEntry(PROVISIONING_ENTRY);
  sidebar.registerEntry(GUARDS_ENTRY);
  return;
}
function define_infra_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(ENVIRONMENTS_TAG) === void 0) {
    customElements.define(ENVIRONMENTS_TAG, PycEnvironments);
  }
  if (customElements.get(PROVISIONING_LIST_TAG) === void 0) {
    customElements.define(PROVISIONING_LIST_TAG, PycProvisioningList);
  }
  if (customElements.get(PROVISIONING_DETAIL_TAG) === void 0) {
    customElements.define(PROVISIONING_DETAIL_TAG, PycProvisioningDetail);
  }
  if (customElements.get(GUARDS_TAG) === void 0) {
    customElements.define(GUARDS_TAG, PycGuards);
  }
  return;
}
function classify_infra_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === ENVIRONMENTS_ROUTE || working.startsWith(ENVIRONMENTS_ROUTE + "/") === true) {
    const rtnval2 = "environments";
    return rtnval2;
  }
  if (working === PROVISIONING_ROUTE || working === PROVISIONING_ROUTE + "/") {
    const rtnval2 = "provisioning-list";
    return rtnval2;
  }
  if (working === GUARDS_ROUTE || working.startsWith(GUARDS_ROUTE + "/") === true) {
    const rtnval2 = "guards";
    return rtnval2;
  }
  const detail_id = run_id_from_path(working);
  if (detail_id.length > 0) {
    const rtnval2 = "provisioning-detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_infra_route(route) {
  if (route === "environments") {
    const rtnval2 = ENVIRONMENTS_TAG;
    return rtnval2;
  }
  if (route === "provisioning-list") {
    const rtnval2 = PROVISIONING_LIST_TAG;
    return rtnval2;
  }
  if (route === "provisioning-detail") {
    const rtnval2 = PROVISIONING_DETAIL_TAG;
    return rtnval2;
  }
  if (route === "guards") {
    const rtnval2 = GUARDS_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_infra_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_infra_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_infra_route(route);
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
  define_infra_elements();
  ensure_infra_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_infra_view_if_active();
  return;
}
function _boot() {
  define_infra_elements();
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
      "pychestrate.ui.infra.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
import { PycEnvironments as PycEnvironments2 } from "./environments-view.js";
import {
  build_environments_query_url,
  build_environments_collection_url,
  build_drift_status_url,
  build_drift_check_url,
  short_id,
  format_timestamp,
  environment_state_tone,
  drift_status_tone,
  drift_status_label,
  drift_status_title,
  register_message_for_status,
  drift_check_message_for_status,
  parse_environment_attrs,
  has_next_page,
  has_previous_page,
  list_load_message_for_status,
  announce_session_expired,
  ENVIRONMENT_STATES,
  DRIFT_STATES
} from "./environments-view.js";
import { PycProvisioningList as PycProvisioningList2 } from "./provisioning-list-view.js";
import {
  build_provisioning_query_url,
  build_provisioning_collection_url,
  build_provisioning_detail_link,
  provisioning_state_tone,
  is_terminal_provisioning_state,
  trigger_message_for_status,
  parse_driver_inputs,
  PROVISIONING_STATES,
  TERMINAL_PROVISIONING_STATES,
  PROVISIONING_ACTIONS
} from "./provisioning-list-view.js";
import { PycProvisioningDetail as PycProvisioningDetail2 } from "./provisioning-detail-view.js";
import {
  run_id_from_path as run_id_from_path2,
  project_id_from_search,
  is_valid_run_id,
  build_provisioning_detail_url
} from "./provisioning-detail-view.js";
import { PycGuards as PycGuards2 } from "./guards-view.js";
import {
  build_guards_collection_url,
  build_guard_item_url,
  build_guards_evaluate_url,
  format_guard_timestamp,
  guard_enabled_tone,
  verdict_tone,
  attach_message_for_status,
  toggle_message_for_status,
  parse_actor_roles,
  extract_guard_projects
} from "./guards-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  DRIFT_STATES,
  ENVIRONMENT_STATES,
  PROVISIONING_ACTIONS,
  PROVISIONING_STATES,
  PycEnvironments2 as PycEnvironments,
  PycGuards2 as PycGuards,
  PycProvisioningDetail2 as PycProvisioningDetail,
  PycProvisioningList2 as PycProvisioningList,
  TERMINAL_PROVISIONING_STATES,
  announce_session_expired,
  attach_message_for_status,
  build_drift_check_url,
  build_drift_status_url,
  build_environments_collection_url,
  build_environments_query_url,
  build_guard_item_url,
  build_guards_collection_url,
  build_guards_evaluate_url,
  build_provisioning_collection_url,
  build_provisioning_detail_link,
  build_provisioning_detail_url,
  build_provisioning_query_url,
  classify_infra_route,
  define_infra_elements,
  drift_check_message_for_status,
  drift_status_label,
  drift_status_title,
  drift_status_tone,
  ensure_infra_stylesheet,
  environment_state_tone,
  extract_guard_projects,
  format_guard_timestamp,
  format_timestamp,
  guard_enabled_tone,
  has_next_page,
  has_previous_page,
  is_terminal_provisioning_state,
  is_valid_run_id,
  list_load_message_for_status,
  mount_infra_view_if_active,
  parse_actor_roles,
  parse_driver_inputs,
  parse_environment_attrs,
  project_id_from_search,
  provisioning_state_tone,
  register_infra_sidebar,
  register_message_for_status,
  run_id_from_path2 as run_id_from_path,
  short_id,
  tag_for_infra_route,
  toggle_message_for_status,
  trigger_message_for_status,
  verdict_tone
};
