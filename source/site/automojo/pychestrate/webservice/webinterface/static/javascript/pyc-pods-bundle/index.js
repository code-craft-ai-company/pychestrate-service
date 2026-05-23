import { PycPodsList } from "./pods-list-view.js";
import { PycPodDetail, pod_id_from_path } from "./pod-detail-view.js";
import { PycClientsList } from "./clients-list-view.js";
import {
  PycClientDetail,
  client_id_from_path
} from "./client-detail-view.js";
const FLEET_GROUP_ID = "fleet";
const PODS_READ_PERMISSION = "system:pods.read";
const CLIENTS_READ_PERMISSION = "system:clients.read";
const PODS_ROUTE = "/pods";
const CLIENTS_ROUTE = "/clients";
const PODS_LIST_TAG = "pyc-pods-list";
const POD_DETAIL_TAG = "pyc-pod-detail";
const CLIENTS_LIST_TAG = "pyc-clients-list";
const CLIENT_DETAIL_TAG = "pyc-client-detail";
const PODS_STYLESHEET_HREF = "/static/javascript/pyc-pods-bundle/pyc-pods-bundle.css";
function ensure_pods_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-pods-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = PODS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-pods-bundle");
  document.head.appendChild(link);
  return;
}
const PODS_ENTRY = {
  entryId: "fleet.pods",
  label: "Pods",
  route: PODS_ROUTE,
  requiredPermissions: [PODS_READ_PERMISSION],
  group: FLEET_GROUP_ID
};
const CLIENTS_ENTRY = {
  entryId: "fleet.clients",
  label: "Clients",
  route: CLIENTS_ROUTE,
  requiredPermissions: [CLIENTS_READ_PERMISSION],
  group: FLEET_GROUP_ID
};
function register_pods_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: FLEET_GROUP_ID,
    label: "Fleet",
    requiredPermissions: [PODS_READ_PERMISSION]
  });
  sidebar.registerEntry(PODS_ENTRY);
  sidebar.registerEntry(CLIENTS_ENTRY);
  return;
}
function define_pods_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(PODS_LIST_TAG) === void 0) {
    customElements.define(PODS_LIST_TAG, PycPodsList);
  }
  if (customElements.get(POD_DETAIL_TAG) === void 0) {
    customElements.define(POD_DETAIL_TAG, PycPodDetail);
  }
  if (customElements.get(CLIENTS_LIST_TAG) === void 0) {
    customElements.define(CLIENTS_LIST_TAG, PycClientsList);
  }
  if (customElements.get(CLIENT_DETAIL_TAG) === void 0) {
    customElements.define(CLIENT_DETAIL_TAG, PycClientDetail);
  }
  return;
}
function classify_pods_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === PODS_ROUTE || working === PODS_ROUTE + "/") {
    const rtnval2 = "pods-list";
    return rtnval2;
  }
  if (working === CLIENTS_ROUTE || working === CLIENTS_ROUTE + "/") {
    const rtnval2 = "clients-list";
    return rtnval2;
  }
  const pod_id = pod_id_from_path(working);
  if (pod_id.length > 0) {
    const rtnval2 = "pod-detail";
    return rtnval2;
  }
  const client_id = client_id_from_path(working);
  if (client_id.length > 0) {
    const rtnval2 = "client-detail";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_pods_route(route) {
  if (route === "pods-list") {
    const rtnval2 = PODS_LIST_TAG;
    return rtnval2;
  }
  if (route === "pod-detail") {
    const rtnval2 = POD_DETAIL_TAG;
    return rtnval2;
  }
  if (route === "clients-list") {
    const rtnval2 = CLIENTS_LIST_TAG;
    return rtnval2;
  }
  if (route === "client-detail") {
    const rtnval2 = CLIENT_DETAIL_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_pods_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_pods_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_pods_route(route);
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
  define_pods_elements();
  ensure_pods_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_pods_view_if_active();
  return;
}
function _boot() {
  define_pods_elements();
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
      "pychestrate.ui.pods.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
import { PycPodsList as PycPodsList2 } from "./pods-list-view.js";
import {
  build_pod_definitions_url,
  build_pod_definition_url,
  member_count,
  short_id,
  format_timestamp,
  has_next_page,
  has_previous_page
} from "./pods-list-view.js";
import { PycPodDetail as PycPodDetail2 } from "./pod-detail-view.js";
import {
  pod_id_from_path as pod_id_from_path2,
  project_id_from_search,
  is_valid_pod_id,
  is_transient_pod_state,
  pod_state_tone,
  build_pod_state_url,
  build_pod_state_history_url,
  build_pod_registration_url,
  build_pod_registrations_url,
  POD_STATES,
  TRANSIENT_POD_STATES
} from "./pod-detail-view.js";
import { PycClientsList as PycClientsList2 } from "./clients-list-view.js";
import {
  build_clients_query_url,
  build_client_detail_url,
  capability_tags,
  status_tone,
  liveness_tone,
  short_id as short_id2,
  format_timestamp as format_timestamp2,
  has_next_page as has_next_page2,
  has_previous_page as has_previous_page2,
  CLIENT_STATUSES,
  LIVENESS_STATES
} from "./clients-list-view.js";
import { PycClientDetail as PycClientDetail2 } from "./client-detail-view.js";
import {
  client_id_from_path as client_id_from_path2,
  is_valid_client_id
} from "./client-detail-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  CLIENT_STATUSES,
  LIVENESS_STATES,
  POD_STATES,
  PycClientDetail2 as PycClientDetail,
  PycClientsList2 as PycClientsList,
  PycPodDetail2 as PycPodDetail,
  PycPodsList2 as PycPodsList,
  TRANSIENT_POD_STATES,
  build_client_detail_url,
  build_clients_query_url,
  build_pod_definition_url,
  build_pod_definitions_url,
  build_pod_registration_url,
  build_pod_registrations_url,
  build_pod_state_history_url,
  build_pod_state_url,
  capability_tags,
  classify_pods_route,
  format_timestamp2 as client_format_timestamp,
  client_id_from_path2 as client_id_from_path,
  short_id2 as client_short_id,
  has_next_page2 as clients_has_next_page,
  has_previous_page2 as clients_has_previous_page,
  define_pods_elements,
  ensure_pods_stylesheet,
  is_transient_pod_state,
  is_valid_client_id,
  is_valid_pod_id,
  liveness_tone,
  member_count,
  mount_pods_view_if_active,
  format_timestamp as pod_format_timestamp,
  pod_id_from_path2 as pod_id_from_path,
  short_id as pod_short_id,
  pod_state_tone,
  has_next_page as pods_has_next_page,
  has_previous_page as pods_has_previous_page,
  project_id_from_search,
  register_pods_sidebar,
  status_tone,
  tag_for_pods_route
};
