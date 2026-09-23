import { PycWebhooks } from "./webhooks-view.js";
import { PycReleaseChannels } from "./release-channels-view.js";
const OPERATIONS_GROUP_ID = "operations";
const WEBHOOKS_READ_PERMISSION = "system:webhooks.read";
const RELEASE_CHANNELS_READ_PERMISSION = "system:release_channels.read";
const WEBHOOKS_ROUTE = "/webhooks";
const RELEASE_CHANNELS_ROUTE = "/release-channels";
const WEBHOOKS_TAG = "pyc-webhooks";
const RELEASE_CHANNELS_TAG = "pyc-release-channels";
const OPS_STYLESHEET_HREF = "/static/javascript/pyc-ops-bundle/pyc-ops-bundle.css";
function ensure_ops_stylesheet() {
  if (typeof document === "undefined") {
    return;
  }
  const selector = 'link[data-pyc-bundle="pyc-ops-bundle"]';
  if (document.head.querySelector(selector) !== null) {
    return;
  }
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = OPS_STYLESHEET_HREF;
  link.setAttribute("data-pyc-bundle", "pyc-ops-bundle");
  document.head.appendChild(link);
  return;
}
const WEBHOOKS_ENTRY = {
  entryId: "operations.webhooks",
  label: "Webhooks",
  route: WEBHOOKS_ROUTE,
  requiredPermissions: [WEBHOOKS_READ_PERMISSION],
  group: OPERATIONS_GROUP_ID
};
const RELEASE_CHANNELS_ENTRY = {
  entryId: "admin.pychestrate-updates",
  label: "Pychestrate Updates",
  route: RELEASE_CHANNELS_ROUTE,
  requiredPermissions: [RELEASE_CHANNELS_READ_PERMISSION],
  group: "admin"
};
function register_ops_sidebar(sidebar) {
  sidebar.registerGroup({
    groupId: OPERATIONS_GROUP_ID,
    label: "Operations",
    requiredPermissions: [WEBHOOKS_READ_PERMISSION]
  });
  sidebar.registerEntry(WEBHOOKS_ENTRY);
  sidebar.registerEntry(RELEASE_CHANNELS_ENTRY);
  return;
}
function define_ops_elements() {
  if (typeof customElements === "undefined") {
    return;
  }
  if (customElements.get(WEBHOOKS_TAG) === void 0) {
    customElements.define(WEBHOOKS_TAG, PycWebhooks);
  }
  if (customElements.get(RELEASE_CHANNELS_TAG) === void 0) {
    customElements.define(RELEASE_CHANNELS_TAG, PycReleaseChannels);
  }
  return;
}
function classify_ops_route(path) {
  if (typeof path !== "string") {
    const rtnval2 = "none";
    return rtnval2;
  }
  let working = path;
  const query_index = working.indexOf("?");
  if (query_index >= 0) {
    working = working.slice(0, query_index);
  }
  if (working === WEBHOOKS_ROUTE || working.startsWith(WEBHOOKS_ROUTE + "/") === true) {
    const rtnval2 = "webhooks";
    return rtnval2;
  }
  if (working === RELEASE_CHANNELS_ROUTE || working.startsWith(RELEASE_CHANNELS_ROUTE + "/") === true) {
    const rtnval2 = "release-channels";
    return rtnval2;
  }
  const rtnval = "none";
  return rtnval;
}
function tag_for_ops_route(route) {
  if (route === "webhooks") {
    const rtnval2 = WEBHOOKS_TAG;
    return rtnval2;
  }
  if (route === "release-channels") {
    const rtnval2 = RELEASE_CHANNELS_TAG;
    return rtnval2;
  }
  const rtnval = "";
  return rtnval;
}
function mount_ops_view_if_active() {
  if (typeof document === "undefined") {
    return;
  }
  const route = classify_ops_route(window.location.pathname);
  if (route === "none") {
    return;
  }
  const target_tag = tag_for_ops_route(route);
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
  define_ops_elements();
  ensure_ops_stylesheet();
  const view = document.createElement(target_tag);
  main.replaceChildren(view);
  return;
}
function _register_against(handle) {
  mount_ops_view_if_active();
  return;
}
function _boot() {
  define_ops_elements();
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
      "pychestrate.ui.ops.bundle_no_shell_handle",
      {
        reason: "window.pychestrateShell missing after microtask retry"
      }
    );
  });
  return;
}
import { PycWebhooks as PycWebhooks2 } from "./webhooks-view.js";
import {
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
  parse_topic_filters
} from "./webhooks-view.js";
import { PycReleaseChannels as PycReleaseChannels2 } from "./release-channels-view.js";
import {
  RELEASE_CHANNEL_VALUES,
  UPDATES_HEADING,
  build_release_channel_url,
  extract_publishing_status,
  format_release_timestamp,
  format_rollout,
  release_status_tone,
  publish_message_for_status
} from "./release-channels-view.js";
if (typeof window !== "undefined") {
  _boot();
}
export {
  PycReleaseChannels2 as PycReleaseChannels,
  PycWebhooks2 as PycWebhooks,
  RELEASE_CHANNEL_VALUES,
  UPDATES_HEADING,
  extract_publishing_status,
  build_in_deliveries_url,
  build_integrations_collection_url,
  build_integrations_url,
  build_release_channel_url,
  build_subscription_deliveries_url,
  build_subscription_test_url,
  build_subscriptions_url,
  classify_ops_route,
  create_message_for_status,
  define_ops_elements,
  delivery_outcome_tone,
  ensure_ops_stylesheet,
  format_release_timestamp,
  format_rollout,
  format_webhook_timestamp,
  mount_ops_view_if_active,
  parse_topic_filters,
  publish_message_for_status,
  register_ops_sidebar,
  release_status_tone,
  tag_for_ops_route,
  test_message_for_status
};
