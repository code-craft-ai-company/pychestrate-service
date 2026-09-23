import { PycPodsList } from "./pods-list-view.js";
import {
  announce_session_expired,
  build_pod_definitions_url,
  build_pod_definition_url,
  extract_projects,
  format_clock_time,
  load_projects,
  member_count,
  pods_load_message_for_status,
  project_display_map,
  short_id,
  format_timestamp,
  has_next_page,
  has_previous_page
} from "./pods-list-view.js";
import { PycPodDetail } from "./pod-detail-view.js";
import {
  pod_id_from_path,
  project_id_from_search,
  is_valid_pod_id,
  is_transient_pod_state,
  is_terminal_pod_state,
  pod_state_tone,
  build_pod_state_url,
  build_pod_state_history_url,
  build_pod_transitions_url,
  build_pod_registration_url,
  build_pod_registrations_url,
  detail_load_message_for_status,
  runtime_section_message_for_status,
  transition_message_for_status,
  POD_STATES,
  TERMINAL_POD_STATES,
  TRANSIENT_POD_STATES
} from "./pod-detail-view.js";
import { PycClientsList } from "./clients-list-view.js";
import {
  advertised_capability_tags,
  build_clients_query_url,
  build_client_capabilities_url,
  build_client_detail_url,
  build_client_revoke_url,
  capability_tags,
  clients_load_message_for_status,
  latest_capability_update,
  perform_client_revoke,
  revoke_message_for_status,
  status_tone,
  liveness_tone,
  short_id as client_short_id,
  format_timestamp as client_format_timestamp,
  has_next_page as clients_has_next_page,
  has_previous_page as clients_has_previous_page,
  CLIENT_STATUSES,
  LIVENESS_STATES
} from "./clients-list-view.js";
import { PycClientDetail } from "./client-detail-view.js";
import {
  client_detail_message_for_status,
  client_id_from_path,
  is_valid_client_id
} from "./client-detail-view.js";
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
function _boot() {
  define_pods_elements();
  const target = window;
  const handle = target.pychestrateShell;
  if (handle !== void 0 && handle.sidebar !== void 0) {
    mount_pods_view_if_active();
    return;
  }
  let registered = false;
  const try_register = () => {
    if (registered === true) {
      return true;
    }
    const current = target.pychestrateShell;
    if (current !== void 0 && current.sidebar !== void 0) {
      registered = true;
      mount_pods_view_if_active();
      return true;
    }
    return false;
  };
  queueMicrotask(() => {
    try_register();
  });
  if (typeof window.addEventListener === "function") {
    const on_shell_ready = () => {
      if (try_register() === true) {
        window.removeEventListener(
          "pyc-site-shell-ready",
          on_shell_ready
        );
      }
    };
    window.addEventListener("pyc-site-shell-ready", on_shell_ready);
  }
  return;
}
if (typeof window !== "undefined") {
  _boot();
}
export {
  CLIENT_STATUSES,
  LIVENESS_STATES,
  POD_STATES,
  PycClientDetail,
  PycClientsList,
  PycPodDetail,
  PycPodsList,
  TERMINAL_POD_STATES,
  TRANSIENT_POD_STATES,
  advertised_capability_tags,
  announce_session_expired,
  build_client_capabilities_url,
  build_client_detail_url,
  build_client_revoke_url,
  build_clients_query_url,
  build_pod_definition_url,
  build_pod_definitions_url,
  build_pod_registration_url,
  build_pod_registrations_url,
  build_pod_state_history_url,
  build_pod_state_url,
  build_pod_transitions_url,
  capability_tags,
  classify_pods_route,
  client_detail_message_for_status,
  client_format_timestamp,
  client_id_from_path,
  client_short_id,
  clients_has_next_page,
  clients_has_previous_page,
  clients_load_message_for_status,
  define_pods_elements,
  detail_load_message_for_status,
  ensure_pods_stylesheet,
  extract_projects,
  format_clock_time,
  is_terminal_pod_state,
  is_transient_pod_state,
  is_valid_client_id,
  is_valid_pod_id,
  latest_capability_update,
  liveness_tone,
  load_projects,
  member_count,
  mount_pods_view_if_active,
  perform_client_revoke,
  format_timestamp as pod_format_timestamp,
  pod_id_from_path,
  short_id as pod_short_id,
  pod_state_tone,
  has_next_page as pods_has_next_page,
  has_previous_page as pods_has_previous_page,
  pods_load_message_for_status,
  project_display_map,
  project_id_from_search,
  revoke_message_for_status,
  runtime_section_message_for_status,
  status_tone,
  tag_for_pods_route,
  transition_message_for_status
};
