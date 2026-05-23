const RELEASE_CHANNELS_PATH = "/api/v1/release-channels";
const RELEASE_CHANNEL_VALUES = [
  "canary",
  "beta",
  "stable"
];
function build_release_channel_url(channel_id) {
  const rtnval = RELEASE_CHANNELS_PATH + "/" + encodeURIComponent(channel_id);
  return rtnval;
}
function format_release_timestamp(value) {
  if (value === null || value === void 0 || value.length === 0) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = value;
    return rtnval2;
  }
  const rtnval = parsed.toLocaleString();
  return rtnval;
}
function format_rollout(value) {
  if (typeof value !== "number" || Number.isNaN(value) === true) {
    const rtnval2 = "\u2014";
    return rtnval2;
  }
  const percent = value * 100;
  const rtnval = String(Math.round(percent)) + "%";
  return rtnval;
}
function release_status_tone(status) {
  if (typeof status !== "string") {
    const rtnval2 = "neutral";
    return rtnval2;
  }
  const lowered = status.toLowerCase();
  if (lowered === "active" || lowered === "published") {
    const rtnval2 = "ok";
    return rtnval2;
  }
  if (lowered === "rolling_out" || lowered === "staged") {
    const rtnval2 = "warn";
    return rtnval2;
  }
  if (lowered === "rolled_back" || lowered === "failed" || lowered === "revoked") {
    const rtnval2 = "error";
    return rtnval2;
  }
  const rtnval = "neutral";
  return rtnval;
}
function publish_message_for_status(status) {
  if (status === 201 || status === 200) {
    const rtnval2 = "Release published to the channel.";
    return rtnval2;
  }
  if (status === 409) {
    const rtnval2 = "That version is already published on the channel.";
    return rtnval2;
  }
  if (status === 422) {
    const rtnval2 = "The publish request was rejected \u2014 check the fields.";
    return rtnval2;
  }
  if (status === 403) {
    const rtnval2 = "You do not have permission to publish releases.";
    return rtnval2;
  }
  const rtnval = "Failed to publish release (HTTP " + String(status) + ").";
  return rtnval;
}
class PycReleaseChannels extends HTMLElement {
  _entries;
  _loading;
  _errored;
  _root;
  _table_region;
  _publish_region;
  _detail_region;
  _toast_region;
  constructor() {
    super();
    this._entries = [];
    this._loading = false;
    this._errored = false;
    this._root = null;
    this._table_region = null;
    this._publish_region = null;
    this._detail_region = null;
    this._toast_region = null;
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
   * channels fetch when the element is inserted.
   */
  connectedCallback() {
    this._render_chrome();
    void this._refresh();
    return;
  }
  /**
   * Build the persistent chrome -- heading, publish + refresh
   * actions, publish-form region, table region, detail region,
   * toast region.
   */
  _render_chrome() {
    const root = document.createElement("section");
    root.classList.add("pyc-ops");
    const heading = document.createElement("h1");
    heading.classList.add("pyc-ops__heading");
    heading.textContent = "Release Channels";
    root.appendChild(heading);
    const controls = document.createElement("div");
    controls.classList.add("pyc-ops__controls");
    const publish_button = document.createElement("mj-button");
    publish_button.classList.add("pyc-ops__button");
    publish_button.setAttribute("type", "button");
    publish_button.setAttribute("data-role", "publish-toggle");
    publish_button.textContent = "Publish Release";
    publish_button.addEventListener("click", () => {
      this._toggle_publish_form();
    });
    controls.appendChild(publish_button);
    const refresh_button = document.createElement("mj-button");
    refresh_button.classList.add("pyc-ops__button");
    refresh_button.setAttribute("type", "button");
    refresh_button.setAttribute("data-role", "refresh");
    refresh_button.textContent = "Refresh";
    refresh_button.addEventListener("click", () => {
      void this._refresh();
    });
    controls.appendChild(refresh_button);
    root.appendChild(controls);
    const publish_region = document.createElement("div");
    publish_region.classList.add("pyc-ops__form-region");
    publish_region.setAttribute("data-role", "publish-region");
    publish_region.hidden = true;
    root.appendChild(publish_region);
    this._publish_region = publish_region;
    const toast_region = document.createElement("div");
    toast_region.classList.add("pyc-ops__toast-region");
    toast_region.setAttribute("data-role", "toast-region");
    root.appendChild(toast_region);
    this._toast_region = toast_region;
    const table_region = document.createElement("div");
    table_region.classList.add("pyc-ops__table-region");
    table_region.setAttribute("data-role", "table-region");
    root.appendChild(table_region);
    this._table_region = table_region;
    const detail_region = document.createElement("div");
    detail_region.classList.add("pyc-ops__table-region");
    detail_region.setAttribute("data-role", "detail-region");
    root.appendChild(detail_region);
    this._detail_region = detail_region;
    this._root = root;
    this.replaceChildren(root);
    return;
  }
  /**
   * Fetch the release-channels list and re-render. Exposed so
   * unit tests can await a fetch cycle.
   */
  async refresh() {
    await this._refresh();
    return;
  }
  async _refresh() {
    this._loading = true;
    this._errored = false;
    this._render_table_region();
    let page = null;
    try {
      const response = await fetch(RELEASE_CHANNELS_PATH, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === false) {
        throw new Error(
          "release-channels fetch failed: HTTP " + String(response.status)
        );
      }
      const body = await response.json();
      page = body;
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.release_channels_fetch_failed",
        { reason: String(reason) }
      );
      this._loading = false;
      this._errored = true;
      this._render_table_region();
      return;
    }
    if (page === null || Array.isArray(page.items) === false) {
      this._loading = false;
      this._errored = true;
      this._render_table_region();
      return;
    }
    this._entries = page.items;
    this._loading = false;
    this._errored = false;
    this._render_table_region();
    return;
  }
  _render_table_region() {
    if (this._table_region === null) {
      return;
    }
    const region = this._table_region;
    if (this._loading === true) {
      const loading = document.createElement("p");
      loading.classList.add("pyc-ops__notice");
      loading.setAttribute("data-role", "loading-state");
      loading.textContent = "Loading release channels\u2026";
      region.replaceChildren(loading);
      return;
    }
    if (this._errored === true) {
      const error = document.createElement("p");
      error.classList.add("pyc-ops__notice", "pyc-ops__notice--error");
      error.setAttribute("data-role", "error-state");
      error.textContent = "Failed to load release channels. Try refreshing.";
      region.replaceChildren(error);
      return;
    }
    if (this._entries.length === 0) {
      const empty = document.createElement("p");
      empty.classList.add("pyc-ops__notice");
      empty.setAttribute("data-role", "empty-state");
      empty.textContent = "No releases published to any channel yet";
      region.replaceChildren(empty);
      return;
    }
    const table = this._build_table();
    region.replaceChildren(table);
    return;
  }
  _build_table() {
    const table = document.createElement("table");
    table.classList.add("pyc-ops__table");
    const thead = document.createElement("thead");
    const head_row = document.createElement("tr");
    const columns = [
      "Component",
      "Channel",
      "Version",
      "Status",
      "Rollout",
      "Issued",
      "Actions"
    ];
    for (const column of columns) {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = column;
      head_row.appendChild(th);
    }
    thead.appendChild(head_row);
    table.appendChild(thead);
    const ordered = this._entries.slice();
    ordered.sort(
      (left, right) => {
        const left_key = left.component + "/" + left.channel;
        const right_key = right.component + "/" + right.channel;
        if (left_key < right_key) {
          return -1;
        }
        if (left_key > right_key) {
          return 1;
        }
        return 0;
      }
    );
    const tbody = document.createElement("tbody");
    for (const entry of ordered) {
      tbody.appendChild(this._build_row(entry));
    }
    table.appendChild(tbody);
    return table;
  }
  _build_row(entry) {
    const row = document.createElement("tr");
    row.setAttribute("data-channel-id", entry.channel_id);
    this._append_text_cell(row, entry.component);
    const channel_cell = document.createElement("td");
    const channel_badge = document.createElement("span");
    channel_badge.classList.add("pyc-ops__badge");
    channel_badge.setAttribute("data-tone", "neutral");
    channel_badge.textContent = entry.channel;
    channel_cell.appendChild(channel_badge);
    row.appendChild(channel_cell);
    this._append_text_cell(row, entry.version);
    const status_cell = document.createElement("td");
    const status_badge = document.createElement("span");
    status_badge.classList.add("pyc-ops__badge");
    status_badge.setAttribute(
      "data-tone",
      release_status_tone(entry.status)
    );
    status_badge.textContent = entry.status;
    status_cell.appendChild(status_badge);
    row.appendChild(status_cell);
    this._append_text_cell(row, format_rollout(entry.rollout_fraction));
    this._append_text_cell(
      row,
      format_release_timestamp(entry.issued_at)
    );
    const actions_cell = document.createElement("td");
    const show_button = document.createElement("mj-button");
    show_button.classList.add("pyc-ops__button", "pyc-ops__row-action");
    show_button.setAttribute("type", "button");
    show_button.setAttribute("data-role", "show-release");
    show_button.textContent = "Show Published Release";
    show_button.addEventListener("click", () => {
      show_button.toggleAttribute("disabled", true);
      void this._on_show_release(entry, show_button);
    });
    actions_cell.appendChild(show_button);
    row.appendChild(actions_cell);
    return row;
  }
  async _on_show_release(entry, button) {
    const detail = await this.loadReleaseChannel(entry.channel_id);
    button.toggleAttribute("disabled", false);
    this._render_detail(detail);
    return;
  }
  /**
   * Read one release-channel entry's published-release detail.
   * Exposed so unit tests can await the detail fetch.
   *
   * @param channel_id The entry to read.
   *
   * @returns The entry, or ``null`` when the read fails.
   */
  async loadReleaseChannel(channel_id) {
    let entry = null;
    try {
      const url = build_release_channel_url(channel_id);
      const response = await fetch(url, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const parsed = body;
        if (parsed !== null && typeof parsed.channel_id === "string") {
          entry = parsed;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.release_channel_fetch_failed",
        { reason: String(reason) }
      );
    }
    const rtnval = entry;
    return rtnval;
  }
  _render_detail(entry) {
    if (this._detail_region === null) {
      return;
    }
    const region = this._detail_region;
    if (entry === null) {
      const error = document.createElement("p");
      error.classList.add("pyc-ops__notice", "pyc-ops__notice--error");
      error.setAttribute("data-role", "detail-error");
      error.textContent = "Failed to load the published release.";
      region.replaceChildren(error);
      return;
    }
    const heading = document.createElement("h2");
    heading.classList.add("pyc-ops__subheading");
    heading.textContent = "Published Release \u2014 " + entry.component + " " + entry.version;
    const list = document.createElement("dl");
    list.classList.add("pyc-ops__detail-list");
    list.setAttribute("data-role", "release-detail");
    this._append_detail_pair(list, "Channel", entry.channel);
    this._append_detail_pair(list, "Status", entry.status);
    this._append_detail_pair(
      list,
      "Rollout",
      format_rollout(entry.rollout_fraction)
    );
    this._append_detail_pair(list, "Artifact URI", entry.artifact_uri);
    this._append_detail_pair(
      list,
      "Artifact SHA-256",
      entry.artifact_sha256
    );
    this._append_detail_pair(
      list,
      "Issued by",
      entry.issued_by ?? "\u2014"
    );
    this._append_detail_pair(
      list,
      "Issued at",
      format_release_timestamp(entry.issued_at)
    );
    region.replaceChildren(heading, list);
    return;
  }
  _append_detail_pair(list, label, value) {
    const term = document.createElement("dt");
    term.classList.add("pyc-ops__detail-term");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.classList.add("pyc-ops__detail-value");
    detail.textContent = value;
    list.appendChild(term);
    list.appendChild(detail);
    return;
  }
  _toggle_publish_form() {
    if (this._publish_region === null) {
      return;
    }
    const region = this._publish_region;
    if (region.hidden === true) {
      this._render_publish_form();
      region.hidden = false;
    } else {
      region.hidden = true;
    }
    return;
  }
  _render_publish_form() {
    if (this._publish_region === null) {
      return;
    }
    const form = document.createElement("form");
    form.classList.add("pyc-ops__form");
    form.setAttribute("data-role", "publish-form");
    const component_input = this._build_field(
      form,
      "Component",
      "publish-component",
      "agent-runtime"
    );
    const channel_label = document.createElement("label");
    channel_label.classList.add("pyc-ops__field");
    channel_label.textContent = "Channel";
    const channel_select = document.createElement("mj-select");
    channel_select.classList.add("pyc-ops__select");
    channel_select.setAttribute("data-role", "publish-channel");
    for (const channel of RELEASE_CHANNEL_VALUES) {
      const option = document.createElement("mj-option");
      option.setAttribute("value", channel);
      option.textContent = channel;
      channel_select.appendChild(option);
    }
    channel_label.appendChild(channel_select);
    form.appendChild(channel_label);
    const version_input = this._build_field(
      form,
      "Version",
      "publish-version",
      "1.4.0"
    );
    const uri_input = this._build_field(
      form,
      "Artifact URI",
      "publish-uri",
      "oci://registry/x:1.4.0"
    );
    const sha_input = this._build_field(
      form,
      "Artifact SHA-256 (64 hex chars)",
      "publish-sha",
      ""
    );
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-ops__submit");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "publish-submit");
    submit.textContent = "Publish Release";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-ops__form-status");
    status.setAttribute("data-role", "publish-status");
    form.appendChild(status);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      void this._submit_publish(
        component_input,
        channel_select,
        version_input,
        uri_input,
        sha_input,
        submit,
        status
      );
    });
    this._publish_region.replaceChildren(form);
    return;
  }
  async _submit_publish(component_input, channel_select, version_input, uri_input, sha_input, submit, status) {
    const component = component_input.value.trim();
    const channel = channel_select.value;
    const version = version_input.value.trim();
    const artifact_uri = uri_input.value.trim();
    const artifact_sha256 = sha_input.value.trim();
    if (component.length === 0 || version.length === 0 || artifact_uri.length === 0) {
      status.textContent = "Component, version and artifact URI are required.";
      return;
    }
    if (artifact_sha256.length !== 64) {
      status.textContent = "Artifact SHA-256 must be 64 hexadecimal characters.";
      return;
    }
    submit.toggleAttribute("disabled", true);
    status.textContent = "Publishing release\u2026";
    const outcome = await this._do_publish(
      component,
      channel,
      version,
      artifact_uri,
      artifact_sha256
    );
    submit.toggleAttribute("disabled", false);
    status.textContent = "";
    this._show_toast(outcome.message, outcome.ok === true ? "ok" : "error");
    if (outcome.ok === true) {
      await this._refresh();
    }
    return;
  }
  /**
   * POST a release-publish request. Exposed so unit tests can
   * invoke a publish without a real form-submit event.
   *
   * @param component The component being published.
   * @param channel The target channel.
   * @param version The release version string.
   * @param artifact_uri The release artifact URI.
   * @param artifact_sha256 The 64-hex-char artifact digest.
   *
   * @returns The publish outcome.
   */
  async publishRelease(component, channel, version, artifact_uri, artifact_sha256) {
    const rtnval = await this._do_publish(
      component,
      channel,
      version,
      artifact_uri,
      artifact_sha256
    );
    return rtnval;
  }
  async _do_publish(component, channel, version, artifact_uri, artifact_sha256) {
    const payload = {
      component,
      channel,
      version,
      artifact_uri,
      artifact_sha256
    };
    let status = 0;
    let channel_id = "";
    try {
      const response = await fetch(RELEASE_CHANNELS_PATH, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      status = response.status;
      if (response.ok === true) {
        const body = await response.json();
        const entry = body;
        if (entry !== null && typeof entry.channel_id === "string") {
          channel_id = entry.channel_id;
        }
      }
    } catch (reason) {
      console.warn(
        "pychestrate.ui.ops.release_publish_failed",
        { reason: String(reason) }
      );
      const rtnval2 = {
        ok: false,
        status: 0,
        channelId: "",
        message: "Failed to reach the release-channels service."
      };
      return rtnval2;
    }
    const ok = status === 201 || status === 200;
    const rtnval = {
      ok,
      status,
      channelId: channel_id,
      message: publish_message_for_status(status)
    };
    return rtnval;
  }
  /**
   * Append a plain-text ``<td>`` to a table row.
   *
   * @param row The row to append the cell to.
   * @param text The cell text content.
   */
  _append_text_cell(row, text) {
    const cell = document.createElement("td");
    cell.textContent = text;
    row.appendChild(cell);
    return;
  }
  /**
   * Build a labelled text input, append it to the supplied form,
   * and return the input element.
   *
   * @param form The form to append the field to.
   * @param label_text The visible field label.
   * @param role The ``data-role`` value for test selection.
   * @param placeholder The input placeholder text.
   *
   * @returns The created input element.
   */
  _build_field(form, label_text, role, placeholder) {
    const label = document.createElement("label");
    label.classList.add("pyc-ops__field");
    label.textContent = label_text;
    const input = document.createElement("mj-text-field");
    input.classList.add("pyc-ops__input");
    input.setAttribute("type", "text");
    input.setAttribute("data-role", role);
    input.setAttribute("placeholder", placeholder);
    label.appendChild(input);
    form.appendChild(label);
    return input;
  }
  /**
   * Render a dismissible toast in the toast region.
   *
   * @param message The toast message text.
   * @param tone ``"ok"`` | ``"error"`` | ``"neutral"``.
   */
  _show_toast(message, tone) {
    if (this._toast_region === null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-ops__toast");
    toast.setAttribute("data-role", "toast");
    toast.setAttribute("data-tone", tone);
    const text = document.createElement("span");
    text.textContent = message;
    toast.appendChild(text);
    const dismiss = document.createElement("mj-button");
    dismiss.classList.add("pyc-ops__toast-dismiss");
    dismiss.setAttribute("type", "button");
    dismiss.setAttribute("aria-label", "Dismiss");
    dismiss.textContent = "\xD7";
    dismiss.addEventListener("click", () => {
      toast.remove();
    });
    toast.appendChild(dismiss);
    this._toast_region.replaceChildren(toast);
    return;
  }
}
export {
  PycReleaseChannels,
  RELEASE_CHANNEL_VALUES,
  build_release_channel_url,
  format_release_timestamp,
  format_rollout,
  publish_message_for_status,
  release_status_tone
};
