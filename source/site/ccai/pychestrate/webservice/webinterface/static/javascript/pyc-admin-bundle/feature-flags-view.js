import { confirm_action } from "../shared/confirm.js";
import { hide_unless_may } from "../shared/permissions.js";
import { message_with_detail, read_problem_detail } from "../shared/problem-detail.js";
import { build_empty_state } from "../shared/empty-state.js";
const FLAGS_PATH = "/api/v1/flags";
const FLAG_STATE_ENABLED = "enabled";
const FLAG_STATE_DISABLED = "disabled";
const FLAG_STATE_RETIRED = "retired";
function build_flag_url(flag_key) {
  const rtnval = FLAGS_PATH + "/" + encodeURIComponent(flag_key);
  return rtnval;
}
function flag_state_tone(state) {
  if (typeof state !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = state.toLowerCase();
  if (lowered === FLAG_STATE_ENABLED) {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === FLAG_STATE_DISABLED) {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  if (lowered === FLAG_STATE_RETIRED) {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "warn";
  return rtnval;
}
function next_flag_state(state) {
  if (typeof state === "string" && state.toLowerCase() === FLAG_STATE_ENABLED) {
    const rtnval2 = FLAG_STATE_DISABLED;
    return rtnval2;
  }
  const rtnval = FLAG_STATE_ENABLED;
  return rtnval;
}
/**
 * What to say when a section failed to load.
 *
 * @param status HTTP status (0 when the request never completed).
 * @param subject What was being loaded ("system health").
 * @param required_permission The permission a 403 problem document
 *   named (its ``required_permission`` member), when known.
 */
function load_failure_message(status, subject, required_permission) {
  if (status === 403) {
    if (typeof required_permission === "string" && required_permission.length > 0) {
      const rtnval3 = "You do not have permission to view " + subject + ": it needs the \u201C" + required_permission + "\u201D permission. Ask an administrator for access.";
      return rtnval3;
    }
    const rtnval2 = "You do not have permission to view " + subject + ".";
    return rtnval2;
  }
  if (status === 0) {
    const rtnval2 = "Could not reach the service while loading " + subject + ". Check your connection and try refreshing.";
    return rtnval2;
  }
  const rtnval = "Failed to load " + subject + " (HTTP " + String(status) + "). Try refreshing.";
  return rtnval;
}
/**
 * The ``required_permission`` member of a 403 problem document
 * (``""`` when the body is not one).
 *
 * @param response The fetch response.
 */
async function read_required_permission(response) {
  try {
    const body = await response.json();
    if (body !== null && typeof body === "object" && typeof body.required_permission === "string") {
      const rtnval2 = body.required_permission;
      return rtnval2;
    }
  } catch (reason) {
    // Not a JSON problem document.
  }
  const rtnval = "";
  return rtnval;
}
function toggle_message_for_status(status) {
  if (status === 200) {
    const rtnval2 = "Flag state updated.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "The flag was modified concurrently \u2014 refresh.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The flag-state update was rejected.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to manage flags.";
    return rtnval2;
  }
  const rtnval = "Failed to update flag (HTTP " + String(status) + ").";
  return rtnval;
}
class PycFeatureFlags extends HTMLElement {
  _entries;
  _loading;
  _errored;
  _error_status;
  _filter_text;
  _table_region;
  _status_region;
  constructor() {
    super();
    this._entries = [];
    this._loading = false;
    this._errored = false;
    this._error_status = 0;
    this._filter_text = "";
    this._table_region = null;
    this._status_region = null;
  }
  /**
   * Diagnostic accessor used by unit tests to read the loading
   * flag without scraping the DOM.
   */
  get loading() {
    const rtnval = this._loading;
    return rtnval;
  }
  /**
   * Diagnostic accessor used by unit tests to read the errored
   * flag without scraping the DOM.
   */
  get errored() {
    const rtnval = this._errored;
    return rtnval;
  }
  /**
   * Lifecycle hook -- render the static chrome and kick off the
   * flags fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-admin");
    const header = document.createElement("div");
    header.classList.add("pyc-admin__header");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-admin__heading");
    heading.textContent = "Feature Flags";
    header.appendChild(heading);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-admin__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("variant", "tertiary");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    header.appendChild(refresh_button);
    root.appendChild(header);
    const lede = document.createElement("p");
    lede.classList.add("pyc-admin__lede");
    lede.textContent = "Toggle a flag's state. Retired flags are read-only.";
    root.appendChild(lede);
    const controls = document.createElement("div");
    controls.classList.add("pyc-admin__controls");
    const filter_input = document.createElement("input");
    filter_input.classList.add("pyc-admin__filter");
    filter_input.setAttribute("type", "search");
    filter_input.setAttribute("data-role", "flag-filter");
    filter_input.setAttribute("placeholder", "Filter by flag key…");
    filter_input.setAttribute("aria-label", "Filter feature flags by key");
    filter_input.addEventListener("input", () => {
      this._filter_text = filter_input.value;
      this._render_table();
    });
    controls.appendChild(filter_input);
    root.appendChild(controls);
    const status_region = document.createElement("div");
    status_region.setAttribute("data-role", "status-region");
    root.appendChild(status_region);
    this._status_region = status_region;
    const table_region = document.createElement("div");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the flags list and re-render. Exposed so unit tests
   * can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._errored = false;
    this._error_status = 0;
    this._render_table();
    let entries = null;
    try {
      const response = await fetch(FLAGS_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        this._error_status = response.status;
        throw new Error(
          "flags fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      if (Array.isArray(body) === true) {
        entries = body;
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.flags_fetch_failed",
        { reason: String(reason) }
      );
    }
    if (entries === null) {
      this._loading = false;
      this._errored = true;
      this._render_table();
      return;
    }
    this._entries = entries;
    this._loading = false;
    this._errored = false;
    this._render_table();
    return;
  }
  _render_table() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-admin__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading feature flags\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._errored === true) {
      const error = document.createElement("p");
      error.classList.add(
        "pyc-admin__notice",
        "pyc-admin__notice--error"
      );
      error.setAttribute("data-role", "error-state");
      error.textContent = load_failure_message(
        this._error_status,
        "feature flags"
      );
      region.replaceChildren(error);
      return;
    }
    if (this._entries.length === 0) {
      // Say what a flag is and where one comes from, not just that there is none (ADM-30).
      const empty = build_empty_state({
        class_name: "pyc-admin__notice",
        message: "No feature flags are registered.",
        next_step: "A flag switches an optional behaviour on or off without a release; " +
          "flags are created through the REST API (POST /api/v1/flags) or by an extension, and appear here for you to toggle."
      });
      region.replaceChildren(empty);
      return;
    }
    const filter_text = this._filter_text.trim().toLowerCase();
    let visible = this._entries;
    if (filter_text.length > 0) {
      visible = this._entries.filter((entry) => {
        if (typeof entry.flag_key !== "string") {
          return false;
        }
        return entry.flag_key.toLowerCase().includes(filter_text);
      });
    }
    if (visible.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-admin__notice");
      empty.setAttribute("data-role", "filter-empty-state");
      empty.textContent = "No feature flags match \u201C" + this._filter_text.trim() + "\u201D.";
      region.replaceChildren(empty);
      return;
    }
    const ordered = visible.slice();
    ordered.sort(
      (left, right) => {
        if (left.flag_key < right.flag_key) {
          return -1;
        }
        if (left.flag_key > right.flag_key) {
          return 1;
        }
        return 0;
      }
    );
    const self = this;
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-admin__table");
    table.setAttribute("sortable", "");
    table.setAttribute("resizable", "");
    table.rowClass = "pyc-admin__row";
    table.rowAttrs = (entry) => ({ "data-flag-key": entry.flag_key });
    table.columns = [
      {
        key: "flag_key",
        label: "Flag Key",
        width: "20rem",
        render: (entry) => {
          const key_cell = document.createElement("span");
          key_cell.classList.add("pyc-admin__mono");
          key_cell.textContent = entry.flag_key ?? "\u2014";
          if (typeof entry.flag_key === "string") {
            key_cell.setAttribute("title", entry.flag_key);
          }
          return key_cell;
        }
      },
      {
        key: "flag_kind",
        label: "Kind",
        width: "10rem",
        render: (entry) => entry.flag_kind ?? "\u2014"
      },
      {
        key: "current_version",
        label: "Version",
        width: "8rem",
        render: (entry) => String(entry.current_version)
      },
      {
        key: "state",
        label: "State",
        width: "10rem",
        render: (entry) => {
          const state_badge = document.createElement("mj-chip");
          state_badge.classList.add("pyc-admin__badge");
          state_badge.setAttribute("data-tone", flag_state_tone(entry.state));
          state_badge.textContent = entry.state ?? "\u2014";
          return state_badge;
        }
      },
      {
        key: "actions",
        label: "Actions",
        width: "10rem",
        sortable: false,
        render: (entry) => self._build_toggle(entry)
      }
    ];
    table.rows = ordered;
    region.replaceChildren(table);
    return;
  }
  _build_toggle(entry) {
    const is_retired = typeof entry.state === "string" && entry.state.toLowerCase() === FLAG_STATE_RETIRED;
    const toggle = document.createElement("mj-button");
    toggle.classList.add("pyc-admin__toggle");
    toggle.setAttribute("type", "button");
    toggle.setAttribute("data-role", "toggle");
    const target = next_flag_state(entry.state);
    toggle.textContent = target === FLAG_STATE_ENABLED ? "Enable" : "Disable";
    hide_unless_may(toggle, "system:flags.admin");
    if (is_retired === true) {
      toggle.toggleAttribute("disabled", true);
    }
    toggle.addEventListener("click", () => {
      const question = "Set flag \"" + String(entry.flag_key) + "\" to " + target + "?";
      const proceed = () => {
        toggle.toggleAttribute("disabled", true);
        void this._on_toggle(entry, toggle);
      };
      if (target === FLAG_STATE_ENABLED) {
        proceed();
        return;
      }
      void confirm_action(this, question, "Disable flag").then((confirmed) => {
        if (confirmed === true) {
          proceed();
        }
      });
    });
    return toggle;
  }
  async _on_toggle(entry, toggle) {
    const target = next_flag_state(entry.state);
    const outcome = await this.toggleFlag(entry.flag_key, target);
    toggle.toggleAttribute("disabled", false);
    this._show_status(
      outcome.message,
      outcome.ok === true ? "ok" : "error"
    );
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * PATCH a flag's state. Exposed so unit tests can invoke a
   * toggle without a real click event.
   *
   * @param flag_key The flag to update.
   * @param target_state The desired flag-state value.
   *
   * @returns The toggle outcome.
   */
  async toggleFlag(flag_key, target_state) {
    const payload = { state: target_state };
    let status = 0;
    let detail = "";
    try {
      const response = await fetch(build_flag_url(flag_key), {
        method: "PATCH",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      status = response.status;
      detail = await read_problem_detail(response);
    } catch (reason) {
      console.warn(
        "pychestrate.ui.admin.flag_toggle_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        flagKey: flag_key,
        message: "Failed to reach the feature-flags service."
      };
      return rtnval2;
    }
    const ok = status === 200;
    const rtnval = {
      ok,
      status,
      flagKey: flag_key,
      message: message_with_detail("Feature flag not changed", detail, toggle_message_for_status(status))
    };
    return rtnval;
  }
  _show_status(message, tone) {
    if (this._status_region === null) {
      return;
    }
    const notice = document.createElement("p");
    notice.classList.add("pyc-admin__notice");
    if (tone === "error") {
      notice.classList.add("pyc-admin__notice--error");
    }
    notice.setAttribute("data-role", "toggle-status");
    notice.setAttribute("role", tone === "error" ? "alert" : "status");
    notice.textContent = message;
    this._status_region.replaceChildren(notice);
    return;
  }
}
export {
  FLAGS_PATH,
  FLAG_STATE_DISABLED,
  FLAG_STATE_ENABLED,
  FLAG_STATE_RETIRED,
  PycFeatureFlags,
  build_flag_url,
  flag_state_tone,
  load_failure_message,
  next_flag_state,
  read_required_permission,
  toggle_message_for_status
};
