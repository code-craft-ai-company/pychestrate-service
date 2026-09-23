import {
  attach_sidebar_keyboard,
  initialize_sidebar_roving_tabindex
} from "./sidebar-keyboard.js";

/*
 * Default group icons. The nav manifest does not (yet) ship icon
 * URLs for the top-level major items, so we render label-keyed
 * inline SVGs as a fallback. When the manifest grows an `icon`
 * field the renderer prefers that value and falls back here only
 * when the manifest's icon is null.
 *
 * Inline SVGs are kept simple (24x24, currentColor stroke) so they
 * inherit the sidebar's foreground color through the active /
 * muted state.
 */
const DEFAULT_GROUP_ICON_SVGS = {
  "Projects":
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<path d=\"M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z\" />"
    + "</svg>",
  "Orchestration":
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<polygon points=\"6 4 20 12 6 20 6 4\" />"
    + "</svg>",
  "Insights":
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<path d=\"M4 20V10\" /><path d=\"M10 20V4\" /><path d=\"M16 20v-7\" /><path d=\"M22 20H2\" />"
    + "</svg>",
  "Fleet":
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<rect x=\"3\" y=\"4\" width=\"18\" height=\"5\" rx=\"1\" />"
    + "<rect x=\"3\" y=\"11\" width=\"18\" height=\"5\" rx=\"1\" />"
    + "<rect x=\"3\" y=\"18\" width=\"18\" height=\"3\" rx=\"1\" />"
    + "<circle cx=\"7\" cy=\"6.5\" r=\"0.6\" fill=\"currentColor\" />"
    + "<circle cx=\"7\" cy=\"13.5\" r=\"0.6\" fill=\"currentColor\" />"
    + "</svg>",
  "Operations":
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<path d=\"M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 1 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z\" />"
    + "</svg>",
  "System":
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<circle cx=\"12\" cy=\"12\" r=\"3\" />"
    + "<path d=\"M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.05A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.05A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.05A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.34.6.94 1 1.55 1H21a2 2 0 1 1 0 4h-.05a1.7 1.7 0 0 0-1.55 1z\" />"
    + "</svg>",
  "Admin":
    "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
    + "<path d=\"M12 2 4 5v6c0 5 3.5 9.5 8 11 4.5-1.5 8-6 8-11V5l-8-3z\" />"
    + "</svg>"
};

const CHEVRON_ICON_SVG =
  "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"2\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
  + "<path d=\"M9 6l6 6-6 6\" />"
  + "</svg>";

const FALLBACK_GROUP_ICON_SVG =
  "<svg viewBox=\"0 0 24 24\" fill=\"none\" stroke=\"currentColor\" stroke-width=\"1.6\" stroke-linecap=\"round\" stroke-linejoin=\"round\" aria-hidden=\"true\" focusable=\"false\">"
  + "<circle cx=\"12\" cy=\"12\" r=\"4\" />"
  + "</svg>";

class SidebarRenderer {
  _container;
  _on_entry_clicked;
  _detach_keyboard;
  _detach_keydown;
  _open_button;
  constructor(container, on_entry_clicked = null) {
    this._container = container;
    this._on_entry_clicked = on_entry_clicked;
    this._detach_keyboard = null;
    this._detach_keydown = null;
    this._open_button = null;
  }
  /**
   * Render the supplied visible sidebar into the container.
   *
   * @param registry - The sidebar registry source of truth.
   * @param perms - Current permission set.
   * @param active_path - Path of the active route, used for the
   *                      ``aria-current="page"`` marker. The
   *                      accordion group containing the active
   *                      route is auto-expanded on render.
   */
  render(registry, perms, active_path) {
    const visible_sidebar = registry.visible(perms);
    if (this._detach_keyboard !== null) {
      this._detach_keyboard();
      this._detach_keyboard = null;
    }
    if (this._detach_keydown !== null) {
      this._detach_keydown();
      this._detach_keydown = null;
    }
    this._open_button = null;
    this._container.replaceChildren();
    // <mj-side-nav> already renders the <nav> landmark around this
    // container, so the entry list is a plain group (one Navigation
    // landmark per page, not three).
    // <mj-side-nav> slots this content into its own <ul role="list">,
    // so every top-level child we render must be a list item and the
    // wrappers in between must be transparent to the accessibility tree.
    this._container.setAttribute("role", "presentation");
    const nav = document.createElement("div");
    nav.classList.add("pyc-site-shell__sidebar-nav");
    nav.setAttribute("role", "presentation");
    const resolved_active = this._resolve_active_route(visible_sidebar, active_path);
    active_path = resolved_active;
    for (const entry of visible_sidebar.ungrouped) {
      const entry_element = this._build_entry_element(
        entry.label,
        entry.route,
        active_path
      );
      entry_element.classList.add("pyc-site-shell__sidebar-navitem");
      const item = document.createElement("li");
      item.classList.add("pyc-site-shell__sidebar-item");
      item.appendChild(entry_element);
      nav.appendChild(item);
    }
    let auto_open_button = null;
    for (const bucket of visible_sidebar.groups) {
      const built = this._build_group_element(
        bucket.group,
        bucket.entries,
        active_path
      );
      nav.appendChild(built.wrapper);
      if (built.has_active_entry === true && auto_open_button === null) {
        auto_open_button = built.button;
      }
    }
    this._container.appendChild(nav);
    if (auto_open_button !== null) {
      this._open_group(auto_open_button);
    }
    initialize_sidebar_roving_tabindex(this._container);
    this._detach_keyboard = attach_sidebar_keyboard(this._container);
    this._detach_keydown = this._attach_keydown();
    return;
  }
  /**
   * Build one accordion group: a wrapper holding the major button
   * (icon + label + chevron) and the inline panel of sub-entries.
   * Only one panel may be open at a time; the renderer's
   * ``_toggle_group`` closes the previously open one.
   */
  _build_group_element(group, entries, active_path) {
    const wrapper = document.createElement("li");
    wrapper.classList.add("pyc-site-shell__sidebar-group", "pyc-site-shell__sidebar-item");
    const button = document.createElement("button");
    button.type = "button";
    button.classList.add(
      "pyc-site-shell__sidebar-group-btn",
      "pyc-site-shell__sidebar-navitem"
    );
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("tabindex", "-1");
    const panel_id = "pyc-sidebar-panel-" + String(group.groupId || group.group_id || group.label || "").toLowerCase().replace(/[^a-z0-9]+/g, "-");
    button.setAttribute("aria-controls", panel_id);
    const icon_span = document.createElement("span");
    icon_span.classList.add("pyc-site-shell__sidebar-group-icon");
    icon_span.setAttribute("aria-hidden", "true");
    const resolved_icon_svg = this._resolve_group_icon(group);
    icon_span.innerHTML = resolved_icon_svg;
    const label_span = document.createElement("span");
    label_span.classList.add("pyc-site-shell__sidebar-group-label");
    label_span.textContent = group.label;
    button.appendChild(icon_span);
    button.appendChild(label_span);
    const chevron_span = document.createElement("span");
    chevron_span.classList.add("pyc-site-shell__sidebar-group-chevron");
    chevron_span.setAttribute("aria-hidden", "true");
    chevron_span.innerHTML = CHEVRON_ICON_SVG;
    button.appendChild(chevron_span);
    const panel = document.createElement("div");
    panel.classList.add("pyc-site-shell__sidebar-panel");
    panel.id = panel_id;
    panel.setAttribute("role", "group");
    panel.setAttribute("aria-label", group.label);
    panel.hidden = true;
    const panel_list = document.createElement("ul");
    panel_list.classList.add("pyc-site-shell__sidebar-panel-list");
    let has_active_entry = false;
    for (const entry of entries) {
      const entry_element = this._build_entry_element(
        entry.label,
        entry.route,
        active_path
      );
      if (entry.route === active_path) {
        has_active_entry = true;
      }
      const item = document.createElement("li");
      item.appendChild(entry_element);
      panel_list.appendChild(item);
    }
    panel.appendChild(panel_list);
    if (has_active_entry === true) {
      button.classList.add("pyc-site-shell__sidebar-group-btn--active");
    }
    button.addEventListener("click", (event) => {
      event.preventDefault();
      this._toggle_group(button);
    });
    wrapper.appendChild(button);
    wrapper.appendChild(panel);
    const rtnval = { wrapper, button, has_active_entry };
    return rtnval;
  }
  /**
   * Pick the SVG markup for a group. Honor an explicit
   * ``group.icon`` when the manifest ships one (allowing an inline
   * SVG string or a URL — both are passed through as-is); fall
   * back to the label-keyed defaults; final fallback is a generic
   * mark so even an unknown group renders something rather than
   * leaving a gap.
   */
  _resolve_group_icon(group) {
    if (group !== null && typeof group === "object") {
      const supplied = group.icon;
      if (typeof supplied === "string" && supplied.length > 0) {
        if (supplied.trim().startsWith("<svg")) {
          return supplied;
        }
        for (const key of Object.keys(DEFAULT_GROUP_ICON_SVGS)) {
          if (key.toLowerCase() === supplied.toLowerCase()) {
            return DEFAULT_GROUP_ICON_SVGS[key];
          }
        }
      }
      const label = group.label;
      if (typeof label === "string" && DEFAULT_GROUP_ICON_SVGS[label] !== undefined) {
        return DEFAULT_GROUP_ICON_SVGS[label];
      }
    }
    return FALLBACK_GROUP_ICON_SVG;
  }
  /**
   * Longest-prefix (segment boundary) match of the current path
   * against every visible entry, so /admin/users/u-1 highlights
   * "Users" and /builds/42 highlights "Builds". Falls back to the
   * raw path when nothing matches.
   */
  _resolve_active_route(visible_sidebar, active_path) {
    if (typeof active_path !== "string" || active_path.length === 0) {
      return active_path;
    }
    const entries = [];
    for (const entry of visible_sidebar.ungrouped) {
      entries.push(entry);
    }
    for (const bucket of visible_sidebar.groups) {
      for (const entry of bucket.entries) {
        entries.push(entry);
      }
    }
    let best = null;
    for (const entry of entries) {
      const route = entry.route;
      if (typeof route !== "string" || route.length === 0) {
        continue;
      }
      const prefix = route.endsWith("/") ? route : route + "/";
      if (active_path === route || active_path.startsWith(prefix)) {
        if (best === null || route.length > best.length) {
          best = route;
        }
      }
    }
    return best !== null ? best : active_path;
  }
  /**
   * Toggle a group's accordion. Opening one closes the other open
   * group so the sidebar holds at most one expanded panel at a
   * time.
   */
  _toggle_group(button) {
    const is_open = button.getAttribute("aria-expanded") === "true";
    if (is_open === true) {
      this._close_group();
      return;
    }
    this._open_group(button);
    return;
  }
  /**
   * Open a group's panel, closing any other open group first.
   */
  _open_group(button) {
    if (this._open_button !== null && this._open_button !== button) {
      this._close_group();
    }
    button.setAttribute("aria-expanded", "true");
    const panel = button.nextElementSibling;
    if (panel instanceof HTMLElement) {
      panel.hidden = false;
    }
    this._open_button = button;
    return;
  }
  /**
   * Close whatever group is currently open. No-op when nothing is
   * open. The next sibling of the open button is its panel.
   */
  _close_group() {
    if (this._open_button === null) {
      return;
    }
    const button = this._open_button;
    button.setAttribute("aria-expanded", "false");
    const panel = button.nextElementSibling;
    if (panel instanceof HTMLElement) {
      panel.hidden = true;
    }
    this._open_button = null;
    return;
  }
  /**
   * Escape key closes the currently-open group and restores focus
   * to its major button -- but only when the keystroke originated
   * INSIDE the sidebar. The listener sits on the document (the
   * sidebar container is re-built every render), so without the
   * containment guard an Escape aimed at a modal or the command
   * palette would also collapse the accordion and yank focus into
   * the sidebar. No outside-click handler: the accordion is meant
   * to stay open until the user picks a different major. An Escape
   * something else already handled (defaultPrevented -- e.g. the
   * overlay drawer closing itself) is left alone, so one keystroke
   * does one thing.
   */
  _attach_keydown() {
    const on_document_keydown = (event) => {
      if (event.key !== "Escape" || event.defaultPrevented === true) {
        return;
      }
      if (this._open_button === null) {
        return;
      }
      const target = event.target;
      if (target instanceof Node === false) {
        return;
      }
      if (this._container.contains(target) === false) {
        return;
      }
      const button = this._open_button;
      this._close_group();
      button.focus();
    };
    document.addEventListener("keydown", on_document_keydown);
    const detach = () => {
      document.removeEventListener("keydown", on_document_keydown);
    };
    return detach;
  }
  /**
   * Helper — build one ``<a>`` element representing a sidebar
   * entry. Text-only (no ``innerHTML``) per the design's security
   * notes.
   */
  _build_entry_element(label, route, active_path) {
    const link = document.createElement("a");
    link.href = route;
    link.textContent = label;
    link.classList.add("pyc-site-shell__sidebar-entry");
    link.setAttribute("tabindex", "-1");
    if (route === active_path) {
      link.setAttribute("aria-current", "page");
    }
    link.addEventListener("click", (event) => {
      const mouse_event = event;
      if (mouse_event.defaultPrevented === true) {
        return;
      }
      if (mouse_event.button !== void 0 && mouse_event.button !== 0) {
        return;
      }
      if (mouse_event.metaKey === true || mouse_event.ctrlKey === true || mouse_event.shiftKey === true || mouse_event.altKey === true) {
        return;
      }
      // The pychestrate site is server-rendered: every sidebar
      // route is a distinct Flask page. Let the <a href> do a
      // real browser navigation; fire telemetry first.
      if (this._on_entry_clicked !== null) {
        this._on_entry_clicked(route, label);
      }
    });
    return link;
  }
}
export {
  SidebarRenderer
};
