import { format_timestamp } from "../shared/datetime.js";
import { message_with_detail, read_problem_detail } from "../shared/problem-detail.js";
import {
  RESOURCES_WRITE_PERMISSION,
  on_shell_permissions_changed,
  resource_state_tone,
  shell_write_allowed,
} from "./resource-pools-view.js";
/*
 * The project's resources, and a form to register a device (RES-04).
 *
 * Nothing could register a resource, so no pool could have a member and no
 * job could use one. This lists the project's registered resources (state,
 * kind, tags) and, for people who may write resources, registers a device:
 * a name, the hostname that identifies it, and the optional details the
 * `device` kind keeps. The server validates and normalises the attributes; a
 * refused registration shows the server's own reason.
 */
const RESOURCES_API_PATH = "/api/v1/resources";
const LIST_LIMIT = 100;
const DEVICE_KIND = "device";
// The optional details a device keeps, in form order: [attribute, label, hint].
const DEVICE_DETAILS = [
  ["mac_address", "MAC address", "aa:bb:cc:dd:ee:ff"],
  ["ipv4", "IPv4 address", "10.0.0.12"],
  ["vendor", "Vendor", "optional"],
  ["model", "Model", "optional"],
  ["location", "Location", "optional"],
  ["notes", "Notes", "optional"],
];
function build_resources_url(project_id, limit) {
  const params = new URLSearchParams();
  params.set("project_id", project_id);
  params.set("per_page", String(limit));
  return RESOURCES_API_PATH + "?" + params.toString();
}
/* "a, b ,a" -> ["a", "b"]: trimmed, without blanks or repeats. */
function parse_tags(raw) {
  const rtnval = [];
  if (typeof raw !== "string") {
    return rtnval;
  }
  for (const part of raw.split(",")) {
    const trimmed = part.trim();
    if (trimmed.length > 0 && rtnval.indexOf(trimmed) < 0) {
      rtnval.push(trimmed);
    }
  }
  return rtnval;
}
/* The request body that registers a device, or the reason it cannot be built. */
function build_device_body(project_id, values) {
  const name = String(values.display_name || "").trim();
  const hostname = String(values.hostname || "").trim();
  if (project_id.length === 0) {
    return { error: "Pick a project before registering a device." };
  }
  if (name.length === 0) {
    return { error: "A name is required." };
  }
  if (hostname.length === 0) {
    return { error: "A hostname is required: it is what tells one device from another." };
  }
  const attributes = { hostname };
  for (const [key] of DEVICE_DETAILS) {
    const value = String(values[key] || "").trim();
    if (value.length > 0) {
      attributes[key] = value;
    }
  }
  const body = { project_id, kind: DEVICE_KIND, display_name: name, attributes };
  const tags = parse_tags(values.tags);
  if (tags.length > 0) {
    body.tags = tags;
  }
  return { body };
}
/* What a refused registration says, in the person's terms. */
function registration_failure_message(status, detail) {
  if (status === 403) {
    return "You do not have permission to register resources.";
  }
  if (status === 409) {
    return "That device is already registered (same hostname and MAC address).";
  }
  return message_with_detail("Not registered", detail, "Not registered (HTTP " + String(status) + ").");
}
class PycResourceInventory extends HTMLElement {
  _project_id = "";
  _resources = [];
  _total = 0;
  _state = "idle";
  _error_status = 0;
  _saving = false;
  _list_region = null;
  _form_region = null;
  _status = null;
  constructor() {
    super();
  }
  /* Diagnostic accessor for tests. */
  get inventoryState() {
    return {
      projectId: this._project_id,
      state: this._state,
      count: this._resources.length,
      total: this._total,
      saving: this._saving,
    };
  }
  connectedCallback() {
    const section = document.createElement("section");
    section.classList.add("pyc-resources__inventory");
    section.setAttribute("data-role", "inventory-section");
    const heading = document.createElement("h2");
    heading.classList.add("pyc-resources__section-heading");
    heading.textContent = "Resources";
    section.appendChild(heading);
    const list_region = document.createElement("div");
    list_region.setAttribute("data-role", "inventory-list");
    section.appendChild(list_region);
    this._list_region = list_region;
    const form_region = document.createElement("div");
    form_region.setAttribute("data-role", "inventory-form-region");
    section.appendChild(form_region);
    this._form_region = form_region;
    this.replaceChildren(section);
    this._render_form();
    on_shell_permissions_changed(() => {
      if (this.isConnected === true) {
        this._render_form();
        this._render_list();
      }
    });
    void this._load();
    return;
  }
  /* The project whose resources are shown; setting it loads them. */
  set projectId(value) {
    const next = typeof value === "string" ? value : "";
    if (next === this._project_id) {
      return;
    }
    this._project_id = next;
    if (this.isConnected === true) {
      void this._load();
    }
  }
  get projectId() {
    return this._project_id;
  }
  async refresh() {
    await this._load();
    return;
  }
  async _load() {
    if (this._list_region === null) {
      return;
    }
    if (this._project_id.length === 0) {
      this._state = "idle";
      this._resources = [];
      this._total = 0;
      this._render_list();
      return;
    }
    this._state = "loading";
    this._render_list();
    try {
      const response = await fetch(build_resources_url(this._project_id, LIST_LIMIT), {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (response.ok === false) {
        this._state = "error";
        this._error_status = response.status;
      } else {
        const body = await response.json();
        this._resources = Array.isArray(body.items) ? body.items : [];
        this._total = body.meta && typeof body.meta.total === "number" ? body.meta.total : this._resources.length;
        this._state = "loaded";
      }
    } catch (reason) {
      console.warn("pychestrate.ui.resources.inventory_fetch_failed", { reason: String(reason) });
      this._state = "error";
      this._error_status = 0;
    }
    this._render_list();
    return;
  }
  _note(text, role, tone) {
    const note = document.createElement("p");
    note.classList.add("pyc-resources__status");
    if (tone === "error") {
      note.classList.add("pyc-resources__status--error");
    }
    note.setAttribute("data-role", role);
    note.setAttribute("role", "status");
    note.textContent = text;
    return note;
  }
  _render_list() {
    const region = this._list_region;
    if (region === null) {
      return;
    }
    if (this._state === "idle") {
      region.replaceChildren(this._note("Pick a project above to list its resources.", "inventory-needs-project"));
      return;
    }
    if (this._state === "loading") {
      region.replaceChildren(this._note("Loading resources…", "inventory-loading"));
      return;
    }
    if (this._state === "error") {
      const text = this._error_status === 403
        ? "You do not have permission to view resources."
        : "Failed to load resources" + (this._error_status > 0 ? " (HTTP " + String(this._error_status) + ")." : ".");
      region.replaceChildren(this._note(text, "inventory-error", "error"));
      return;
    }
    if (this._resources.length === 0) {
      const writable = shell_write_allowed(RESOURCES_WRITE_PERMISSION) !== false;
      region.replaceChildren(this._note(
        writable
          ? "No resources in this project yet. Register a device below, then add it to a pool."
          : "No resources in this project yet.",
        "inventory-empty"
      ));
      return;
    }
    const fragment = document.createDocumentFragment();
    fragment.appendChild(this._build_table());
    if (this._total > this._resources.length) {
      fragment.appendChild(this._note(
        "Showing the first " + String(this._resources.length) + " of " + String(this._total) + " resources.",
        "inventory-truncated"
      ));
    }
    region.replaceChildren(fragment);
    return;
  }
  _build_table() {
    const table = document.createElement("mj-data-table");
    table.classList.add("pyc-resources__table", "pyc-resources__table--inventory");
    table.setAttribute("sortable", "");
    table.rowClass = "pyc-resources__row";
    table.columns = [
      {
        key: "display_name",
        label: "Name",
        width: "16rem",
        render: (resource) => {
          const link = document.createElement("a");
          link.classList.add("pyc-resources__link");
          link.setAttribute("href", "/resource-pools/resources/" + resource.resource_id);
          link.textContent = resource.display_name && resource.display_name.length > 0 ? resource.display_name : resource.resource_id;
          return link;
        },
      },
      { key: "kind", label: "Kind", width: "8rem", render: (resource) => resource.kind },
      {
        key: "state",
        label: "State",
        width: "9rem",
        render: (resource) => {
          const badge = document.createElement("mj-badge");
          badge.classList.add("pyc-resources__badge");
          badge.setAttribute("data-tone", resource_state_tone(resource.state));
          badge.textContent = resource.state;
          return badge;
        },
      },
      {
        key: "tags",
        label: "Tags",
        width: "16rem",
        sortable: false,
        render: (resource) => {
          const tags = Array.isArray(resource.tags) ? resource.tags : [];
          if (tags.length === 0) {
            return "—";
          }
          const fragment = document.createDocumentFragment();
          for (const tag of tags) {
            const chip = document.createElement("mj-chip");
            chip.classList.add("pyc-resources__tag");
            chip.textContent = tag;
            fragment.appendChild(chip);
          }
          return fragment;
        },
      },
      { key: "created_at", label: "Registered", width: "14rem", render: (resource) => format_timestamp(resource.created_at) },
    ];
    table.rows = this._resources;
    return table;
  }
  /* The register form, for people who may write resources (the server still checks). */
  _render_form() {
    const region = this._form_region;
    if (region === null) {
      return;
    }
    if (shell_write_allowed(RESOURCES_WRITE_PERMISSION) === false) {
      region.replaceChildren();
      return;
    }
    const details = document.createElement("details");
    details.classList.add("pyc-resources__register");
    details.setAttribute("data-role", "register-section");
    const summary = document.createElement("summary");
    summary.textContent = "Register a device";
    details.appendChild(summary);
    const form = document.createElement("form");
    form.classList.add("pyc-resources__form");
    form.setAttribute("data-role", "register-form");
    const inputs = {};
    const add_field = (key, label, placeholder) => {
      const wrapper = document.createElement("div");
      wrapper.classList.add("pyc-resources__filter");
      const input = document.createElement("mj-text-field");
      input.setAttribute("label", label);
      input.classList.add("pyc-resources__input");
      input.setAttribute("type", "text");
      input.setAttribute("placeholder", placeholder);
      input.setAttribute("data-role", "register-" + key);
      wrapper.appendChild(input);
      form.appendChild(wrapper);
      inputs[key] = input;
    };
    add_field("display_name", "Name", "Bench phone 1");
    add_field("hostname", "Hostname", "phone-01");
    for (const [key, label, hint] of DEVICE_DETAILS) {
      add_field(key, label, hint);
    }
    add_field("tags", "Tags", "comma-separated, for example android, lab");
    const submit = document.createElement("mj-button");
    submit.classList.add("pyc-resources__button");
    submit.setAttribute("type", "submit");
    submit.setAttribute("data-role", "register-submit");
    submit.textContent = "Register device";
    form.appendChild(submit);
    const status = document.createElement("p");
    status.classList.add("pyc-resources__form-status");
    status.setAttribute("data-role", "register-status");
    status.setAttribute("role", "status");
    status.hidden = true;
    this._status = status;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const values = {};
      for (const key of Object.keys(inputs)) {
        values[key] = inputs[key].value;
      }
      void this._register(values, submit, inputs);
    });
    details.appendChild(form);
    details.appendChild(status);
    region.replaceChildren(details);
    return;
  }
  _show_status(message, errored) {
    if (this._status === null) {
      return;
    }
    this._status.hidden = false;
    this._status.textContent = message;
    this._status.setAttribute("data-tone", errored === true ? "error" : "ok");
    return;
  }
  async _register(values, submit, inputs) {
    if (this._saving === true) {
      return;
    }
    const built = build_device_body(this._project_id, values);
    if (built.error !== undefined) {
      this._show_status(built.error, true);
      return;
    }
    this._saving = true;
    submit.setAttribute("disabled", "");
    let registered = false;
    try {
      const response = await fetch(RESOURCES_API_PATH, {
        method: "POST",
        credentials: "same-origin",
        headers: { Accept: "application/json", "Content-Type": "application/json" },
        body: JSON.stringify(built.body),
      });
      if (response.ok === false) {
        const detail = await read_problem_detail(response);
        this._show_status(registration_failure_message(response.status, detail), true);
      } else {
        registered = true;
      }
    } catch (reason) {
      console.warn("pychestrate.ui.resources.register_failed", { reason: String(reason) });
      this._show_status("Not registered: network error. Try again.", true);
    } finally {
      this._saving = false;
      submit.removeAttribute("disabled");
    }
    if (registered === true) {
      for (const key of Object.keys(inputs)) {
        inputs[key].value = "";
      }
      this._show_status("Registered " + built.body.display_name + ".", false);
      await this._load();
    }
    return;
  }
}
export {
  DEVICE_DETAILS,
  PycResourceInventory,
  build_device_body,
  build_resources_url,
  parse_tags,
  registration_failure_message,
};
