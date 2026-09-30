// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/empty-state.js
var EMAIL_PATTERN = /^[^\s@<>"']+@[^\s@<>"']+\.[^\s@<>"']+$/;
function build_request_link(contact, login_name) {
  const lines = ["Hello,", "", "Please give my Pychestrate account a role so I can use it."];
  if (login_name.length > 0) {
    lines.push("", "Account: " + login_name);
  }
  const link = document.createElement("a");
  link.setAttribute(
    "href",
    "mailto:" + contact + "?subject=" + encodeURIComponent("Pychestrate access request") + "&body=" + encodeURIComponent(lines.join("\n"))
  );
  link.setAttribute("data-role", "request-access");
  link.textContent = "Email " + contact + " to request access";
  return link;
}
function build_empty_state(options) {
  const settings = options !== null && typeof options === "object" ? options : {};
  const contact = typeof settings.admin_contact === "string" ? settings.admin_contact.trim() : "";
  const login_name = typeof settings.user_login_name === "string" ? settings.user_login_name.trim() : "";
  const panel = document.createElement("mj-empty-state");
  panel.setAttribute("heading", "Your account has no access yet");
  panel.setAttribute("role", "status");
  panel.setAttribute("heading-level", "1");
  panel.classList.add("pyc-site-shell__empty-state");
  const body = document.createElement("p");
  body.setAttribute("slot", "description");
  body.classList.add("pyc-site-shell__empty-state-body");
  body.textContent = "Ask an administrator to grant you a role so you can use Pychestrate.";
  panel.appendChild(body);
  if (contact.length > 0) {
    const who = document.createElement("p");
    who.setAttribute("slot", "description");
    who.classList.add("pyc-site-shell__empty-state-body");
    who.setAttribute("data-role", "admin-contact");
    if (EMAIL_PATTERN.test(contact) === true) {
      who.appendChild(build_request_link(contact, login_name));
    } else {
      who.textContent = "To ask for access, contact " + contact + ".";
    }
    panel.appendChild(who);
  }
  return panel;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/flash-notices.js
var FLASH_SELECTOR = "div.alert.alert-success, div.alert.alert-error, div.alert.alert-danger, div.alert.alert-warning, div.alert.alert-info";
var CATEGORY_TO_SEVERITY = {
  "alert-success": "success",
  "alert-error": "error",
  "alert-danger": "error",
  "alert-warning": "warning",
  "alert-info": "info"
};
function extract_flash_messages(nodes) {
  const flashes = [];
  const remaining_nodes = [];
  for (const node of nodes) {
    if (node.nodeType !== Node.ELEMENT_NODE) {
      remaining_nodes.push(node);
      continue;
    }
    const element = node;
    if (element.matches(FLASH_SELECTOR) === true) {
      flashes.push(_flash_from(element));
      continue;
    }
    for (const found of Array.from(
      element.querySelectorAll(FLASH_SELECTOR)
    )) {
      flashes.push(_flash_from(found));
      found.remove();
    }
    remaining_nodes.push(element);
  }
  const rtnval = { flashes, remaining_nodes };
  return rtnval;
}
function _flash_from(flash_element) {
  const rtnval = {
    severity: _severity_for(flash_element),
    message: flash_element.textContent.trim()
  };
  return rtnval;
}
function build_flash_notice(flash) {
  const notice = document.createElement("mj-alert");
  notice.setAttribute("severity", flash.severity);
  notice.setAttribute("dismissible", "");
  notice.setAttribute("open", "");
  notice.classList.add("pyc-site-shell__flash-notice");
  const message = document.createElement("span");
  message.classList.add("pyc-site-shell__flash-notice-message");
  message.textContent = flash.message;
  notice.appendChild(message);
  notice.addEventListener("mj-alert-close", () => {
    if (notice.parentNode !== null) {
      notice.parentNode.removeChild(notice);
    }
  });
  return notice;
}
function _severity_for(flash_element) {
  for (const class_name of Array.from(flash_element.classList)) {
    const severity = CATEGORY_TO_SEVERITY[class_name];
    if (severity !== void 0) {
      return severity;
    }
  }
  return "info";
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/header.js
var LOGOUT_PATH = "/logout";
var ACCOUNT_PANEL_ID = "pyc-site-shell-account-panel";
var NAV_TOGGLE_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true" focusable="false"><path d="M4 6h16" /><path d="M4 12h16" /><path d="M4 18h16" /></svg>';
var SEARCH_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></svg>';
var CHEVRON_DOWN_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M6 9l6 6 6-6" /></svg>';
function build_header(options) {
  const app_bar = document.createElement("mj-app-bar");
  app_bar.setAttribute("slot", "app-bar");
  app_bar.setAttribute("sticky", "");
  app_bar.classList.add("pyc-site-shell__header");
  if (typeof options.on_nav_toggle === "function") {
    const nav_toggle = build_nav_toggle(
      options.on_nav_toggle,
      options.nav_open_initial === true,
      options.nav_controls_id
    );
    app_bar.appendChild(nav_toggle);
  }
  const brand = document.createElement("span");
  brand.setAttribute("slot", "brand");
  brand.classList.add("pyc-site-shell__brand");
  const brand_link = document.createElement("a");
  brand_link.href = "/";
  brand_link.classList.add("pyc-site-shell__brand-link");
  brand_link.textContent = options.brand_label;
  brand_link.setAttribute("aria-label", options.brand_label + " home");
  brand.appendChild(brand_link);
  app_bar.appendChild(brand);
  if (typeof options.on_palette_hint_activate === "function") {
    const hint = build_palette_hint(
      options.palette_shortcut_label,
      options.on_palette_hint_activate
    );
    app_bar.appendChild(hint);
  }
  const display_name = options.user_display_name !== null && options.user_display_name !== void 0 ? options.user_display_name : "Account";
  app_bar.appendChild(build_account_menu(options, display_name));
  return app_bar;
}
function build_account_menu(options, display_name) {
  const actions = document.createElement("div");
  actions.setAttribute("slot", "actions");
  actions.classList.add("pyc-site-shell__user-menu");
  const account_button = document.createElement("button");
  account_button.type = "button";
  account_button.classList.add("pyc-site-shell__account-button");
  account_button.setAttribute("aria-expanded", "false");
  account_button.setAttribute("aria-controls", ACCOUNT_PANEL_ID);
  const account_prefix = document.createElement("span");
  account_prefix.classList.add("pyc-site-shell__visually-hidden");
  account_prefix.textContent = "Account: ";
  const account_name = document.createElement("span");
  account_name.classList.add("pyc-site-shell__account-button-name");
  account_name.textContent = display_name;
  const account_chevron = document.createElement("span");
  account_chevron.classList.add("pyc-site-shell__account-button-chevron");
  account_chevron.setAttribute("aria-hidden", "true");
  account_chevron.innerHTML = CHEVRON_DOWN_ICON_SVG;
  account_button.appendChild(account_prefix);
  account_button.appendChild(account_name);
  account_button.appendChild(account_chevron);
  actions.appendChild(account_button);
  const panel = document.createElement("div");
  panel.id = ACCOUNT_PANEL_ID;
  panel.classList.add("pyc-site-shell__account-panel");
  const login_name = typeof options.user_login_name === "string" ? options.user_login_name : "";
  const name_label = document.createElement("span");
  name_label.classList.add("pyc-site-shell__user-menu-name");
  name_label.textContent = login_name.length > 0 && login_name !== display_name ? "Signed in as " + display_name + " (" + login_name + ")" : "Signed in as " + display_name;
  panel.appendChild(name_label);
  if (typeof options.on_theme_toggle === "function") {
    const theme_button = document.createElement("mj-button");
    theme_button.setAttribute("type", "button");
    theme_button.setAttribute("variant", "tertiary");
    theme_button.setAttribute("size", "sm");
    theme_button.classList.add("pyc-site-shell__theme-toggle");
    theme_button.addEventListener("click", (event) => {
      event.preventDefault();
      options.on_theme_toggle();
    });
    update_theme_toggle(theme_button, options.current_theme);
    panel.appendChild(theme_button);
  }
  const preferences_link = document.createElement("a");
  preferences_link.href = "/account/preferences";
  preferences_link.classList.add("pyc-site-shell__preferences-link");
  preferences_link.textContent = "Preferences";
  panel.appendChild(preferences_link);
  const tokens_link = document.createElement("a");
  tokens_link.href = "/account/api-tokens";
  tokens_link.classList.add("pyc-site-shell__preferences-link", "pyc-site-shell__tokens-link");
  tokens_link.textContent = "API tokens";
  panel.appendChild(tokens_link);
  const help_links = [
    { text: "API reference", href: "/api/docs", css: "pyc-site-shell__api-reference-link" },
    { text: "Error types", href: "/errors", css: "pyc-site-shell__error-types-link" }
  ];
  const user_guide_url = typeof options.user_guide_url === "string" ? options.user_guide_url : "";
  if (user_guide_url.length > 0) {
    help_links.unshift({ text: "User guide", href: user_guide_url, css: "pyc-site-shell__user-guide-link" });
  }
  help_links.forEach((entry) => {
    const link = document.createElement("a");
    link.href = entry.href;
    link.classList.add("pyc-site-shell__preferences-link", "pyc-site-shell__help-link", entry.css);
    link.textContent = entry.text;
    panel.appendChild(link);
  });
  const logout_button = document.createElement("mj-button");
  logout_button.setAttribute("type", "button");
  logout_button.setAttribute("variant", "tertiary");
  logout_button.setAttribute("size", "sm");
  logout_button.classList.add("pyc-site-shell__logout-button");
  logout_button.textContent = "Sign out";
  logout_button.addEventListener("click", (event) => {
    event.preventDefault();
    const csrf_token = typeof options.csrf_token === "string" ? options.csrf_token : "";
    if (csrf_token.length === 0) {
      window.location.assign(LOGOUT_PATH);
      return;
    }
    const form = document.createElement("form");
    form.method = "post";
    form.action = LOGOUT_PATH;
    form.hidden = true;
    const token_input = document.createElement("input");
    token_input.type = "hidden";
    token_input.name = "csrf_token";
    token_input.value = csrf_token;
    form.appendChild(token_input);
    document.body.appendChild(form);
    form.submit();
  });
  panel.appendChild(logout_button);
  const service_version = typeof options.service_version === "string" ? options.service_version : "";
  if (service_version.length > 0) {
    const version_label = document.createElement("span");
    version_label.classList.add("pyc-site-shell__service-version");
    version_label.textContent = "Pychestrate " + service_version;
    panel.appendChild(version_label);
  }
  actions.appendChild(panel);
  wire_account_disclosure(actions, account_button, panel);
  return actions;
}
function wire_account_disclosure(container, button, panel) {
  const set_open = (open) => {
    button.setAttribute("aria-expanded", open === true ? "true" : "false");
    if (open === true) {
      panel.setAttribute("data-open", "");
    } else {
      panel.removeAttribute("data-open");
    }
  };
  const is_open = () => panel.hasAttribute("data-open");
  button.addEventListener("click", (event) => {
    event.preventDefault();
    set_open(is_open() === false);
  });
  container.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || is_open() === false) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    set_open(false);
    button.focus();
  });
  container.addEventListener("focusout", (event) => {
    const next = event.relatedTarget;
    if (next instanceof Node && container.contains(next) === true) {
      return;
    }
    set_open(false);
  });
  document.addEventListener("click", (event) => {
    if (is_open() === false) {
      return;
    }
    if (event.composedPath().includes(container) === true) {
      return;
    }
    set_open(false);
  });
  return;
}
function update_theme_toggle(theme_button, current_theme) {
  const is_dark = current_theme === "dark";
  theme_button.textContent = is_dark === true ? "Theme: Dark" : "Theme: Light";
  theme_button.setAttribute("title", is_dark === true ? "Switch to the light theme" : "Switch to the dark theme");
  theme_button.setAttribute("data-theme-state", is_dark === true ? "dark" : "light");
  return;
}
function build_nav_toggle(on_nav_toggle, nav_open_initial, nav_controls_id) {
  const nav_toggle = document.createElement("button");
  nav_toggle.type = "button";
  nav_toggle.setAttribute("slot", "brand");
  nav_toggle.classList.add("pyc-site-shell__nav-toggle");
  nav_toggle.setAttribute("aria-label", "Toggle navigation sidebar");
  nav_toggle.setAttribute("title", "Toggle navigation sidebar");
  nav_toggle.setAttribute(
    "aria-expanded",
    nav_open_initial === true ? "true" : "false"
  );
  if (typeof nav_controls_id === "string" && nav_controls_id.length > 0) {
    nav_toggle.setAttribute("aria-controls", nav_controls_id);
  }
  nav_toggle.innerHTML = NAV_TOGGLE_ICON_SVG;
  nav_toggle.addEventListener("click", (event) => {
    event.preventDefault();
    on_nav_toggle();
  });
  return nav_toggle;
}
function build_palette_hint(shortcut_label, on_activate) {
  const resolved_label = typeof shortcut_label === "string" && shortcut_label.length > 0 ? shortcut_label : "Ctrl+K";
  const hint = document.createElement("button");
  hint.type = "button";
  hint.setAttribute("slot", "brand");
  hint.classList.add("pyc-site-shell__palette-hint");
  hint.setAttribute(
    "title",
    "Open the command palette to search navigation (" + resolved_label + ")"
  );
  hint.setAttribute("aria-label", "Open the command palette");
  hint.setAttribute("aria-keyshortcuts", resolved_label === "\u2318K" ? "Meta+K" : "Control+K");
  const icon = document.createElement("span");
  icon.classList.add("pyc-site-shell__palette-hint-icon");
  icon.setAttribute("aria-hidden", "true");
  icon.innerHTML = SEARCH_ICON_SVG;
  const shortcut = document.createElement("span");
  shortcut.classList.add("pyc-site-shell__palette-hint-shortcut");
  shortcut.textContent = resolved_label;
  hint.appendChild(icon);
  hint.appendChild(shortcut);
  hint.addEventListener("click", (event) => {
    event.preventDefault();
    on_activate();
  });
  return hint;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/confirm-delegate.js
var CONFIRM_ATTRIBUTE = "data-confirm";
var INSTALLED_FLAG = "__pycConfirmDelegateInstalled";
function resolve_confirm_message(form, submitter) {
  let raw = null;
  if (submitter !== null && submitter !== void 0 && typeof submitter.getAttribute === "function") {
    raw = submitter.getAttribute(CONFIRM_ATTRIBUTE);
  }
  if (raw === null) {
    raw = form.getAttribute(CONFIRM_ATTRIBUTE);
  }
  if (raw === null) {
    return null;
  }
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return "Are you sure?";
  }
  return trimmed;
}
function ask_with_dialog(message, confirm_label) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.classList.add("pyc-confirm");
    dialog.setAttribute("aria-labelledby", "pyc-confirm-title");
    dialog.setAttribute("aria-describedby", "pyc-confirm-message");
    const form = document.createElement("form");
    form.setAttribute("method", "dialog");
    const title = document.createElement("h2");
    title.id = "pyc-confirm-title";
    title.classList.add("pyc-confirm__title");
    title.textContent = "Please confirm";
    form.appendChild(title);
    const body = document.createElement("div");
    body.id = "pyc-confirm-message";
    body.classList.add("pyc-confirm__message");
    for (const line of message.split(/\r?\n/)) {
      if (line.trim().length === 0) {
        continue;
      }
      const paragraph = document.createElement("p");
      paragraph.textContent = line.trim();
      body.appendChild(paragraph);
    }
    form.appendChild(body);
    const actions = document.createElement("div");
    actions.classList.add("pyc-confirm__actions");
    const cancel = document.createElement("button");
    cancel.type = "submit";
    cancel.value = "cancel";
    cancel.autofocus = true;
    cancel.classList.add("pyc-confirm__button");
    cancel.setAttribute("data-role", "confirm-cancel");
    cancel.textContent = "Cancel";
    const accept = document.createElement("button");
    accept.type = "submit";
    accept.value = "confirm";
    accept.classList.add("pyc-confirm__button", "pyc-confirm__button--danger");
    accept.setAttribute("data-role", "confirm-accept");
    accept.textContent = confirm_label;
    actions.appendChild(cancel);
    actions.appendChild(accept);
    form.appendChild(actions);
    dialog.appendChild(form);
    dialog.addEventListener("close", () => {
      const accepted = dialog.returnValue === "confirm";
      dialog.remove();
      resolve(accepted);
    });
    document.body.appendChild(dialog);
    dialog.showModal();
  });
}
async function ask_confirmation(message, confirm_label) {
  const dialog_ctor = typeof customElements !== "undefined" ? customElements.get("mj-dialog") : void 0;
  if (dialog_ctor !== void 0 && typeof dialog_ctor.confirm === "function") {
    try {
      const result = await dialog_ctor.confirm({ message, confirmLabel: confirm_label, cancelLabel: "Cancel" });
      return result === true;
    } catch (error) {
    }
  }
  if (typeof HTMLDialogElement === "function" && typeof HTMLDialogElement.prototype.showModal === "function") {
    return ask_with_dialog(message, confirm_label);
  }
  return window.confirm(message);
}
function resolve_confirm_label(submitter) {
  if (submitter !== null && submitter !== void 0 && typeof submitter.textContent === "string") {
    const text = submitter.textContent.replace(/\s+/g, " ").trim();
    if (text.length > 0 && text.length <= 40) {
      return text;
    }
  }
  return "Continue";
}
function install_confirm_delegate(root) {
  const target = root !== void 0 && root !== null ? root : document;
  if (target[INSTALLED_FLAG] === true) {
    return;
  }
  target[INSTALLED_FLAG] = true;
  target.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    const submitter = event.submitter !== void 0 ? event.submitter : null;
    const submitter_confirms = submitter !== null && submitter.hasAttribute(CONFIRM_ATTRIBUTE);
    if (form.hasAttribute(CONFIRM_ATTRIBUTE) === false && submitter_confirms === false) {
      return;
    }
    if (form.dataset.pycConfirmed === "true") {
      delete form.dataset.pycConfirmed;
      return;
    }
    event.preventDefault();
    const message = resolve_confirm_message(form, submitter);
    ask_confirmation(message, resolve_confirm_label(submitter)).then((accepted) => {
      if (accepted !== true) {
        return;
      }
      window.setTimeout(() => {
        form.dataset.pycConfirmed = "true";
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit(submitter !== null && submitter.form === form ? submitter : void 0);
        } else {
          form.submit();
        }
      }, 0);
    });
  }, true);
  target.addEventListener("pyc-confirm-request", (event) => {
    const detail = event.detail;
    if (detail === null || typeof detail !== "object" || typeof detail.message !== "string" || typeof detail.resolve !== "function") {
      return;
    }
    event.preventDefault();
    const label = typeof detail.confirm_label === "string" && detail.confirm_label.trim().length > 0 ? detail.confirm_label.trim() : "Continue";
    ask_confirmation(detail.message, label).then((accepted) => detail.resolve(accepted === true));
  });
  return;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/reveal-toggle.js
var REVEAL_ATTRIBUTE = "data-reveal-for";
var BUSY_ATTRIBUTE = "data-busy-label";
var INSTALLED_FLAG2 = "__pycRevealToggleInstalled";
function toggle_reveal(button) {
  const target_id = button.getAttribute(REVEAL_ATTRIBUTE);
  if (target_id === null || target_id.length === 0) {
    return;
  }
  const input = document.getElementById(target_id);
  if (input === null) {
    return;
  }
  const revealed = input.getAttribute("type") === "text";
  input.setAttribute("type", revealed ? "password" : "text");
  button.setAttribute("aria-pressed", revealed ? "false" : "true");
  const show_label = button.getAttribute("data-show-label") || "Show";
  const hide_label = button.getAttribute("data-hide-label") || "Hide";
  button.textContent = revealed ? show_label : hide_label;
  return;
}
function mark_busy(form) {
  const label = form.getAttribute(BUSY_ATTRIBUTE);
  form.setAttribute("aria-busy", "true");
  const buttons = form.querySelectorAll('button[type="submit"], input[type="submit"]');
  buttons.forEach((button) => {
    button.disabled = true;
    if (label !== null && label.length > 0) {
      if (button.tagName === "BUTTON") {
        button.dataset.pycIdleLabel = button.textContent;
        button.textContent = label;
      } else {
        button.value = label;
      }
    }
  });
  return;
}
function install_reveal_toggle(root) {
  const target = root !== void 0 && root !== null ? root : document;
  if (target[INSTALLED_FLAG2] === true) {
    return;
  }
  target[INSTALLED_FLAG2] = true;
  target.addEventListener("click", (event) => {
    const origin = event.target;
    if (!(origin instanceof Element)) {
      return;
    }
    const button = origin.closest("[" + REVEAL_ATTRIBUTE + "]");
    if (button === null) {
      return;
    }
    event.preventDefault();
    toggle_reveal(button);
  });
  target.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    if (form.hasAttribute(BUSY_ATTRIBUTE) === false) {
      return;
    }
    if (event.defaultPrevented === true) {
      return;
    }
    window.setTimeout(() => {
      mark_busy(form);
    }, 0);
  });
  return;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/log-viewer.js
var VIEWER_SELECTOR = ".pyc-log-viewer";
var OUTPUT_SELECTOR = ".pyc-log-viewer__output";
var INSTALLED_FLAG3 = "__pycLogViewerInstalled";
var DEFAULT_REFRESH_SECONDS = 10;
function is_following(viewer) {
  const toggle = viewer.querySelector("[data-log-follow]");
  if (toggle === null) {
    return true;
  }
  return toggle.checked === true;
}
function scroll_to_end(output) {
  output.scrollTop = output.scrollHeight;
  return;
}
async function refresh_once(viewer) {
  const source = viewer.getAttribute("data-log-source") || window.location.href;
  let response;
  try {
    response = await fetch(source, { credentials: "same-origin", cache: "no-store", headers: { "Accept": "text/html" } });
  } catch (error) {
    return false;
  }
  if (response.ok !== true) {
    return false;
  }
  const html = await response.text();
  const parsed = new DOMParser().parseFromString(html, "text/html");
  const fresh_viewer = parsed.querySelector(VIEWER_SELECTOR);
  const fresh_output = parsed.querySelector(OUTPUT_SELECTOR);
  const output = viewer.querySelector(OUTPUT_SELECTOR);
  if (fresh_output === null || output === null) {
    return false;
  }
  const follow = is_following(viewer);
  if (output.textContent !== fresh_output.textContent) {
    output.textContent = fresh_output.textContent;
    if (follow === true) {
      scroll_to_end(output);
    }
  }
  const still_running = fresh_viewer !== null && fresh_viewer.getAttribute("data-log-running") === "true";
  viewer.setAttribute("data-log-running", still_running ? "true" : "false");
  const status = viewer.querySelector("[data-log-status]");
  const fresh_status = fresh_viewer !== null ? fresh_viewer.querySelector("[data-log-status]") : null;
  if (status !== null) {
    if (fresh_status !== null) {
      status.textContent = fresh_status.textContent;
    } else {
      status.textContent = still_running ? "Live: refreshing while the job runs" : "Finished: log is complete";
    }
  }
  return still_running;
}
function schedule(viewer) {
  if (viewer.getAttribute("data-log-running") !== "true") {
    return;
  }
  const seconds = Number.parseInt(viewer.getAttribute("data-log-refresh-seconds") || "", 10);
  const delay = Number.isFinite(seconds) && seconds > 0 ? seconds * 1e3 : DEFAULT_REFRESH_SECONDS * 1e3;
  window.setTimeout(() => {
    if (document.body.contains(viewer) === false) {
      return;
    }
    refresh_once(viewer).then((still_running) => {
      if (still_running === true) {
        schedule(viewer);
      }
    });
  }, delay);
  return;
}
function copy_output(viewer) {
  const output = viewer.querySelector(OUTPUT_SELECTOR);
  if (output === null || typeof navigator === "undefined" || !navigator.clipboard) {
    return;
  }
  navigator.clipboard.writeText(output.textContent).then(() => {
    const status = viewer.querySelector("[data-log-status]");
    if (status !== null) {
      const previous = status.textContent;
      status.textContent = "Copied to clipboard";
      window.setTimeout(() => {
        status.textContent = previous;
      }, 2e3);
    }
  }).catch(() => {
  });
  return;
}
function download_output(viewer) {
  const output = viewer.querySelector(OUTPUT_SELECTOR);
  if (output === null) {
    return;
  }
  const name = viewer.getAttribute("data-log-filename") || "log.txt";
  const blob = new Blob([output.textContent], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => {
    URL.revokeObjectURL(url);
  }, 1e3);
  return;
}
function initialise_viewer(viewer) {
  if (viewer.dataset.pycLogInitialised === "true") {
    return;
  }
  viewer.dataset.pycLogInitialised = "true";
  const output = viewer.querySelector(OUTPUT_SELECTOR);
  if (output !== null && is_following(viewer) === true) {
    scroll_to_end(output);
  }
  schedule(viewer);
  return;
}
function install_log_viewer(root) {
  const target = root !== void 0 && root !== null ? root : document;
  if (target[INSTALLED_FLAG3] === true) {
    return;
  }
  target[INSTALLED_FLAG3] = true;
  target.addEventListener("click", (event) => {
    const origin = event.target;
    if (!(origin instanceof Element)) {
      return;
    }
    const action = origin.closest("[data-log-action]");
    if (action === null) {
      return;
    }
    const viewer = action.closest(VIEWER_SELECTOR);
    if (viewer === null) {
      return;
    }
    event.preventDefault();
    const kind = action.getAttribute("data-log-action");
    if (kind === "copy") {
      copy_output(viewer);
    } else if (kind === "download") {
      download_output(viewer);
    } else if (kind === "refresh") {
      refresh_once(viewer);
    }
  });
  const scan = () => {
    target.querySelectorAll(VIEWER_SELECTOR).forEach((viewer) => {
      initialise_viewer(viewer);
    });
  };
  scan();
  if (typeof MutationObserver === "function" && target === document) {
    const observer = new MutationObserver(() => {
      scan();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }
  return;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/live-region.js
var REGION_SELECTOR = "[data-live-region]";
var INSTALLED_FLAG4 = "__pycLiveRegionInstalled";
var DEFAULT_REFRESH_SECONDS2 = 10;
function is_active(region) {
  return region.getAttribute("data-live-region-active") === "true";
}
async function refresh_once2(region) {
  const name = region.getAttribute("data-live-region") || "";
  let response;
  try {
    response = await fetch(window.location.href, { credentials: "same-origin", cache: "no-store", headers: { "Accept": "text/html" } });
  } catch (error) {
    return true;
  }
  if (response.ok !== true) {
    return response.status >= 500;
  }
  const html = await response.text();
  const parsed = new DOMParser().parseFromString(html, "text/html");
  let fresh = null;
  parsed.querySelectorAll(REGION_SELECTOR).forEach((candidate) => {
    if (fresh === null && candidate.getAttribute("data-live-region") === name) {
      fresh = candidate;
    }
  });
  if (fresh === null) {
    return false;
  }
  if (region.innerHTML !== fresh.innerHTML) {
    region.innerHTML = fresh.innerHTML;
  }
  const still_active = is_active(fresh);
  region.setAttribute("data-live-region-active", still_active ? "true" : "false");
  return still_active;
}
function schedule2(region) {
  if (is_active(region) !== true) {
    return;
  }
  const seconds = Number.parseInt(region.getAttribute("data-live-region-refresh-seconds") || "", 10);
  const delay = Number.isFinite(seconds) && seconds > 0 ? seconds * 1e3 : DEFAULT_REFRESH_SECONDS2 * 1e3;
  window.setTimeout(() => {
    if (document.body.contains(region) === false) {
      return;
    }
    refresh_once2(region).then((still_active) => {
      if (still_active === true) {
        schedule2(region);
      }
    });
  }, delay);
  return;
}
function initialise_region(region) {
  if (region.dataset.pycLiveRegionInitialised === "true") {
    return;
  }
  region.dataset.pycLiveRegionInitialised = "true";
  schedule2(region);
  return;
}
function install_live_region(root) {
  const target = root !== void 0 && root !== null ? root : document;
  if (target[INSTALLED_FLAG4] === true) {
    return;
  }
  target[INSTALLED_FLAG4] = true;
  const scan = () => {
    target.querySelectorAll(REGION_SELECTOR).forEach((region) => {
      initialise_region(region);
    });
  };
  scan();
  if (typeof MutationObserver === "function" && target === document) {
    const observer = new MutationObserver(() => {
      scan();
    });
    observer.observe(document.body, { childList: true, subtree: true });
  }
  return;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/chip-tone.js
var TONE_PROPERTIES = {
  ok: {
    "--mj-chip-bg": "var(--pyc-color-success-surface, hsla(145, 63%, 42%, 0.16))",
    "--mj-chip-color": "var(--pyc-color-on-success-surface, hsl(145, 63%, 24%))",
    "--mj-chip-border-color": "transparent"
  },
  warn: {
    "--mj-chip-bg": "var(--pyc-color-warning-surface, hsla(38, 100%, 67%, 0.2))",
    "--mj-chip-color": "var(--pyc-color-on-warning-surface, hsl(32, 75%, 21%))",
    "--mj-chip-border-color": "transparent"
  },
  error: {
    "--mj-chip-bg": "var(--pyc-color-error-surface, hsla(0, 72%, 51%, 0.14))",
    "--mj-chip-color": "var(--pyc-color-on-error-surface, hsl(0, 72%, 34%))",
    "--mj-chip-border-color": "transparent"
  }
};
var MANAGED_PROPERTIES = ["--mj-chip-bg", "--mj-chip-color", "--mj-chip-border-color"];
var TONE_ATTRIBUTE = "data-tone";
var PATCHED_FLAG = "__pycChipTonePatched";
var OBSERVER_KEY = "__pycChipToneObserver";
function apply_chip_tone(chip) {
  const tone = chip.getAttribute(TONE_ATTRIBUTE) || "";
  const properties = TONE_PROPERTIES[tone];
  for (const name of MANAGED_PROPERTIES) {
    if (properties !== void 0) {
      chip.style.setProperty(name, properties[name]);
    } else {
      chip.style.removeProperty(name);
    }
  }
  return;
}
function watch_chip_tone(chip) {
  apply_chip_tone(chip);
  if (chip[OBSERVER_KEY] === void 0 && typeof MutationObserver === "function") {
    const observer = new MutationObserver(() => {
      apply_chip_tone(chip);
    });
    observer.observe(chip, { attributes: true, attributeFilter: [TONE_ATTRIBUTE] });
    chip[OBSERVER_KEY] = observer;
  }
  return;
}
function patch_chip_class(chip_class) {
  const proto = chip_class.prototype;
  if (proto[PATCHED_FLAG] === true) {
    return;
  }
  proto[PATCHED_FLAG] = true;
  const original_connected = proto.onConnected;
  const original_disconnected = proto.onDisconnected;
  proto.onConnected = function onConnected() {
    if (typeof original_connected === "function") {
      original_connected.call(this);
    }
    watch_chip_tone(this);
    return;
  };
  proto.onDisconnected = function onDisconnected() {
    if (typeof original_disconnected === "function") {
      original_disconnected.call(this);
    }
    const observer = this[OBSERVER_KEY];
    if (observer !== void 0) {
      observer.disconnect();
      delete this[OBSERVER_KEY];
    }
    return;
  };
  return;
}
function install_chip_tone() {
  if (typeof customElements === "undefined") {
    return;
  }
  customElements.whenDefined("mj-chip").then(() => {
    patch_chip_class(customElements.get("mj-chip"));
    document.querySelectorAll("mj-chip[" + TONE_ATTRIBUTE + "]").forEach((chip) => {
      watch_chip_tone(chip);
    });
  });
  return;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/shared/datetime.js
var ISO_DATE_TIME_PATTERN = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
var ZONE_DESIGNATOR_PATTERN = /(?:Z|[+-]\d{2}:?\d{2})$/i;
function pad_two(number) {
  const rtnval = (number < 10 ? "0" : "") + String(number);
  return rtnval;
}
function parse_timestamp(value) {
  if (typeof value !== "string" || value.length === 0) {
    const rtnval2 = null;
    return rtnval2;
  }
  let text = value.trim();
  if (ISO_DATE_TIME_PATTERN.test(text) === true && ZONE_DESIGNATOR_PATTERN.test(text) === false) {
    text = text.replace(" ", "T") + "Z";
  }
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime()) === true) {
    const rtnval2 = null;
    return rtnval2;
  }
  const rtnval = parsed;
  return rtnval;
}
function zone_label(instant) {
  try {
    const parts = new Intl.DateTimeFormat(void 0, { timeZoneName: "short" }).formatToParts(instant);
    for (const part of parts) {
      if (part.type === "timeZoneName" && part.value.length > 0) {
        const rtnval2 = part.value;
        return rtnval2;
      }
    }
  } catch (error) {
  }
  const offset_minutes = -instant.getTimezoneOffset();
  const sign = offset_minutes >= 0 ? "+" : "-";
  const magnitude = Math.abs(offset_minutes);
  const rtnval = "UTC" + sign + pad_two(Math.floor(magnitude / 60)) + ":" + pad_two(magnitude % 60);
  return rtnval;
}
function format_instant(instant) {
  const date_part = instant.getFullYear() + "-" + pad_two(instant.getMonth() + 1) + "-" + pad_two(instant.getDate());
  const time_part = pad_two(instant.getHours()) + ":" + pad_two(instant.getMinutes());
  const rtnval = date_part + " " + time_part + " " + zone_label(instant);
  return rtnval;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/home-view.js
var PROJECTS_URL = "/api/v1/projects?per_page=1";
var CLIENTS_URL = "/api/v1/clients?per_page=1";
var RUNS_URL = "/api/v1/runs?per_page=5";
var RECENT_RUN_LIMIT = 5;
function build_home_view(options) {
  const panel = document.createElement("section");
  panel.classList.add("pyc-site-shell__home");
  panel.setAttribute("aria-label", "Home");
  const heading = document.createElement("h1");
  heading.classList.add("pyc-site-shell__home-heading");
  heading.textContent = options.brand_label;
  panel.appendChild(heading);
  const subtitle = document.createElement("p");
  subtitle.classList.add("pyc-site-shell__home-subtitle");
  subtitle.textContent = "Checking what is set up\u2026";
  panel.appendChild(subtitle);
  const status = document.createElement("div");
  status.classList.add("pyc-site-shell__home-status");
  status.setAttribute("aria-live", "polite");
  panel.appendChild(status);
  const sections = document.createElement("details");
  sections.classList.add("pyc-site-shell__home-sections");
  sections.setAttribute("data-role", "all-sections");
  const summary = document.createElement("summary");
  summary.textContent = "All sections";
  sections.appendChild(summary);
  sections.appendChild(build_nav_link_grid(options.visible_sidebar));
  panel.appendChild(sections);
  void hydrate_home_view(panel, subtitle, status, sections, options);
  return panel;
}
async function hydrate_home_view(panel, subtitle, status, sections, options) {
  const fetch_impl = typeof options.fetch_impl === "function" ? options.fetch_impl : window.fetch.bind(window);
  const routes = visible_routes(options.visible_sidebar);
  const wants_projects = routes.has("/projects");
  const wants_clients = routes.has("/clients");
  const wants_runs = routes.has("/runs");
  const [projects, clients, runs] = await Promise.all([
    wants_projects ? fetch_page(PROJECTS_URL, fetch_impl) : Promise.resolve(null),
    wants_clients ? fetch_page(CLIENTS_URL, fetch_impl) : Promise.resolve(null),
    wants_runs ? fetch_page(RUNS_URL, fetch_impl) : Promise.resolve(null)
  ]);
  const counts = {
    projects: total_of(projects),
    clients: total_of(clients),
    runs: total_of(runs)
  };
  const steps = build_steps(counts, routes);
  const readable = counts.projects !== null || counts.clients !== null || counts.runs !== null;
  status.textContent = "";
  if (readable === false) {
    subtitle.textContent = "Choose a destination to get started.";
    sections.open = true;
  } else if (all_done(steps) === true) {
    subtitle.textContent = "You are set up. Pick up where you left off.";
    sections.open = false;
  } else {
    subtitle.textContent = "Three steps to your first run.";
    status.appendChild(build_checklist(steps));
    sections.open = false;
  }
  if (runs !== null && Array.isArray(runs.items) === true && runs.items.length > 0) {
    status.appendChild(build_recent_runs(runs.items.slice(0, RECENT_RUN_LIMIT)));
  }
  panel.setAttribute("data-home-ready", "true");
  panel.dispatchEvent(new CustomEvent("pyc-site-shell-home-hydrated", { bubbles: true }));
  return;
}
async function fetch_page(url, fetch_impl) {
  let rtnval = null;
  try {
    const response = await fetch_impl(url, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    if (response.ok === true) {
      rtnval = await response.json();
    }
  } catch (reason) {
    console.warn("pychestrate.ui.shell.home_fetch_failed", { url, reason: String(reason) });
  }
  return rtnval;
}
function total_of(body) {
  let rtnval = null;
  if (Array.isArray(body) === true) {
    rtnval = body.length;
  } else if (body !== null && typeof body === "object") {
    if (body.meta !== void 0 && body.meta !== null && typeof body.meta.total === "number") {
      rtnval = body.meta.total;
    } else if (Array.isArray(body.items) === true) {
      rtnval = body.items.length;
    }
  }
  return rtnval;
}
function visible_routes(visible_sidebar) {
  const rtnval = /* @__PURE__ */ new Set();
  for (const entry of visible_sidebar.ungrouped) {
    rtnval.add(entry.route);
  }
  for (const bucket of visible_sidebar.groups) {
    for (const entry of bucket.entries) {
      rtnval.add(entry.route);
    }
  }
  return rtnval;
}
function build_steps(counts, routes) {
  const project_actions = [];
  if (routes.has("/projects") === true) {
    project_actions.push({ label: "Create a project", href: "/projects/create" });
  }
  const pod_actions = [];
  let pod_detail = "A pod is a machine that runs your jobs. Mint an enrollment token, then run the client on the machine.";
  if (routes.has("/admin/enrollment-tokens") === true) {
    pod_actions.push({ label: "Mint an enrollment token", href: "/admin/enrollment-tokens" });
  } else {
    pod_detail = "A pod is a machine that runs your jobs. Ask an administrator to enroll one.";
  }
  const run_actions = [];
  if (routes.has("/test-catalog") === true) {
    run_actions.push({ label: "Import tests", href: "/test-catalog" });
  }
  if (routes.has("/builds") === true) {
    run_actions.push({ label: "Start a build", href: "/builds" });
  }
  if (routes.has("/runs") === true) {
    run_actions.push({ label: "See runs", href: "/runs" });
  }
  const rtnval = [
    {
      id: "project",
      title: "Create a project",
      detail: "Projects organize your jobs, pods and resources.",
      done: done_from(counts.projects),
      actions: project_actions
    },
    {
      id: "pod",
      title: "Enroll a pod",
      detail: pod_detail,
      done: done_from(counts.clients),
      actions: pod_actions
    },
    {
      id: "run",
      title: "Run something",
      detail: "Add tests, a build or an RPA job to a project, then start a run.",
      done: done_from(counts.runs),
      actions: run_actions
    }
  ];
  return rtnval;
}
function done_from(count) {
  let rtnval = null;
  if (count !== null) {
    rtnval = count > 0;
  }
  return rtnval;
}
function all_done(steps) {
  let rtnval = true;
  for (const step of steps) {
    if (step.done !== true) {
      rtnval = false;
    }
  }
  return rtnval;
}
function build_checklist(steps) {
  const section = document.createElement("section");
  section.classList.add("pyc-site-shell__getting-started");
  section.setAttribute("data-role", "getting-started");
  section.setAttribute("aria-labelledby", "pyc-getting-started-heading");
  const heading = document.createElement("h2");
  heading.id = "pyc-getting-started-heading";
  heading.classList.add("pyc-site-shell__home-section-heading");
  heading.textContent = "Get started";
  section.appendChild(heading);
  const list = document.createElement("ol");
  list.classList.add("pyc-site-shell__checklist");
  for (const step of steps) {
    list.appendChild(build_step(step));
  }
  section.appendChild(list);
  return section;
}
function build_step(step) {
  const item = document.createElement("li");
  item.classList.add("pyc-site-shell__checklist-step");
  item.setAttribute("data-step", step.id);
  let state = "unknown";
  if (step.done === true) {
    state = "done";
  } else if (step.done === false) {
    state = "todo";
  }
  item.setAttribute("data-state", state);
  const mark = document.createElement("span");
  mark.classList.add("pyc-site-shell__checklist-mark");
  mark.setAttribute("aria-hidden", "true");
  mark.textContent = state === "done" ? "\u2713" : "";
  item.appendChild(mark);
  const body = document.createElement("div");
  body.classList.add("pyc-site-shell__checklist-body");
  const title = document.createElement("p");
  title.classList.add("pyc-site-shell__checklist-title");
  title.textContent = step.title;
  if (state === "done") {
    const hidden = document.createElement("span");
    hidden.classList.add("pyc-site-shell__visually-hidden");
    hidden.textContent = " (done)";
    title.appendChild(hidden);
  }
  body.appendChild(title);
  const detail = document.createElement("p");
  detail.classList.add("pyc-site-shell__checklist-detail");
  detail.textContent = step.detail;
  body.appendChild(detail);
  if (state !== "done" && step.actions.length > 0) {
    const actions = document.createElement("p");
    actions.classList.add("pyc-site-shell__checklist-actions");
    for (const action of step.actions) {
      const link = document.createElement("a");
      link.href = action.href;
      link.textContent = action.label;
      actions.appendChild(link);
    }
    body.appendChild(actions);
  }
  item.appendChild(body);
  return item;
}
var RUN_ERROR_STATES = ["failed", "dispatch_failed", "dispatch_lost", "needs_investigation"];
var RUN_WARN_STATES = ["progress_stalled", "dispatch_unconfirmed", "cancel_requested", "cancelling", "cancelled"];
function run_tone(run_state) {
  let rtnval = "neutral";
  if (run_state === "completed") {
    rtnval = "ok";
  } else if (RUN_ERROR_STATES.indexOf(run_state) >= 0) {
    rtnval = "error";
  } else if (RUN_WARN_STATES.indexOf(run_state) >= 0) {
    rtnval = "warn";
  }
  return rtnval;
}
function build_recent_runs(runs) {
  const section = document.createElement("section");
  section.classList.add("pyc-site-shell__recent-runs");
  section.setAttribute("data-role", "recent-runs");
  section.setAttribute("aria-labelledby", "pyc-recent-runs-heading");
  const heading = document.createElement("h2");
  heading.id = "pyc-recent-runs-heading";
  heading.classList.add("pyc-site-shell__home-section-heading");
  heading.textContent = "Recent runs";
  section.appendChild(heading);
  const list = document.createElement("ul");
  list.classList.add("pyc-site-shell__recent-runs-list");
  for (const run of runs) {
    const item = document.createElement("li");
    item.classList.add("pyc-site-shell__recent-run");
    const link = document.createElement("a");
    const run_id = String(run.run_id);
    link.href = "/runs/" + run_id;
    link.textContent = run_id.slice(0, 8);
    item.appendChild(link);
    const chip = document.createElement("mj-chip");
    chip.setAttribute("data-tone", run_tone(run.state));
    chip.textContent = String(run.state);
    item.appendChild(chip);
    const when = document.createElement("span");
    when.classList.add("pyc-site-shell__recent-run-time");
    const stamp = run.completed_at || run.started_at || run.created_at;
    const parsed = stamp ? parse_timestamp(stamp) : null;
    when.textContent = parsed !== null ? format_instant(parsed) : "";
    item.appendChild(when);
    list.appendChild(item);
  }
  section.appendChild(list);
  const all = document.createElement("p");
  all.classList.add("pyc-site-shell__recent-runs-all");
  const all_link = document.createElement("a");
  all_link.href = "/runs";
  all_link.textContent = "All runs";
  all.appendChild(all_link);
  section.appendChild(all);
  return section;
}
function build_nav_link_grid(visible_sidebar) {
  const grid = document.createElement("nav");
  grid.classList.add("pyc-site-shell__nav-grid");
  grid.setAttribute("aria-label", "Site sections");
  if (visible_sidebar.ungrouped.length > 0) {
    const card = build_nav_grid_card(null, visible_sidebar.ungrouped);
    grid.appendChild(card);
  }
  for (const bucket of visible_sidebar.groups) {
    const card = build_nav_grid_card(bucket.group.label, bucket.entries);
    grid.appendChild(card);
  }
  return grid;
}
function build_nav_grid_card(group_label, entries) {
  const card = document.createElement("section");
  card.classList.add("pyc-site-shell__nav-grid-card");
  if (group_label !== null) {
    const heading = document.createElement("h2");
    heading.classList.add("pyc-site-shell__nav-grid-card-heading");
    heading.textContent = group_label;
    card.appendChild(heading);
  }
  const list = document.createElement("ul");
  list.classList.add("pyc-site-shell__nav-grid-list");
  for (const entry of entries) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.href = entry.route;
    link.textContent = entry.label;
    link.classList.add("pyc-site-shell__nav-grid-link");
    item.appendChild(link);
    list.appendChild(item);
  }
  card.appendChild(list);
  return card;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/not-found-view.js
function build_not_found_view(options) {
  const panel = document.createElement("section");
  panel.classList.add("pyc-site-shell__not-found");
  panel.setAttribute("aria-label", "Page not found");
  const heading = document.createElement("h1");
  heading.classList.add("pyc-site-shell__not-found-heading");
  heading.textContent = "Page not found";
  panel.appendChild(heading);
  const body = document.createElement("p");
  body.classList.add("pyc-site-shell__not-found-body");
  body.appendChild(
    document.createTextNode("There is no page at ")
  );
  const path_code = document.createElement("code");
  path_code.classList.add("pyc-site-shell__not-found-path");
  path_code.textContent = options.path;
  body.appendChild(path_code);
  body.appendChild(document.createTextNode("."));
  panel.appendChild(body);
  const home_paragraph = document.createElement("p");
  home_paragraph.classList.add("pyc-site-shell__not-found-home");
  const home_link = document.createElement("a");
  home_link.href = "/";
  home_link.textContent = "Go to the home page";
  home_link.classList.add("pyc-site-shell__not-found-home-link");
  home_paragraph.appendChild(home_link);
  panel.appendChild(home_paragraph);
  const grid = build_nav_link_grid(options.visible_sidebar);
  panel.appendChild(grid);
  return panel;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/degraded-banner.js
var BANNER_MESSAGE = "Permissions could not be refreshed. Using the last known set. Some controls may behave incorrectly.";
var DegradedBanner = class {
  constructor(container, options = null) {
    this._container = container;
    this._element = null;
    this._dismissed = false;
    this._message = BANNER_MESSAGE;
    this._action_label = null;
    this._on_action = null;
    if (options !== null && typeof options === "object") {
      if (typeof options.message === "string" && options.message.length > 0) {
        this._message = options.message;
      }
      if (typeof options.action_label === "string" && options.action_label.length > 0) {
        this._action_label = options.action_label;
      }
      if (typeof options.on_action === "function") {
        this._on_action = options.on_action;
      }
    }
  }
  show() {
    if (this._dismissed === true) {
      return;
    }
    if (this._element !== null && this._element.parentNode !== null) {
      return;
    }
    const banner = document.createElement("mj-alert");
    banner.setAttribute("severity", "warning");
    banner.setAttribute("dismissible", "");
    banner.setAttribute("open", "");
    banner.classList.add("pyc-site-shell__degraded-banner");
    const message = document.createElement("span");
    message.classList.add("pyc-site-shell__degraded-banner-message");
    message.textContent = this._message;
    banner.appendChild(message);
    if (this._action_label !== null && this._on_action !== null) {
      const action_button = document.createElement("mj-button");
      action_button.setAttribute("slot", "actions");
      action_button.setAttribute("type", "button");
      action_button.setAttribute("variant", "tertiary");
      action_button.setAttribute("size", "sm");
      action_button.classList.add(
        "pyc-site-shell__degraded-banner-action"
      );
      action_button.textContent = this._action_label;
      action_button.addEventListener("click", () => {
        this._on_action();
      });
      banner.appendChild(action_button);
    }
    banner.addEventListener("mj-alert-close", () => {
      this._dismissed = true;
      this._element = null;
    });
    this._element = banner;
    this._container.insertBefore(banner, this._container.firstChild);
    return;
  }
  hide() {
    if (this._element !== null && this._element.parentNode !== null) {
      this._element.parentNode.removeChild(this._element);
    }
    this._element = null;
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/session-toast.js
var TOAST_HEADING = "Your session expired. Please sign in again.";
var SessionExpiredToast = class {
  constructor(container) {
    this._container = container;
    this._element = null;
  }
  show() {
    if (this._element !== null && this._element.parentNode !== null) {
      this._element.setAttribute("open", "");
      return;
    }
    const toast = document.createElement("mj-toast");
    toast.setAttribute("severity", "warning");
    toast.setAttribute("heading", TOAST_HEADING);
    toast.setAttribute("auto-dismiss", "0");
    toast.setAttribute("open", "");
    toast.classList.add("pyc-site-shell__session-toast");
    const action = document.createElement("a");
    action.setAttribute("slot", "actions");
    action.classList.add("pyc-site-shell__session-toast-action");
    action.textContent = "Sign in";
    const current_path = window.location.pathname + window.location.search;
    const encoded = encodeURIComponent(current_path);
    action.href = "/login?next=" + encoded;
    toast.appendChild(action);
    this._element = toast;
    this._container.appendChild(toast);
    return;
  }
  hide() {
    if (this._element !== null && this._element.parentNode !== null) {
      this._element.parentNode.removeChild(this._element);
    }
    this._element = null;
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/hidden-surface-notice.js
var PREFERENCES_PATH = "/account/preferences";
function path_under_route(pathname, route) {
  if (typeof route !== "string" || route.length === 0) {
    return false;
  }
  if (pathname === route) {
    return true;
  }
  const prefix = route.endsWith("/") ? route : route + "/";
  const rtnval = pathname.startsWith(prefix);
  return rtnval;
}
function match_hidden_route(pathname, hidden_routes) {
  if (Array.isArray(hidden_routes) === false) {
    return null;
  }
  for (const route of hidden_routes) {
    if (path_under_route(pathname, route) === true) {
      return route;
    }
  }
  return null;
}
function build_hidden_surface_notice(route) {
  const notice = document.createElement("div");
  notice.classList.add("alert", "alert-info", "pyc-hidden-surface-notice");
  notice.setAttribute("role", "status");
  notice.setAttribute("data-hidden-route", route);
  const text = document.createElement("span");
  text.textContent = "This area is hidden from your navigation. ";
  notice.appendChild(text);
  const link = document.createElement("a");
  link.href = PREFERENCES_PATH;
  link.textContent = "Change your preferences";
  notice.appendChild(link);
  const dismiss = document.createElement("button");
  dismiss.type = "button";
  dismiss.classList.add("btn", "btn-sm", "btn-secondary", "pyc-hidden-surface-notice__dismiss");
  dismiss.textContent = "Dismiss";
  dismiss.setAttribute("aria-label", "Dismiss hidden-surface notice");
  dismiss.addEventListener("click", () => {
    notice.remove();
  });
  notice.appendChild(dismiss);
  return notice;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/palette/palette-registry.js
var DEFAULT_PROVIDER_TIMEOUT_MS = 5e3;
var PALETTE_QUERY_MAX_LENGTH = 128;
var PaletteRegistry = class {
  _providers;
  constructor() {
    this._providers = /* @__PURE__ */ new Map();
  }
  /**
   * Register a palette provider. Duplicate ``providerId`` calls
   * are dropped with a ``console.warn`` (first wins) -- mirrors
   * the sidebar registry's collision policy.
   *
   * @param provider Descriptor.
   */
  registerProvider(provider) {
    if (provider === null || typeof provider !== "object") {
      console.warn(
        "pychestrate.ui.shell.palette_malformed_provider_registration"
      );
      return;
    }
    if (typeof provider.providerId !== "string" || provider.providerId.length === 0) {
      console.warn(
        "pychestrate.ui.shell.palette_malformed_provider_registration",
        { reason: "missing_providerId" }
      );
      return;
    }
    if (typeof provider.query !== "function") {
      console.warn(
        "pychestrate.ui.shell.palette_malformed_provider_registration",
        { reason: "missing_query", providerId: provider.providerId }
      );
      return;
    }
    if (this._providers.has(provider.providerId) === true) {
      console.warn(
        "pychestrate.ui.shell.palette_dup_provider",
        { providerId: provider.providerId }
      );
      return;
    }
    this._providers.set(provider.providerId, provider);
    return;
  }
  /**
   * Return the providers that pass the permission gate for the
   * supplied permission set. Order follows registration order.
   */
  visibleProviders(perms) {
    const visible = [];
    for (const provider of this._providers.values()) {
      const required = provider.requiredPermissions !== void 0 ? provider.requiredPermissions : [];
      if (perms.hasAll(required) === true) {
        visible.push(provider);
      }
    }
    return visible;
  }
  /**
   * Total registered provider count. Diagnostic only.
   */
  size() {
    const rtnval = this._providers.size;
    return rtnval;
  }
  /**
   * Fan-out the supplied query to every visible provider,
   * applying a per-provider timeout. Returns an array of
   * outcomes in the same order as ``visibleProviders``.
   *
   * Failures (rejections, timeouts) are reported as outcomes
   * with ``error`` set, NOT as a thrown rejection from this
   * method. Callers can therefore render partial results
   * deterministically.
   *
   * @param query Raw query string. Trimmed and capped to
   *              ``PALETTE_QUERY_MAX_LENGTH`` characters.
   * @param perms Active permission set.
   */
  async queryAll(query, perms) {
    const normalized = _normalize_query(query);
    const visible = this.visibleProviders(perms);
    const pending = [];
    for (const provider of visible) {
      pending.push(_run_provider(provider, normalized));
    }
    const settled = await Promise.all(pending);
    return settled;
  }
};
function _normalize_query(query) {
  let working = typeof query === "string" ? query : "";
  working = working.trim();
  if (working.length > PALETTE_QUERY_MAX_LENGTH) {
    working = working.slice(0, PALETTE_QUERY_MAX_LENGTH);
  }
  return working;
}
async function _run_provider(provider, query) {
  const timeout_ms = typeof provider.timeoutMs === "number" && provider.timeoutMs > 0 ? provider.timeoutMs : DEFAULT_PROVIDER_TIMEOUT_MS;
  let timer_handle = null;
  const timeout_promise = new Promise((_, reject) => {
    timer_handle = setTimeout(() => {
      reject(new Error("palette_provider_timeout"));
    }, timeout_ms);
  });
  try {
    const results = await Promise.race([
      provider.query(query),
      timeout_promise
    ]);
    if (timer_handle !== null) {
      clearTimeout(timer_handle);
    }
    const safe_results = Array.isArray(results) ? results : [];
    const outcome = {
      providerId: provider.providerId,
      providerLabel: provider.label,
      results: safe_results,
      error: null
    };
    return outcome;
  } catch (reason) {
    if (timer_handle !== null) {
      clearTimeout(timer_handle);
    }
    const outcome = {
      providerId: provider.providerId,
      providerLabel: provider.label,
      results: [],
      error: String(reason)
    };
    return outcome;
  }
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/palette/palette-dialog.js
var PALETTE_INPUT_DEBOUNCE_MS = 80;
var PaletteDialog = class {
  _registry;
  _host;
  _container;
  _input;
  _results_region;
  _status_region;
  _is_open;
  _previous_focus;
  _debounce_handle;
  _query_token;
  _flat_results;
  _active_index;
  constructor(registry, host) {
    this._registry = registry;
    this._host = host;
    this._container = null;
    this._input = null;
    this._results_region = null;
    this._status_region = null;
    this._is_open = false;
    this._previous_focus = null;
    this._debounce_handle = null;
    this._query_token = 0;
    this._flat_results = [];
    this._active_index = -1;
  }
  get isOpen() {
    const rtnval = this._is_open;
    return rtnval;
  }
  /**
   * Open the palette. No-op when already open. Builds the DOM
   * on first open and attaches it to ``document.body``.
   *
   * @param mount_target Optional override for the parent
   *                     element the dialog attaches to. Falls
   *                     back to ``document.body``.
   */
  open(mount_target = null) {
    if (this._is_open === true) {
      return;
    }
    if (this._container === null) {
      this._build_dom();
    }
    const container = this._container;
    if (container === null) {
      return;
    }
    const parent = mount_target !== null ? mount_target : document.body;
    parent.appendChild(container);
    this._is_open = true;
    this._previous_focus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (this._input !== null) {
      this._input.value = "";
      this._input.focus();
    }
    this._render_status("Search pages, projects and actions, or paste a run or build id.");
    this._host.emit("pyc-site-shell-palette-opened", {});
    if (typeof this._host.observePaletteOpened === "function") {
      this._host.observePaletteOpened();
    }
    return;
  }
  /**
   * Close the palette and restore focus to the previously
   * focused element. No-op when already closed.
   */
  close() {
    if (this._is_open === false) {
      return;
    }
    const container = this._container;
    if (container !== null && container.parentNode !== null) {
      container.parentNode.removeChild(container);
    }
    this._is_open = false;
    if (this._debounce_handle !== null) {
      clearTimeout(this._debounce_handle);
      this._debounce_handle = null;
    }
    this._flat_results = [];
    this._active_index = -1;
    const restore_target = this._previous_focus;
    this._previous_focus = null;
    if (restore_target !== null && typeof restore_target.focus === "function") {
      restore_target.focus();
    }
    this._host.emit("pyc-site-shell-palette-closed", {});
    return;
  }
  _build_dom() {
    const container = document.createElement("div");
    container.classList.add("pyc-site-shell__palette-backdrop");
    container.setAttribute("role", "presentation");
    const dialog = document.createElement("div");
    dialog.classList.add("pyc-site-shell__palette-dialog");
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    dialog.setAttribute("aria-label", "Command Palette");
    dialog.tabIndex = -1;
    const input = document.createElement("input");
    input.type = "search";
    input.classList.add("pyc-site-shell__palette-input");
    input.setAttribute("aria-label", "Search pages, projects and actions");
    input.setAttribute("autocomplete", "off");
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", "pyc-palette-results");
    input.setAttribute("spellcheck", "false");
    input.placeholder = "Type to search...";
    input.addEventListener("input", () => {
      this._on_input_changed();
    });
    dialog.appendChild(input);
    const status = document.createElement("div");
    status.classList.add("pyc-site-shell__palette-status");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    dialog.appendChild(status);
    const results = document.createElement("div");
    results.classList.add("pyc-site-shell__palette-results");
    results.setAttribute("role", "listbox");
    results.id = "pyc-palette-results";
    results.setAttribute("aria-label", "Search results");
    dialog.appendChild(results);
    dialog.addEventListener("keydown", (event) => {
      this._on_dialog_keydown(event);
    });
    container.addEventListener("mousedown", (event) => {
      if (event.target === container) {
        this.close();
      }
    });
    container.appendChild(dialog);
    this._container = container;
    this._input = input;
    this._status_region = status;
    this._results_region = results;
    return;
  }
  _on_input_changed() {
    if (this._debounce_handle !== null) {
      clearTimeout(this._debounce_handle);
    }
    this._debounce_handle = setTimeout(() => {
      this._debounce_handle = null;
      void this._run_query();
    }, PALETTE_INPUT_DEBOUNCE_MS);
    return;
  }
  async _run_query() {
    if (this._input === null || this._results_region === null) {
      return;
    }
    const raw_query = this._input.value;
    this._query_token = this._query_token + 1;
    const token = this._query_token;
    if (raw_query.trim().length === 0) {
      this._results_region.replaceChildren();
      this._flat_results = [];
      this._active_index = -1;
      this._render_status(
        "Search pages, projects and actions, or paste a run or build id."
      );
      return;
    }
    const perms = this._host.getPermissions();
    const visible_providers = this._registry.visibleProviders(perms);
    if (visible_providers.length === 0) {
      this._results_region.replaceChildren();
      this._flat_results = [];
      this._active_index = -1;
      this._render_status("Navigation search is unavailable for your account.");
      return;
    }
    this._render_status("Searching...");
    const fanout_started = typeof performance !== "undefined" ? performance.now() : 0;
    const outcomes = await this._registry.queryAll(raw_query, perms);
    const fanout_finished = typeof performance !== "undefined" ? performance.now() : 0;
    if (typeof this._host.observePaletteFanout === "function") {
      this._host.observePaletteFanout(
        (fanout_finished - fanout_started) / 1e3
      );
    }
    if (token !== this._query_token) {
      return;
    }
    this._render_outcomes(outcomes);
    return;
  }
  _render_outcomes(outcomes) {
    if (this._results_region === null) {
      return;
    }
    this._results_region.replaceChildren();
    this._flat_results = [];
    let total_results = 0;
    const any_results = outcomes.some((outcome) => outcome.error === null && outcome.results.length > 0);
    const any_error = outcomes.some((outcome) => outcome.error !== null);
    if (any_results === false && any_error === false) {
      this._active_index = -1;
      if (this._input !== null) {
        this._input.setAttribute("aria-expanded", "false");
        this._input.removeAttribute("aria-activedescendant");
      }
      this._render_status("No results.");
      return;
    }
    for (const outcome of outcomes) {
      if (any_results === true && outcome.error === null && outcome.results.length === 0) {
        continue;
      }
      const section = document.createElement("div");
      section.classList.add("pyc-site-shell__palette-group");
      section.setAttribute("role", "group");
      section.setAttribute("aria-label", outcome.providerLabel);
      const heading = document.createElement("div");
      heading.classList.add("pyc-site-shell__palette-group-label");
      heading.setAttribute("role", "presentation");
      heading.textContent = outcome.providerLabel;
      section.appendChild(heading);
      if (outcome.error !== null) {
        const notice = document.createElement("div");
        notice.classList.add("pyc-site-shell__palette-provider-error");
        notice.setAttribute("role", "presentation");
        notice.textContent = "This source is unavailable right now.";
        section.appendChild(notice);
        this._results_region.appendChild(section);
        continue;
      }
      if (outcome.results.length === 0) {
        const empty = document.createElement("div");
        empty.classList.add("pyc-site-shell__palette-empty");
        empty.textContent = "No matches.";
        section.appendChild(empty);
        this._results_region.appendChild(section);
        continue;
      }
      for (const result of outcome.results) {
        const option = document.createElement("div");
        option.classList.add("pyc-site-shell__palette-option");
        option.setAttribute("role", "option");
        option.setAttribute("data-provider-id", outcome.providerId);
        option.setAttribute("data-result-id", result.id);
        option.id = "pyc-palette-option-" + String(total_results);
        option.tabIndex = -1;
        const label = document.createElement("div");
        label.classList.add("pyc-site-shell__palette-option-label");
        label.textContent = result.label;
        option.appendChild(label);
        if (typeof result.description === "string" && result.description.length > 0) {
          const desc = document.createElement("div");
          desc.classList.add(
            "pyc-site-shell__palette-option-description"
          );
          desc.textContent = result.description;
          option.appendChild(desc);
        }
        option.addEventListener("click", () => {
          void this._activate_result(result);
        });
        section.appendChild(option);
        this._flat_results.push({
          providerId: outcome.providerId,
          result,
          element: option
        });
        total_results = total_results + 1;
      }
      this._results_region.appendChild(section);
    }
    this._active_index = this._flat_results.length > 0 ? 0 : -1;
    if (this._input !== null) {
      this._input.setAttribute("aria-expanded", this._flat_results.length > 0 ? "true" : "false");
      if (this._flat_results.length === 0) {
        this._input.removeAttribute("aria-activedescendant");
      }
    }
    this._update_active_highlight();
    if (total_results === 0) {
      this._render_status("No results.");
    } else {
      const label = total_results === 1 ? "1 result." : `${total_results} results.`;
      this._render_status(label);
    }
    return;
  }
  _render_status(text) {
    if (this._status_region !== null) {
      this._status_region.textContent = text;
    }
    return;
  }
  _update_active_highlight() {
    for (let index = 0; index < this._flat_results.length; index = index + 1) {
      const entry = this._flat_results[index];
      if (index === this._active_index) {
        entry.element.setAttribute("aria-selected", "true");
        if (this._input !== null) {
          this._input.setAttribute("aria-activedescendant", entry.element.id);
        }
        entry.element.classList.add(
          "pyc-site-shell__palette-option--active"
        );
      } else {
        entry.element.setAttribute("aria-selected", "false");
        entry.element.classList.remove(
          "pyc-site-shell__palette-option--active"
        );
      }
    }
    return;
  }
  async _activate_result(result) {
    this.close();
    if (typeof result.onActivate === "function") {
      try {
        await result.onActivate();
      } catch (reason) {
        console.warn(
          "pychestrate.ui.shell.palette_activate_failed",
          { reason: String(reason) }
        );
      }
      return;
    }
    if (typeof result.route === "string" && result.route.length > 0) {
      this._host.navigate(result.route);
    }
    return;
  }
  _on_dialog_keydown(event) {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      this.close();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (this._flat_results.length === 0) {
        return;
      }
      this._active_index = (this._active_index + 1) % this._flat_results.length;
      this._update_active_highlight();
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      if (this._flat_results.length === 0) {
        return;
      }
      const next_index = this._active_index <= 0 ? this._flat_results.length - 1 : this._active_index - 1;
      this._active_index = next_index;
      this._update_active_highlight();
      return;
    }
    if (event.key === "Enter") {
      if (this._active_index >= 0 && this._active_index < this._flat_results.length) {
        event.preventDefault();
        const active = this._flat_results[this._active_index];
        void this._activate_result(active.result);
      }
      return;
    }
    if (event.key === "Tab") {
      event.preventDefault();
      if (this._input !== null) {
        this._input.focus();
      }
      return;
    }
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/palette/navigation-provider.js
var NAVIGATION_PROVIDER_ID = "shell.navigation";
var NAVIGATION_PROVIDER_LABEL = "Navigation";
var NAVIGATION_RESULT_LIMIT = 12;
var SCORE_LABEL_PREFIX = 400;
var SCORE_LABEL_SUBSTRING = 300;
var SCORE_GROUP_SUBSTRING = 200;
var SCORE_ROUTE_SUBSTRING = 150;
var SCORE_LABEL_SUBSEQUENCE = 100;
function register_navigation_palette_provider(palette, options) {
  palette.registerProvider({
    providerId: NAVIGATION_PROVIDER_ID,
    label: NAVIGATION_PROVIDER_LABEL,
    requiredPermissions: [],
    query: async (query) => {
      const visible_sidebar = options.get_visible_sidebar();
      const candidates = _collect_candidates(visible_sidebar);
      const results = _match_candidates(candidates, query);
      return results;
    }
  });
  return;
}
function _collect_candidates(visible_sidebar) {
  const candidates = [];
  candidates.push({
    id: "shell.home",
    label: "Home",
    group_label: null,
    route: "/"
  });
  for (const entry of visible_sidebar.ungrouped) {
    candidates.push({
      id: entry.entryId,
      label: entry.label,
      group_label: null,
      route: entry.route
    });
  }
  for (const bucket of visible_sidebar.groups) {
    for (const entry of bucket.entries) {
      candidates.push({
        id: entry.entryId,
        label: entry.label,
        group_label: bucket.group.label,
        route: entry.route
      });
    }
  }
  return candidates;
}
function _match_candidates(candidates, query) {
  const normalized = typeof query === "string" ? query.trim().toLowerCase() : "";
  if (normalized.length === 0) {
    const rtnval = [];
    return rtnval;
  }
  const scored = [];
  for (const candidate of candidates) {
    const score = _score_candidate(candidate, normalized);
    if (score > 0) {
      scored.push({ candidate, score });
    }
  }
  scored.sort((left, right) => right.score - left.score);
  const results = [];
  for (const item of scored.slice(0, NAVIGATION_RESULT_LIMIT)) {
    const candidate = item.candidate;
    const description = candidate.group_label !== null ? candidate.group_label + " \u2014 " + candidate.route : candidate.route;
    results.push({
      id: candidate.id,
      label: candidate.label,
      description,
      route: candidate.route
    });
  }
  return results;
}
function _score_candidate(candidate, normalized_query) {
  const label = candidate.label.toLowerCase();
  const group_label = candidate.group_label !== null ? candidate.group_label.toLowerCase() : "";
  const route = candidate.route.toLowerCase();
  const tiebreak = Math.max(0, 50 - candidate.label.length);
  if (label.startsWith(normalized_query) === true) {
    const rtnval2 = SCORE_LABEL_PREFIX + tiebreak;
    return rtnval2;
  }
  if (label.includes(normalized_query) === true) {
    const rtnval2 = SCORE_LABEL_SUBSTRING + tiebreak;
    return rtnval2;
  }
  if (group_label.length > 0 && group_label.includes(normalized_query) === true) {
    const rtnval2 = SCORE_GROUP_SUBSTRING + tiebreak;
    return rtnval2;
  }
  if (route.includes(normalized_query) === true) {
    const rtnval2 = SCORE_ROUTE_SUBSTRING + tiebreak;
    return rtnval2;
  }
  if (_is_subsequence(normalized_query, label) === true) {
    const rtnval2 = SCORE_LABEL_SUBSEQUENCE + tiebreak;
    return rtnval2;
  }
  const rtnval = 0;
  return rtnval;
}
function _is_subsequence(needle, haystack) {
  let needle_index = 0;
  for (let haystack_index = 0; haystack_index < haystack.length; haystack_index = haystack_index + 1) {
    if (needle_index >= needle.length) {
      break;
    }
    if (haystack[haystack_index] === needle[needle_index]) {
      needle_index = needle_index + 1;
    }
  }
  const rtnval = needle_index >= needle.length;
  return rtnval;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/palette/entity-provider.js
var PROJECTS_PROVIDER_ID = "shell.projects";
var USERS_PROVIDER_ID = "shell.users";
var RECORDS_PROVIDER_ID = "shell.records";
var ACTIONS_PROVIDER_ID = "shell.actions";
var PROJECTS_URL2 = "/api/v1/projects?per_page=500";
var PROJECTS_CACHE_MS = 60 * 1e3;
var PROJECT_RESULT_LIMIT = 6;
var USERS_URL = "/api/v1/identity/users";
var USERS_PERMISSION = "system:users.read";
var USER_RESULT_LIMIT = 6;
var UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
var ACTIONS = [
  { label: "Create a project", words: "new add project", route: "/projects/create", needs: "/projects" },
  { label: "Register a device", words: "add new resource checkout check out lab", route: "/resource-pools", needs: "/resource-pools" },
  { label: "Run tests", words: "test catalog start", route: "/test-catalog", needs: "/test-catalog" },
  { label: "Trigger a build", words: "build start new", route: "/builds", needs: "/builds" },
  { label: "Define a pipeline", words: "pipeline create new", route: "/pipelines", needs: "/pipelines" },
  { label: "Create an API token", words: "token pyc cli new", route: "/account/api-tokens", needs: null },
  { label: "Preferences", words: "settings profile account", route: "/account/preferences", needs: null },
  { label: "Switch theme", words: "dark light mode appearance colour color", route: null, needs: null, callback: "toggle_theme" },
  { label: "Sign out", words: "log out logout leave", route: null, needs: null, callback: "sign_out" }
];
function normalise(text) {
  return typeof text === "string" ? text.trim().toLowerCase() : "";
}
function register_entity_palette_providers(palette, options) {
  let cached = null;
  let cached_at = 0;
  async function projects() {
    const now = Date.now();
    if (cached !== null && now - cached_at < PROJECTS_CACHE_MS) {
      return cached;
    }
    let found = [];
    try {
      const response = await fetch(PROJECTS_URL2, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.ok === true) {
        const body = await response.json();
        const items = Array.isArray(body) ? body : body !== null && Array.isArray(body.items) ? body.items : [];
        found = items.filter((item) => item !== null && typeof item === "object" && typeof item.project_id === "string");
      }
    } catch (reason) {
      found = [];
    }
    cached = found;
    cached_at = now;
    return found;
  }
  palette.registerProvider({
    providerId: PROJECTS_PROVIDER_ID,
    label: "Projects",
    requiredPermissions: [],
    query: async (query) => {
      const wanted = normalise(query);
      if (wanted.length < 2) {
        return [];
      }
      const hits = [];
      for (const project of await projects()) {
        const name = normalise(project.display_name);
        const slug = normalise(project.slug);
        let score = 0;
        if (name.startsWith(wanted) || slug.startsWith(wanted)) {
          score = 2;
        } else if (name.includes(wanted) || slug.includes(wanted)) {
          score = 1;
        }
        if (score > 0) {
          hits.push({ score, project });
        }
      }
      hits.sort((left, right) => right.score - left.score);
      return hits.slice(0, PROJECT_RESULT_LIMIT).map(({ project }) => {
        const shown = typeof project.display_name === "string" && project.display_name.length > 0 ? project.display_name : project.slug;
        const slug = typeof project.slug === "string" && project.slug.length > 0 ? project.slug : project.project_id;
        return { id: "project:" + project.project_id, label: shown, description: "Project \xB7 " + slug, route: "/projects/" + encodeURIComponent(slug) };
      });
    }
  });
  palette.registerProvider({
    providerId: USERS_PROVIDER_ID,
    label: "Users",
    requiredPermissions: [USERS_PERMISSION],
    query: async (query) => {
      const wanted = typeof query === "string" ? query.trim() : "";
      if (wanted.length < 2) {
        return [];
      }
      let items = [];
      try {
        const response = await fetch(USERS_URL + "?per_page=" + String(USER_RESULT_LIMIT) + "&q=" + encodeURIComponent(wanted), {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json" }
        });
        if (response.ok === true) {
          const body = await response.json();
          items = body !== null && Array.isArray(body.items) ? body.items : [];
        }
      } catch (reason) {
        items = [];
      }
      return items.filter((item) => item !== null && typeof item === "object" && typeof item.user_id === "string" && typeof item.login_name === "string").slice(0, USER_RESULT_LIMIT).map((user) => {
        const shown = typeof user.display_name === "string" && user.display_name.length > 0 ? user.display_name : user.login_name;
        const state = typeof user.status === "string" && user.status === "DEACTIVATED" ? " \xB7 deactivated" : "";
        return { id: "user:" + user.user_id, label: shown, description: "User \xB7 " + user.login_name + state, route: "/admin/users/" + encodeURIComponent(user.user_id) };
      });
    }
  });
  palette.registerProvider({
    providerId: RECORDS_PROVIDER_ID,
    label: "Open by id",
    requiredPermissions: [],
    query: async (query) => {
      const text = typeof query === "string" ? query.trim() : "";
      if (UUID_PATTERN.test(text) === false) {
        return [];
      }
      const id = text.toLowerCase();
      return [
        { id: "run:" + id, label: "Run " + id.split("-")[0], description: "Open the run with this id", route: "/runs/" + id },
        { id: "build:" + id, label: "Build " + id.split("-")[0], description: "Open the build with this id", route: "/builds/" + id }
      ];
    }
  });
  palette.registerProvider({
    providerId: ACTIONS_PROVIDER_ID,
    label: "Actions",
    requiredPermissions: [],
    query: async (query) => {
      const wanted = normalise(query);
      if (wanted.length === 0) {
        return [];
      }
      const reachable = typeof options.get_visible_routes === "function" ? options.get_visible_routes() : [];
      const results = [];
      for (const action of ACTIONS) {
        const haystack = normalise(action.label + " " + action.words);
        if (haystack.includes(wanted) === false) {
          continue;
        }
        if (action.needs !== null && reachable.some((route) => route === action.needs || route.startsWith(action.needs + "/")) === false) {
          continue;
        }
        const result = { id: "action:" + action.label.toLowerCase().replace(/[^a-z]+/g, "-"), label: action.label, description: "Action" };
        if (action.route !== null) {
          result.route = action.route;
        } else if (typeof options[action.callback] === "function") {
          result.onActivate = () => options[action.callback]();
        } else {
          continue;
        }
        results.push(result);
      }
      return results;
    }
  });
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/permissions/permission-set.js
var PermissionSet = class {
  _keys;
  /**
   * Construct a permission set from an iterable of permission
   * keys. Duplicates are de-duplicated by the underlying Set.
   *
   * @param keys - Iterable of permission key strings.
   */
  constructor(keys) {
    this._keys = /* @__PURE__ */ new Set();
    for (const key of keys) {
      if (typeof key === "string" && key.length > 0) {
        this._keys.add(key);
      }
    }
  }
  /**
   * Return true when the supplied permission key is present.
   *
   * @param perm - Permission key.
   */
  has(perm) {
    const rtnval = this._keys.has(perm);
    return rtnval;
  }
  /**
   * Return true when every supplied permission key is present.
   * The empty-array case returns true (vacuously satisfied).
   *
   * @param perms - Iterable of permission keys.
   */
  hasAll(perms) {
    for (const perm of perms) {
      if (this._keys.has(perm) === false) {
        return false;
      }
    }
    return true;
  }
  /**
   * Return the diff between this set and another.
   *
   * @param other - Comparison set.
   * @returns Object with `added` (keys in other but not this)
   *          and `removed` (keys in this but not other) string
   *          arrays. Both arrays are sorted for determinism.
   */
  diff(other) {
    const added = [];
    const removed = [];
    for (const key of other._keys) {
      if (this._keys.has(key) === false) {
        added.push(key);
      }
    }
    for (const key of this._keys) {
      if (other._keys.has(key) === false) {
        removed.push(key);
      }
    }
    added.sort();
    removed.sort();
    const rtnval = { added, removed };
    return rtnval;
  }
  /**
   * Return the cardinality of the underlying key set.
   */
  size() {
    const rtnval = this._keys.size;
    return rtnval;
  }
  /**
   * Return the underlying keys as a sorted array snapshot.
   * Intended for logging / diagnostics. Do NOT use as a security
   * boundary — sidebar visibility is UX only.
   */
  toSortedArray() {
    const rtnval = Array.from(this._keys).sort();
    return rtnval;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/permissions/permission-cache.js
var DEFAULT_PERMISSIONS_ENDPOINT = "/api/v1/me/permissions";
var DEFAULT_FRESHNESS_TTL_MS = 6e4;
var PermissionCache = class {
  _current;
  _degraded;
  _endpoint;
  _freshness_ttl_ms;
  _now;
  _last_success_at_ms;
  _diff_listeners;
  _fetch_failed_listeners;
  _session_401_listeners;
  _fetch_succeeded_listeners;
  _last_outcome_was_401;
  /**
   * @param endpoint Either a URL string (back-compat) or an
   *                 options object. When a string is supplied,
   *                 defaults are applied for the other fields.
   */
  constructor(endpoint) {
    let resolved_endpoint = DEFAULT_PERMISSIONS_ENDPOINT;
    let resolved_ttl_ms = DEFAULT_FRESHNESS_TTL_MS;
    let resolved_now = () => Date.now();
    if (typeof endpoint === "string") {
      resolved_endpoint = endpoint;
    } else if (endpoint !== null && typeof endpoint === "object") {
      if (typeof endpoint.endpoint === "string" && endpoint.endpoint.length > 0) {
        resolved_endpoint = endpoint.endpoint;
      }
      if (typeof endpoint.freshnessTtlMs === "number") {
        resolved_ttl_ms = endpoint.freshnessTtlMs;
      }
      if (typeof endpoint.now === "function") {
        resolved_now = endpoint.now;
      }
    }
    this._current = new PermissionSet([]);
    this._degraded = false;
    this._endpoint = resolved_endpoint;
    this._freshness_ttl_ms = resolved_ttl_ms;
    this._now = resolved_now;
    this._last_success_at_ms = null;
    this._diff_listeners = [];
    this._fetch_failed_listeners = [];
    this._session_401_listeners = [];
    this._fetch_succeeded_listeners = [];
    this._last_outcome_was_401 = false;
  }
  /**
   * Return the current snapshot.
   */
  current() {
    const rtnval = this._current;
    return rtnval;
  }
  /**
   * Return true when the most recent fetch failed.
   */
  get degraded() {
    const rtnval = this._degraded;
    return rtnval;
  }
  /**
   * Subscribe to permission-set diffs. Listener fires on every
   * ``refresh()`` whose successful fetch changed the snapshot.
   */
  onPermissionsChanged(listener) {
    this._diff_listeners.push(listener);
    return;
  }
  /**
   * Subscribe to non-401 fetch failures (network errors, 5xx).
   * The degraded banner consumes this hook.
   */
  onFetchFailed(listener) {
    this._fetch_failed_listeners.push(listener);
    return;
  }
  /**
   * Subscribe to successful fetches -- used by the degraded
   * banner to auto-dismiss on recovery.
   */
  onFetchSucceeded(listener) {
    this._fetch_succeeded_listeners.push(listener);
    return;
  }
  /**
   * Subscribe to mid-session 401 events. Fired exactly once per
   * transition from healthy to expired-session.
   */
  onSession401(listener) {
    this._session_401_listeners.push(listener);
    return;
  }
  /**
   * Force a refresh from the server. On success the new
   * `PermissionSet` becomes the current snapshot and `degraded`
   * resets to false. On failure the previous snapshot is
   * retained and `degraded` is set to true. The promise resolves
   * with the current snapshot in both cases -- callers should not
   * branch on this method's success/failure as a security check.
   *
   * When called within the freshness TTL of the previous success
   * AND ``force`` is false, the cached snapshot is returned
   * without a network call.
   *
   * @param force When true, bypass the TTL dedup. Used by the
   *              navigation hook (Requirement 4.1 requires a
   *              refetch on every full navigation).
   */
  async refresh(force = true) {
    if (force === false && this._last_success_at_ms !== null && this._now() - this._last_success_at_ms < this._freshness_ttl_ms) {
      return this._current;
    }
    try {
      const response = await fetch(this._endpoint, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      });
      if (response.status === 401) {
        this._degraded = true;
        if (this._last_outcome_was_401 === false) {
          this._last_outcome_was_401 = true;
          for (const listener of this._session_401_listeners) {
            try {
              listener();
            } catch (reason) {
              console.warn(
                "pychestrate.ui.shell.permissions_listener_failed",
                { kind: "session_401", reason: String(reason) }
              );
            }
          }
        }
        return this._current;
      }
      if (response.ok === false) {
        this._degraded = true;
        this._fire_fetch_failed(`http_${response.status}`);
        return this._current;
      }
      const payload = await response.json();
      const keys = _extract_permission_keys(payload);
      if (keys === null) {
        this._degraded = true;
        this._fire_fetch_failed("malformed_payload");
        return this._current;
      }
      const next_set = new PermissionSet(keys);
      const diff = this._current.diff(next_set);
      this._current = next_set;
      this._degraded = false;
      this._last_outcome_was_401 = false;
      this._last_success_at_ms = this._now();
      if (diff.added.length > 0 || diff.removed.length > 0) {
        for (const listener of this._diff_listeners) {
          try {
            listener(diff);
          } catch (reason) {
            console.warn(
              "pychestrate.ui.shell.permissions_listener_failed",
              { kind: "diff", reason: String(reason) }
            );
          }
        }
      }
      for (const listener of this._fetch_succeeded_listeners) {
        try {
          listener();
        } catch (reason) {
          console.warn(
            "pychestrate.ui.shell.permissions_listener_failed",
            { kind: "success", reason: String(reason) }
          );
        }
      }
      return this._current;
    } catch (reason) {
      this._degraded = true;
      console.warn(
        "pychestrate.ui.shell.permissions_fetch_failed",
        { endpoint: this._endpoint }
      );
      this._fire_fetch_failed(String(reason));
      return this._current;
    }
  }
  _fire_fetch_failed(reason) {
    for (const listener of this._fetch_failed_listeners) {
      try {
        listener({ reason });
      } catch (inner) {
        console.warn(
          "pychestrate.ui.shell.permissions_listener_failed",
          { kind: "failed", reason: String(inner) }
        );
      }
    }
    return;
  }
};
function _extract_permission_keys(payload) {
  if (Array.isArray(payload) === true) {
    const rtnval = payload.filter(
      (item) => typeof item === "string"
    );
    return rtnval;
  }
  if (payload !== null && typeof payload === "object") {
    const obj = payload;
    const candidate = obj.permissions;
    if (Array.isArray(candidate) === true) {
      const rtnval = candidate.filter(
        (item) => typeof item === "string"
      );
      return rtnval;
    }
  }
  return null;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/routing/shell-router.js
var ShellRouter = class _ShellRouter {
  _current;
  _callbacks;
  /**
   * Tracks the active route context for the shell. The
   * pychestrate site is server-rendered: the sidebar and the
   * command palette both perform full page loads, so this router
   * intentionally has no `navigateTo` / pushState path -- it only
   * parses the boot path and refreshes subscribers when the
   * browser traverses history within the same document (back /
   * forward with a bfcache restore).
   *
   * @param initial_path - Path the shell booted on; typically
   *                       `window.location.pathname`.
   */
  constructor(initial_path) {
    this._current = _ShellRouter.parse(initial_path);
    this._callbacks = [];
    window.addEventListener("popstate", () => {
      const next_context = _ShellRouter.parse(window.location.pathname);
      const previous_context = this._current;
      this._current = next_context;
      this._dispatch(next_context, previous_context);
    });
  }
  /**
   * Parse a URL path into a structured `RouteContext`. M1
   * implementation is intentionally trivial — query params are
   * lifted into the `params` map; path segments are not parsed
   * against route patterns.
   */
  static parse(path) {
    let working = path;
    const params = {};
    const query_index = path.indexOf("?");
    if (query_index >= 0) {
      working = path.slice(0, query_index);
      const query_string = path.slice(query_index + 1);
      const search_params = new URLSearchParams(query_string);
      for (const [key, value] of search_params.entries()) {
        params[key] = value;
      }
    }
    const rtnval = { path: working, params };
    return rtnval;
  }
  /**
   * Return the active route context.
   */
  current() {
    const rtnval = this._current;
    return rtnval;
  }
  /**
   * Subscribe a callback for navigation events.
   */
  onNavigate(callback) {
    this._callbacks.push(callback);
    return;
  }
  async _dispatch(next_context, previous_context) {
    for (const callback of this._callbacks) {
      try {
        await callback(next_context, previous_context);
      } catch (reason) {
        console.warn(
          "pychestrate.ui.shell.navigation_callback_failed",
          { reason: String(reason) }
        );
      }
    }
    return;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/sidebar/sidebar-registry.js
var SidebarRegistry = class {
  _groups;
  _entries;
  _entry_routes;
  _change_listeners;
  constructor() {
    this._groups = /* @__PURE__ */ new Map();
    this._entries = [];
    this._entry_routes = /* @__PURE__ */ new Set();
    this._change_listeners = [];
  }
  /**
   * Subscribe to registry mutations. The shell wires its
   * sidebar re-render through here so feature bundles that
   * register their groups / entries AFTER the shell's initial
   * boot render (a load-order race -- the shell bundle and the
   * feature bundle are independent ``<script type="module">``
   * tags) still surface in the sidebar instead of leaving the
   * shell stuck on the zero-permissions empty state.
   */
  onChange(listener) {
    this._change_listeners.push(listener);
    return;
  }
  _notify_change() {
    for (const listener of this._change_listeners) {
      try {
        listener();
      } catch (reason) {
        console.warn(
          "pychestrate.ui.shell.sidebar_change_listener_failed",
          { reason: String(reason) }
        );
      }
    }
    return;
  }
  /**
   * Register a sidebar group. Duplicate `groupId` registrations
   * are dropped with a warn (first wins).
   */
  registerGroup(group) {
    if (group === null || typeof group !== "object") {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_group_registration"
      );
      return;
    }
    if (typeof group.groupId !== "string" || group.groupId.length === 0) {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_group_registration",
        { reason: "missing_groupId" }
      );
      return;
    }
    if (this._groups.has(group.groupId) === true) {
      console.warn(
        "pychestrate.ui.shell.sidebar_dup_group",
        { groupId: group.groupId }
      );
      return;
    }
    const normalized = _normalize_group(group);
    this._groups.set(normalized.groupId, normalized);
    this._notify_change();
    return;
  }
  /**
   * Register a sidebar entry. Duplicate `route` registrations
   * are dropped with a warn (first wins, per Requirement 2.5).
   */
  registerEntry(entry) {
    if (entry === null || typeof entry !== "object") {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_entry_registration"
      );
      return;
    }
    if (typeof entry.route !== "string" || entry.route.length === 0) {
      console.warn(
        "pychestrate.ui.shell.sidebar_malformed_entry_registration",
        { reason: "missing_route" }
      );
      return;
    }
    if (this._entry_routes.has(entry.route) === true) {
      const existing = this._entries.find(
        (candidate) => candidate.route === entry.route
      );
      console.warn(
        "pychestrate.ui.shell.sidebar_dup_route",
        {
          route: entry.route,
          keptLabel: existing !== void 0 ? existing.label : null,
          droppedLabel: entry.label
        }
      );
      return;
    }
    const normalized = _normalize_entry(entry);
    this._entries.push(normalized);
    this._entry_routes.add(normalized.route);
    this._notify_change();
    return;
  }
  /**
   * Compute the visible sidebar for the supplied permission set.
   *
   * Visibility rules (Requirement 2):
   *
   * - A group is visible only when every required permission is
   *   present.
   * - An entry is visible only when (a) its required permissions
   *   are all present AND (b) if it declares a group, the group
   *   is also visible.
   * - Entries without a group are returned in `ungrouped` in
   *   registration order.
   */
  visible(perms) {
    const visible_groups = [];
    const group_by_id = /* @__PURE__ */ new Map();
    for (const group of this._groups.values()) {
      if (perms.hasAll(group.requiredPermissions) === true) {
        group_by_id.set(group.groupId, group);
        visible_groups.push({ group, entries: [] });
      }
    }
    const ungrouped = [];
    for (const entry of this._entries) {
      if (perms.hasAll(entry.requiredPermissions) === false) {
        continue;
      }
      const group_id = entry.group !== null && entry.group !== void 0 ? entry.group : null;
      if (group_id === null) {
        ungrouped.push(entry);
        continue;
      }
      if (group_by_id.has(group_id) === false) {
        continue;
      }
      for (const bucket of visible_groups) {
        if (bucket.group.groupId === group_id) {
          bucket.entries.push(entry);
          break;
        }
      }
    }
    const non_empty_groups = visible_groups.filter(
      (bucket) => bucket.entries.length > 0
    );
    const rtnval = {
      groups: non_empty_groups,
      ungrouped
    };
    return rtnval;
  }
  /**
   * Total number of visible entries — used by the shell to drive
   * the empty-state predicate (Requirement 5.1).
   */
  visibleEntryCount(perms) {
    const visible_sidebar = this.visible(perms);
    let count = visible_sidebar.ungrouped.length;
    for (const bucket of visible_sidebar.groups) {
      count = count + bucket.entries.length;
    }
    return count;
  }
};
function _normalize_group(group) {
  const rtnval = {
    groupId: group.groupId,
    label: typeof group.label === "string" ? group.label : group.groupId,
    icon: group.icon !== void 0 ? group.icon : null,
    requiredPermissions: Array.isArray(group.requiredPermissions) ? group.requiredPermissions.filter(
      (item) => typeof item === "string"
    ) : []
  };
  return rtnval;
}
function _normalize_entry(entry) {
  const rtnval = {
    entryId: typeof entry.entryId === "string" ? entry.entryId : entry.route,
    label: typeof entry.label === "string" ? entry.label : entry.route,
    route: entry.route,
    icon: entry.icon !== void 0 ? entry.icon : null,
    requiredPermissions: Array.isArray(entry.requiredPermissions) ? entry.requiredPermissions.filter(
      (item) => typeof item === "string"
    ) : [],
    group: entry.group !== void 0 ? entry.group : null,
    section: typeof entry.section === "string" ? entry.section : ""
  };
  return rtnval;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/sidebar/sidebar-keyboard.js
var TYPE_TO_JUMP_RESET_MS = 1e3;
var NAVITEM_SELECTOR = ".pyc-site-shell__sidebar-navitem";
var ENTRY_SELECTOR = ".pyc-site-shell__sidebar-entry";
var POPUP_CLASS = "pyc-site-shell__sidebar-panel";
var GROUP_BUTTON_CLASS = "pyc-site-shell__sidebar-group-btn";
function attach_sidebar_keyboard(container) {
  const state = {
    buffer: "",
    last_keystroke_at_ms: 0
  };
  const handler = (event) => {
    _on_keydown(event, container, state);
  };
  container.addEventListener("keydown", handler);
  const detach = () => {
    container.removeEventListener("keydown", handler);
  };
  return detach;
}
function _on_keydown(event, container, state) {
  const open_popup = _enclosing_open_popup(event.target);
  if (open_popup !== null) {
    _handle_popup_keydown(event, open_popup, state);
    return;
  }
  _handle_toplevel_keydown(event, container, state);
  return;
}
function _handle_toplevel_keydown(event, container, state) {
  const navitems = _collect(container, NAVITEM_SELECTOR);
  if (navitems.length === 0) {
    return;
  }
  const active_index = _resolve_active_index(navitems, event.target);
  if (event.key === "ArrowDown") {
    event.preventDefault();
    const next_index = (active_index + 1) % navitems.length;
    _move_focus(navitems, next_index);
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    const next_index = active_index <= 0 ? navitems.length - 1 : active_index - 1;
    _move_focus(navitems, next_index);
    return;
  }
  if (event.key === "Enter") {
    if (active_index >= 0 && active_index < navitems.length) {
      event.preventDefault();
      const item = navitems[active_index];
      item.click();
      if (_is_group_button(item) === true) {
        _focus_first_popup_entry(item);
      }
    }
    return;
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    if (active_index >= 0 && active_index < navitems.length) {
      const item = navitems[active_index];
      if (_is_group_button(item) === true) {
        if (item.getAttribute("aria-expanded") !== "true") {
          item.click();
        }
        _focus_first_popup_entry(item);
      }
    }
    return;
  }
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    return;
  }
  if (_is_type_to_jump_key(event) === true) {
    const match_index = _type_to_jump(navitems, event, state);
    if (match_index >= 0) {
      event.preventDefault();
      _move_focus(navitems, match_index);
    }
    return;
  }
  return;
}
function _handle_popup_keydown(event, popup, state) {
  const entries = _collect(popup, ENTRY_SELECTOR);
  if (entries.length === 0) {
    return;
  }
  const active_index = _resolve_active_index(entries, event.target);
  if (event.key === "ArrowDown") {
    event.preventDefault();
    const next_index = (active_index + 1) % entries.length;
    entries[next_index].focus();
    return;
  }
  if (event.key === "ArrowUp") {
    event.preventDefault();
    const next_index = active_index <= 0 ? entries.length - 1 : active_index - 1;
    entries[next_index].focus();
    return;
  }
  if (event.key === "Enter") {
    if (active_index >= 0 && active_index < entries.length) {
      event.preventDefault();
      entries[active_index].click();
    }
    return;
  }
  if (event.key === "ArrowLeft") {
    event.preventDefault();
    const button = popup.previousElementSibling;
    if (button instanceof HTMLElement) {
      if (button.getAttribute("aria-expanded") === "true") {
        button.click();
      }
      button.focus();
    }
    return;
  }
  if (event.key === "ArrowRight") {
    event.preventDefault();
    return;
  }
  if (_is_type_to_jump_key(event) === true) {
    const match_index = _type_to_jump(entries, event, state);
    if (match_index >= 0) {
      event.preventDefault();
      entries[match_index].focus();
    }
    return;
  }
  return;
}
function _enclosing_open_popup(target) {
  if (target instanceof HTMLElement === false) {
    return null;
  }
  let current = target;
  while (current !== null) {
    if (current.classList.contains(POPUP_CLASS) === true) {
      if (current.hidden === true) {
        return null;
      }
      return current;
    }
    current = current.parentElement;
  }
  return null;
}
function _is_group_button(element) {
  const rtnval = element.classList.contains(GROUP_BUTTON_CLASS);
  return rtnval;
}
function _focus_first_popup_entry(button) {
  const popup = button.nextElementSibling;
  if (popup instanceof HTMLElement === false) {
    return;
  }
  const popup_element = popup;
  if (popup_element.hidden === true) {
    return;
  }
  const entries = _collect(popup_element, ENTRY_SELECTOR);
  if (entries.length > 0) {
    entries[0].focus();
  }
  return;
}
function _is_type_to_jump_key(event) {
  if (event.ctrlKey === true || event.metaKey === true || event.altKey === true) {
    return false;
  }
  if (typeof event.key !== "string") {
    return false;
  }
  if (event.key.length !== 1) {
    return false;
  }
  const code = event.key.charCodeAt(0);
  if (code <= 32 || code >= 127) {
    return false;
  }
  return true;
}
function _type_to_jump(items, event, state) {
  const now_ms = Date.now();
  if (now_ms - state.last_keystroke_at_ms > TYPE_TO_JUMP_RESET_MS) {
    state.buffer = "";
  }
  state.buffer = state.buffer + event.key.toLowerCase();
  state.last_keystroke_at_ms = now_ms;
  const match_index = _find_prefix_match(items, state.buffer);
  return match_index;
}
function _collect(root, selector) {
  const node_list = root.querySelectorAll(selector);
  const rtnval = [];
  for (let index = 0; index < node_list.length; index = index + 1) {
    rtnval.push(node_list[index]);
  }
  return rtnval;
}
function _resolve_active_index(items, target) {
  if (target instanceof HTMLElement) {
    const direct_index = items.indexOf(target);
    if (direct_index >= 0) {
      return direct_index;
    }
  }
  for (let index = 0; index < items.length; index = index + 1) {
    if (items[index].getAttribute("tabindex") === "0") {
      return index;
    }
  }
  return -1;
}
function _move_focus(items, next_index) {
  for (let index = 0; index < items.length; index = index + 1) {
    const item = items[index];
    if (index === next_index) {
      item.setAttribute("tabindex", "0");
      item.focus();
    } else {
      item.setAttribute("tabindex", "-1");
    }
  }
  return;
}
function _find_prefix_match(items, prefix) {
  if (prefix.length === 0) {
    return -1;
  }
  for (let index = 0; index < items.length; index = index + 1) {
    const label = (items[index].textContent || "").trim().toLowerCase();
    if (label.startsWith(prefix) === true) {
      return index;
    }
  }
  return -1;
}
function initialize_sidebar_roving_tabindex(container) {
  const navitems = _collect(container, NAVITEM_SELECTOR);
  if (navitems.length === 0) {
    return;
  }
  let anchor_index = -1;
  for (let index = 0; index < navitems.length; index = index + 1) {
    const item = navitems[index];
    const is_active_link = item.getAttribute("aria-current") === "page";
    const is_active_group = item.classList.contains(
      "pyc-site-shell__sidebar-group-btn--active"
    );
    if (is_active_link === true || is_active_group === true) {
      anchor_index = index;
      break;
    }
  }
  if (anchor_index < 0) {
    anchor_index = 0;
  }
  for (let index = 0; index < navitems.length; index = index + 1) {
    const item = navitems[index];
    if (index === anchor_index) {
      item.setAttribute("tabindex", "0");
    } else {
      item.setAttribute("tabindex", "-1");
    }
  }
  return;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/sidebar/sidebar-renderer.js
var DEFAULT_GROUP_ICON_SVGS = {
  "Projects": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" /></svg>',
  "Orchestration": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><polygon points="6 4 20 12 6 20 6 4" /></svg>',
  "Insights": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M4 20V10" /><path d="M10 20V4" /><path d="M16 20v-7" /><path d="M22 20H2" /></svg>',
  "Fleet": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><rect x="3" y="4" width="18" height="5" rx="1" /><rect x="3" y="11" width="18" height="5" rx="1" /><rect x="3" y="18" width="18" height="3" rx="1" /><circle cx="7" cy="6.5" r="0.6" fill="currentColor" /><circle cx="7" cy="13.5" r="0.6" fill="currentColor" /></svg>',
  "Operations": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 1 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" /></svg>',
  "System": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06A1.7 1.7 0 0 0 15 19.4a1.7 1.7 0 0 0-1 1.55V21a2 2 0 1 1-4 0v-.05A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.6 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 1 1 0-4h.05A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.55V3a2 2 0 1 1 4 0v.05A1.7 1.7 0 0 0 15 4.6a1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.4 9c.34.6.94 1 1.55 1H21a2 2 0 1 1 0 4h-.05a1.7 1.7 0 0 0-1.55 1z" /></svg>',
  "Admin": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M12 2 4 5v6c0 5 3.5 9.5 8 11 4.5-1.5 8-6 8-11V5l-8-3z" /></svg>'
};
var CHEVRON_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M9 6l6 6-6 6" /></svg>';
var FALLBACK_GROUP_ICON_SVG = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4" /></svg>';
var SidebarRenderer = class {
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
    let current_section = "";
    for (const entry of entries) {
      const section = typeof entry.section === "string" ? entry.section : "";
      if (section.length > 0 && section !== current_section) {
        const heading = document.createElement("li");
        heading.classList.add("pyc-site-shell__sidebar-section");
        heading.textContent = section;
        panel_list.appendChild(heading);
      }
      current_section = section;
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
      if (typeof label === "string" && DEFAULT_GROUP_ICON_SVGS[label] !== void 0) {
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
      if (this._on_entry_clicked !== null) {
        this._on_entry_clicked(route, label);
      }
    });
    return link;
  }
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/sidebar/nav-manifest.js
var DEFAULT_NAVIGATION_ENDPOINT = "/api/v1/me/navigation";
async function fetch_nav_manifest(endpoint = DEFAULT_NAVIGATION_ENDPOINT) {
  try {
    const response = await fetch(endpoint, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" }
    });
    if (response.ok === false) {
      const rtnval2 = {
        ok: false,
        manifest: null
      };
      return rtnval2;
    }
    const payload = await response.json();
    const manifest = _coerce_manifest(payload);
    if (manifest === null) {
      const rtnval2 = {
        ok: false,
        manifest: null
      };
      return rtnval2;
    }
    const rtnval = {
      ok: true,
      manifest
    };
    return rtnval;
  } catch (reason) {
    console.warn(
      "pychestrate.ui.shell.nav_manifest_fetch_failed",
      { endpoint, reason: String(reason) }
    );
    const rtnval = {
      ok: false,
      manifest: null
    };
    return rtnval;
  }
}
function apply_nav_manifest(registry, manifest) {
  if (manifest === null || Array.isArray(manifest.groups) === false) {
    return;
  }
  for (const group of manifest.groups) {
    if (group === null || typeof group.group_id !== "string" || group.group_id.length === 0) {
      continue;
    }
    registry.registerGroup({
      groupId: group.group_id,
      label: typeof group.label === "string" ? group.label : group.group_id,
      icon: group.icon !== void 0 ? group.icon : null,
      requiredPermissions: []
    });
    if (Array.isArray(group.entries) === false) {
      continue;
    }
    for (const entry of group.entries) {
      if (entry === null || typeof entry.route !== "string" || entry.route.length === 0) {
        continue;
      }
      registry.registerEntry({
        entryId: typeof entry.entry_id === "string" ? entry.entry_id : entry.route,
        label: typeof entry.label === "string" ? entry.label : entry.route,
        route: entry.route,
        icon: entry.icon !== void 0 ? entry.icon : null,
        requiredPermissions: [],
        group: group.group_id,
        section: typeof entry.section === "string" ? entry.section : ""
      });
    }
  }
  return;
}
function _coerce_manifest(payload) {
  if (payload === null || typeof payload !== "object") {
    return null;
  }
  const candidate = payload;
  if (Array.isArray(candidate.groups) === false) {
    return null;
  }
  const rtnval = {
    groups: candidate.groups,
    ui_profile: candidate.ui_profile !== null && typeof candidate.ui_profile === "object" ? candidate.ui_profile : null
  };
  return rtnval;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/observability/metrics-beacon.js
var DEFAULT_METRICS_ENDPOINT = "/api/v1/_metrics/ui";
var DEFAULT_BUFFER_CAPACITY = 100;
var DEFAULT_FLUSH_WINDOW_MS = 3e4;
var MetricsBeacon = class {
  _endpoint;
  _buffer_capacity;
  _flush_window_ms;
  _now;
  _send_beacon;
  _buffer;
  _disabled_reason;
  _pagehide_handler;
  constructor(options = null) {
    const opts = options !== null ? options : {};
    this._endpoint = typeof opts.endpoint === "string" && opts.endpoint.length > 0 ? opts.endpoint : DEFAULT_METRICS_ENDPOINT;
    this._buffer_capacity = typeof opts.bufferCapacity === "number" && opts.bufferCapacity > 0 ? opts.bufferCapacity : DEFAULT_BUFFER_CAPACITY;
    this._flush_window_ms = typeof opts.flushWindowMs === "number" && opts.flushWindowMs > 0 ? opts.flushWindowMs : DEFAULT_FLUSH_WINDOW_MS;
    this._now = typeof opts.now === "function" ? opts.now : () => {
      if (typeof performance !== "undefined") {
        return performance.now();
      }
      return Date.now();
    };
    const provided_sender = opts.sendBeacon;
    if (typeof provided_sender === "function") {
      this._send_beacon = provided_sender;
    } else if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      const bound = (url, body) => {
        const result = navigator.sendBeacon(url, body);
        return result;
      };
      this._send_beacon = bound;
    } else {
      this._send_beacon = null;
    }
    this._buffer = [];
    this._disabled_reason = null;
    this._pagehide_handler = null;
  }
  /**
   * Wire ``pagehide`` so the buffer is flushed when the user
   * navigates away. Optional -- the shell calls this once after
   * construction. Returns a detach handle.
   */
  attachLifecycle() {
    if (typeof window === "undefined") {
      const noop = () => {
        return;
      };
      return noop;
    }
    const handler = () => {
      this.flush();
    };
    window.addEventListener("pagehide", handler);
    this._pagehide_handler = handler;
    const detach = () => {
      if (this._pagehide_handler !== null) {
        window.removeEventListener("pagehide", this._pagehide_handler);
        this._pagehide_handler = null;
      }
    };
    return detach;
  }
  /**
   * Record a histogram observation (seconds).
   *
   * @param metric Metric name (must match the design.md catalog).
   * @param seconds Observation value in seconds.
   * @param labels Optional label dictionary; values must be
   *               strings. Pass ``null`` for unlabeled metrics.
   */
  observeHistogram(metric, seconds, labels = null) {
    if (this._disabled_reason !== null) {
      return;
    }
    if (typeof metric !== "string" || metric.length === 0) {
      return;
    }
    if (typeof seconds !== "number" || Number.isFinite(seconds) === false) {
      return;
    }
    const entry = {
      metric,
      value: seconds,
      labels: labels !== null ? labels : null,
      timestamp_ms: Date.now()
    };
    this._buffer.push(entry);
    this._maybe_flush();
    return;
  }
  /**
   * Increment a counter metric by 1 (or the supplied amount).
   */
  incrementCounter(metric, labels = null, amount = 1) {
    if (this._disabled_reason !== null) {
      return;
    }
    if (typeof metric !== "string" || metric.length === 0) {
      return;
    }
    const value = typeof amount === "number" && Number.isFinite(amount) === true ? amount : 1;
    const entry = {
      metric,
      value,
      labels: labels !== null ? labels : null,
      timestamp_ms: Date.now()
    };
    this._buffer.push(entry);
    this._maybe_flush();
    return;
  }
  /**
   * Flush the current buffer to the backend. Drops the buffer
   * after the call regardless of delivery outcome -- there is
   * no retry queue.
   */
  flush() {
    if (this._buffer.length === 0) {
      return;
    }
    const batch = this._buffer;
    this._buffer = [];
    if (this._send_beacon === null) {
      return;
    }
    const payload = JSON.stringify(batch);
    try {
      const delivered = this._send_beacon(this._endpoint, payload);
      if (delivered === false) {
        this._disabled_reason = "sendBeacon_refused";
        console.warn(
          "pychestrate.ui.shell.metrics_beacon_disabled",
          { reason: this._disabled_reason }
        );
      }
    } catch (reason) {
      this._disabled_reason = "sendBeacon_threw";
      console.warn(
        "pychestrate.ui.shell.metrics_beacon_disabled",
        { reason: String(reason) }
      );
    }
    return;
  }
  /**
   * Permanently disable this beacon (e.g. after a 404 on the
   * endpoint) and drop any buffered entries.
   */
  disable(reason) {
    this._disabled_reason = reason;
    this._buffer = [];
    return;
  }
  /**
   * Diagnostic accessor for tests.
   */
  bufferLength() {
    const rtnval = this._buffer.length;
    return rtnval;
  }
  /**
   * Diagnostic accessor for tests.
   */
  get disabledReason() {
    const rtnval = this._disabled_reason;
    return rtnval;
  }
  _maybe_flush() {
    if (this._buffer.length >= this._buffer_capacity) {
      this.flush();
      return;
    }
    if (this._buffer.length > 0) {
      const oldest = this._buffer[0];
      const age_ms = Date.now() - oldest.timestamp_ms;
      if (age_ms >= this._flush_window_ms) {
        this.flush();
        return;
      }
    }
    return;
  }
};
var SHELL_METRICS = {
  TTI: "pychestrate_ui_shell_tti_seconds",
  SIDEBAR_RENDER: "pychestrate_ui_shell_sidebar_render_duration_seconds",
  PERMISSION_REFETCH: "pychestrate_ui_shell_navigation_permission_refetch_seconds",
  PALETTE_OPEN: "pychestrate_ui_shell_palette_open_duration_seconds",
  PALETTE_FANOUT: "pychestrate_ui_shell_palette_fanout_duration_seconds",
  SIDEBAR_ENTRY_CLICKED: "pychestrate_ui_shell_sidebar_entry_clicked_total"
};

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/pyc-site-shell.js
var ATTR_INITIAL_ROUTE = "initial-route";
var ATTR_PERMISSIONS_ENDPOINT = "permissions-endpoint";
var ATTR_NAVIGATION_ENDPOINT = "navigation-endpoint";
var ATTR_PALETTE_TIMEOUT_MS = "palette-timeout-ms";
var ATTR_BRAND_LABEL = "brand-label";
var NAV_BANNER_MESSAGE = "Navigation could not be loaded. The sidebar may be incomplete.";
var NAV_COLLAPSED_STORAGE_KEY = "pyc-site-shell.nav-collapsed";
var SIDEBAR_ELEMENT_ID = "pyc-site-shell-sidebar";
var SIDEBAR_NAV_LABEL = "Primary";
var DARK_SCHEME_QUERY = "(prefers-color-scheme: dark)";
var PycSiteShell = class extends HTMLElement {
  _sidebar_registry;
  _palette_registry;
  _permission_cache;
  _router;
  _sidebar_renderer;
  _main_region;
  _sidebar_region;
  _notices_region;
  _palette_dialog;
  _degraded_banner;
  _nav_degraded_banner;
  _session_toast;
  _global_keydown;
  _global_session_401;
  _ready;
  _metrics;
  _metrics_lifecycle_detach;
  _boot_started_perf_now;
  _palette_open_keydown_perf_now;
  _navigation_endpoint;
  _nav_manifest_loaded;
  _nav_manifest_failed;
  _nav_provider_registered;
  _layout;
  _color_scheme_query;
  _color_scheme_listener;
  static observedAttributes = [
    ATTR_INITIAL_ROUTE,
    ATTR_PERMISSIONS_ENDPOINT,
    ATTR_NAVIGATION_ENDPOINT,
    ATTR_PALETTE_TIMEOUT_MS,
    "aria-label",
    ATTR_BRAND_LABEL
  ];
  constructor() {
    super();
    this._sidebar_registry = new SidebarRegistry();
    this._palette_registry = new PaletteRegistry();
    const endpoint = this.getAttribute(ATTR_PERMISSIONS_ENDPOINT);
    const resolved_endpoint = endpoint !== null && endpoint.length > 0 ? endpoint : DEFAULT_PERMISSIONS_ENDPOINT;
    this._permission_cache = new PermissionCache(resolved_endpoint);
    const nav_endpoint = this.getAttribute(ATTR_NAVIGATION_ENDPOINT);
    this._navigation_endpoint = nav_endpoint !== null && nav_endpoint.length > 0 ? nav_endpoint : DEFAULT_NAVIGATION_ENDPOINT;
    this._nav_manifest_loaded = false;
    this._nav_manifest_failed = false;
    this._nav_provider_registered = false;
    this._layout = null;
    this._color_scheme_query = null;
    this._color_scheme_listener = null;
    this._router = null;
    this._sidebar_renderer = null;
    this._main_region = null;
    this._sidebar_region = null;
    this._notices_region = null;
    this._palette_dialog = null;
    this._degraded_banner = null;
    this._nav_degraded_banner = null;
    this._session_toast = null;
    this._global_keydown = null;
    this._global_session_401 = null;
    this._ready = false;
    this._metrics = new MetricsBeacon();
    this._metrics_lifecycle_detach = null;
    this._boot_started_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
    this._palette_open_keydown_perf_now = null;
  }
  /**
   * Diagnostic accessor for tests + bench harness -- returns the
   * metrics beacon instance the shell uses. Not part of the
   * long-term public API.
   */
  get metrics() {
    const rtnval = this._metrics;
    return rtnval;
  }
  get sidebar() {
    const rtnval = this._sidebar_registry;
    return rtnval;
  }
  get palette() {
    const rtnval = this._palette_registry;
    return rtnval;
  }
  get permissions() {
    const rtnval = this._permission_cache;
    return rtnval;
  }
  connectedCallback() {
    _apply_theme_preference(_read_stored_theme());
    this._wire_color_scheme_listener();
    this._install_skip_link();
    this._install_sortable_header_keys();
    install_confirm_delegate(document);
    install_reveal_toggle(document);
    install_log_viewer(document);
    install_live_region(document);
    install_chip_tone();
    this._boot_started_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
    this._metrics_lifecycle_detach = this._metrics.attachLifecycle();
    this._render_skeleton();
    this._wire_permission_listeners();
    this._wire_global_keydown();
    this._wire_global_session_401();
    this._install_fetch_session_watch();
    this._wire_window_registry();
    queueMicrotask(() => {
      this._boot().catch((reason) => {
        console.warn(
          "pychestrate.ui.shell.boot_failed",
          { reason: String(reason) }
        );
      });
    });
    return;
  }
  disconnectedCallback() {
    if (this._metrics_lifecycle_detach !== null) {
      this._metrics_lifecycle_detach();
      this._metrics_lifecycle_detach = null;
    }
    this._metrics.flush();
    if (this._global_keydown !== null) {
      window.removeEventListener("keydown", this._global_keydown);
      this._global_keydown = null;
    }
    if (this._global_session_401 !== null) {
      window.removeEventListener(
        "pyc-session-401",
        this._global_session_401
      );
      this._global_session_401 = null;
    }
    if (this._color_scheme_query !== null && this._color_scheme_listener !== null) {
      this._color_scheme_query.removeEventListener(
        "change",
        this._color_scheme_listener
      );
      this._color_scheme_query = null;
      this._color_scheme_listener = null;
    }
    return;
  }
  /**
   * Public hook -- open the command palette. Exposed so feature
   * bundles or tests can trigger the palette without simulating
   * a keystroke.
   */
  openPalette() {
    if (this._palette_open_keydown_perf_now === null) {
      this._palette_open_keydown_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
    }
    if (this._palette_dialog !== null) {
      this._palette_dialog.open();
    }
    return;
  }
  /**
   * Public hook -- close the command palette.
   */
  closePalette() {
    if (this._palette_dialog !== null) {
      this._palette_dialog.close();
    }
    return;
  }
  _render_skeleton() {
    const initial_route_attr = this.getAttribute(ATTR_INITIAL_ROUTE);
    const initial_path = initial_route_attr !== null && initial_route_attr.length > 0 ? initial_route_attr : window.location.pathname;
    const preserved_main_content = Array.from(this.childNodes).filter(
      (node) => {
        if (node.nodeType !== Node.ELEMENT_NODE) {
          return node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 0;
        }
        const element = node;
        if (element.tagName === "MJ-APP-SHELL") {
          return false;
        }
        return true;
      }
    );
    this.replaceChildren();
    const layout = document.createElement("mj-app-shell");
    layout.classList.add("pyc-site-shell__layout");
    const nav_collapsed_preference = _read_nav_collapsed_preference();
    const nav_open_initial = nav_collapsed_preference === false;
    if (nav_open_initial === true) {
      layout.setAttribute("nav-open", "");
    }
    layout.addEventListener("mj-shell-nav-toggle", (event) => {
      if (event.target !== layout) {
        return;
      }
      const toggle_button = this.querySelector(".pyc-site-shell__nav-toggle");
      if (toggle_button !== null) {
        toggle_button.setAttribute(
          "aria-expanded",
          layout.hasAttribute("nav-open") === true ? "true" : "false"
        );
      }
    });
    this._layout = layout;
    const brand_attr = this.getAttribute(ATTR_BRAND_LABEL);
    const is_mac_platform = typeof navigator !== "undefined" && typeof navigator.platform === "string" && navigator.platform.toLowerCase().indexOf("mac") >= 0;
    const header = build_header({
      brand_label: brand_attr !== null && brand_attr.length > 0 ? brand_attr : "Pychestrate",
      user_display_name: this._read_optional_attribute("user-display-name"),
      user_login_name: this._read_optional_attribute("user-login-name"),
      csrf_token: this._read_optional_attribute("csrf-token"),
      service_version: this._read_optional_attribute("service-version"),
      user_guide_url: this._read_optional_attribute("user-guide-url"),
      on_theme_toggle: () => {
        this._toggle_theme();
      },
      current_theme: _read_effective_theme(),
      nav_open_initial,
      nav_controls_id: SIDEBAR_ELEMENT_ID,
      on_nav_toggle: () => {
        this._toggle_sidebar();
      },
      palette_shortcut_label: is_mac_platform === true ? "\u2318K" : "Ctrl+K",
      on_palette_hint_activate: () => {
        this.openPalette();
      }
    });
    layout.appendChild(header);
    const sidebar = document.createElement("mj-side-nav");
    sidebar.setAttribute("slot", "nav");
    sidebar.setAttribute("nav-label", SIDEBAR_NAV_LABEL);
    sidebar.id = SIDEBAR_ELEMENT_ID;
    sidebar.classList.add("pyc-site-shell__sidebar");
    layout.appendChild(sidebar);
    this._sidebar_region = sidebar;
    const flash_extraction = extract_flash_messages(preserved_main_content);
    const notices = document.createElement("div");
    notices.setAttribute("slot", "main");
    notices.classList.add("pyc-site-shell__notices");
    for (const flash of flash_extraction.flashes) {
      const notice = build_flash_notice(flash);
      notices.appendChild(notice);
    }
    layout.appendChild(notices);
    this._notices_region = notices;
    const main = document.createElement("main");
    main.setAttribute("slot", "main");
    main.classList.add("pyc-site-shell__main");
    main.id = "pyc-main-content";
    main.setAttribute("tabindex", "-1");
    for (const node of flash_extraction.remaining_nodes) {
      main.appendChild(node);
    }
    layout.appendChild(main);
    this._main_region = main;
    this.appendChild(layout);
    this._degraded_banner = new DegradedBanner(main);
    this._nav_degraded_banner = new DegradedBanner(
      main,
      {
        message: NAV_BANNER_MESSAGE,
        action_label: "Retry",
        on_action: () => {
          void this._retry_nav_manifest();
        }
      }
    );
    this._session_toast = new SessionExpiredToast(main);
    this._palette_dialog = new PaletteDialog(
      this._palette_registry,
      {
        getPermissions: () => this._permission_cache.current(),
        navigate: (route) => {
          window.location.assign(route);
        },
        emit: (event_name, detail) => {
          this._emit(event_name, detail);
        },
        observePaletteOpened: () => {
          if (this._palette_open_keydown_perf_now !== null) {
            const now_value = typeof performance !== "undefined" ? performance.now() : 0;
            const seconds = (now_value - this._palette_open_keydown_perf_now) / 1e3;
            this._palette_open_keydown_perf_now = null;
            this._metrics.observeHistogram(
              SHELL_METRICS.PALETTE_OPEN,
              seconds
            );
          }
        },
        observePaletteFanout: (seconds) => {
          this._metrics.observeHistogram(
            SHELL_METRICS.PALETTE_FANOUT,
            seconds
          );
        }
      }
    );
    this._router = new ShellRouter(initial_path);
    if (this._nav_provider_registered === false) {
      register_navigation_palette_provider(
        this._palette_registry,
        {
          get_visible_sidebar: () => this._sidebar_registry.visible(
            this._permission_cache.current()
          )
        }
      );
      register_entity_palette_providers(
        this._palette_registry,
        {
          get_visible_routes: () => {
            const visible = this._sidebar_registry.visible(this._permission_cache.current());
            const routes = visible.ungrouped.map((entry) => entry.route);
            for (const bucket of visible.groups) {
              for (const entry of bucket.entries) {
                routes.push(entry.route);
              }
            }
            return routes;
          },
          toggle_theme: () => this._toggle_theme(),
          sign_out: () => this._sign_out()
        }
      );
      this._nav_provider_registered = true;
    }
    this._sidebar_renderer = new SidebarRenderer(
      sidebar,
      (entry_route, entry_label) => {
        this._emit(
          "pyc-site-shell-sidebar-clicked",
          {
            entryRoute: entry_route,
            entryLabel: entry_label
          }
        );
        this._metrics.incrementCounter(
          SHELL_METRICS.SIDEBAR_ENTRY_CLICKED,
          { entry_route }
        );
      }
    );
    this._router.onNavigate(async (next_ctx, prev_ctx) => {
      const refetch_started = typeof performance !== "undefined" ? performance.now() : 0;
      await this._permission_cache.refresh(true);
      const refetch_finished = typeof performance !== "undefined" ? performance.now() : 0;
      this._metrics.observeHistogram(
        SHELL_METRICS.PERMISSION_REFETCH,
        (refetch_finished - refetch_started) / 1e3
      );
      this._render_sidebar_and_empty_state();
      this._emit(
        "pyc-site-shell-navigated",
        {
          from: prev_ctx !== null ? prev_ctx.path : null,
          to: next_ctx.path
        }
      );
    });
    return;
  }
  _wire_permission_listeners() {
    this._permission_cache.onPermissionsChanged((diff) => {
      this._emit(
        "pyc-site-shell-permissions-changed",
        { added: diff.added, removed: diff.removed }
      );
      this._render_sidebar_and_empty_state();
    });
    this._permission_cache.onFetchFailed(() => {
      if (this._degraded_banner !== null) {
        this._degraded_banner.show();
      }
      this._emit_window_event(
        "pyc-permissions-fetch-failed",
        {}
      );
    });
    this._permission_cache.onFetchSucceeded(() => {
      if (this._degraded_banner !== null) {
        this._degraded_banner.hide();
      }
    });
    this._permission_cache.onSession401(() => {
      this._emit_window_event("pyc-session-401", {});
    });
    return;
  }
  _wire_global_keydown() {
    const handler = (event) => {
      if (event.defaultPrevented === true) {
        return;
      }
      const is_palette_combo = (event.ctrlKey === true || event.metaKey === true) && event.key.toLowerCase() === "k";
      if (is_palette_combo === true) {
        event.preventDefault();
        this._palette_open_keydown_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
        this.openPalette();
      }
    };
    window.addEventListener("keydown", handler);
    this._global_keydown = handler;
    return;
  }
  /**
   * Every bundle view calls the REST API with fetch, and only some of them
   * turned a 401 into the shell's "session expired" notice; creating a
   * secret after the session ended said "Failed to create the secret. Try
   * again." (XC-12). One wrapper on fetch, installed once by the shell,
   * announces `pyc-session-401` whenever a request to this site's own /api/
   * is refused with 401, whichever view made it, and hands the response back
   * unchanged so the view still shows its own message as well.
   */
  _install_fetch_session_watch() {
    if (typeof window.fetch !== "function" || window.fetch.__pycSessionWatch === true) {
      return;
    }
    const original = window.fetch.bind(window);
    const watched = async (input, init) => {
      const response = await original(input, init);
      if (response.status === 401) {
        try {
          const target = new URL(typeof input === "string" ? input : input.url, window.location.href);
          if (target.origin === window.location.origin && target.pathname.startsWith("/api/") === true) {
            window.dispatchEvent(new CustomEvent("pyc-session-401", { bubbles: false, detail: {} }));
          }
        } catch (error) {
        }
      }
      return response;
    };
    watched.__pycSessionWatch = true;
    window.fetch = watched;
    return;
  }
  _wire_global_session_401() {
    const handler = () => {
      if (this._session_toast !== null) {
        this._session_toast.show();
      }
    };
    window.addEventListener("pyc-session-401", handler);
    this._global_session_401 = handler;
    return;
  }
  _wire_window_registry() {
    const global_target = window;
    const handle = {
      sidebar: this._sidebar_registry,
      palette: this._palette_registry,
      element: this
    };
    global_target.pychestrateShell = handle;
    this._sidebar_registry.onChange(() => {
      this._render_sidebar_and_empty_state();
    });
    return;
  }
  /**
   * Fetch the central navigation manifest and seed the sidebar
   * registry from it. The manifest is the authoritative source
   * of truth for sidebar navigation -- it carries every group /
   * entry the calling session may see, independent of which
   * feature bundle happens to be loaded for the current route.
   *
   * Seeding the manifest is what makes the sidebar complete on
   * the bare ``/`` route (which loads no feature bundle at
   * all). Idempotent -- a second call is a no-op once the
   * manifest has been applied, so the Retry control can call it
   * again freely. A fetch failure is non-fatal but no longer
   * silent: the shell shows the navigation degraded banner (with
   * a Retry action) and ``_render_sidebar_and_empty_state``
   * paints an explanatory state into the sidebar region while
   * the registry has nothing to show.
   */
  async _load_nav_manifest() {
    if (this._nav_manifest_loaded === true) {
      return;
    }
    const result = await fetch_nav_manifest(this._navigation_endpoint);
    if (result.ok === true && result.manifest !== null) {
      apply_nav_manifest(this._sidebar_registry, result.manifest);
      this._show_hidden_surface_notice(result.manifest.ui_profile);
      this._nav_manifest_loaded = true;
      this._nav_manifest_failed = false;
      if (this._nav_degraded_banner !== null) {
        this._nav_degraded_banner.hide();
      }
    } else {
      this._nav_manifest_failed = true;
      if (this._nav_degraded_banner !== null) {
        this._nav_degraded_banner.show();
      }
    }
    return;
  }
  /**
   * Retry handler for the navigation degraded banner and the
   * sidebar failure state. Refetches the manifest; on success
   * re-renders the sidebar, updates the document title, and
   * paints the home / not-found landing state the failed boot
   * could not produce.
   */
  /**
   * 9-ui-profiles: when the current location belongs to a surface the
   * caller has hidden, show a dismissible notice pointing at the
   * preferences page. Idempotent per page load.
   */
  _show_hidden_surface_notice(ui_profile) {
    if (ui_profile === null || ui_profile === void 0) {
      return;
    }
    if (this._notices_region === null || this._notices_region === void 0) {
      return;
    }
    if (this._notices_region.querySelector(".pyc-hidden-surface-notice") !== null) {
      return;
    }
    const pathname = window.location.pathname;
    const route = match_hidden_route(pathname, ui_profile.hidden_routes);
    if (route === null) {
      return;
    }
    this._notices_region.appendChild(build_hidden_surface_notice(route));
    return;
  }
  async _retry_nav_manifest() {
    await this._load_nav_manifest();
    this._render_sidebar_and_empty_state();
    if (this._nav_manifest_loaded === true) {
      this._update_document_title();
      this._schedule_landing_state_check();
    }
    return;
  }
  async _boot() {
    await Promise.all([
      this._permission_cache.refresh(true),
      this._load_nav_manifest()
    ]);
    this._render_sidebar_and_empty_state();
    this._update_document_title();
    this._ready = true;
    const ready_perf_now = typeof performance !== "undefined" ? performance.now() : 0;
    const tti_seconds = (ready_perf_now - this._boot_started_perf_now) / 1e3;
    this._metrics.observeHistogram(SHELL_METRICS.TTI, tti_seconds);
    this._metrics.flush();
    this._emit(
      "pyc-site-shell-ready",
      {
        visibleEntryCount: this._sidebar_registry.visibleEntryCount(
          this._permission_cache.current()
        ),
        degraded: this._permission_cache.degraded
      }
    );
    this._schedule_landing_state_check();
    return;
  }
  /**
   * Schedule the home / not-found decision for the next frame.
   * Bundles mount synchronously (at module load or during the
   * ready-event dispatch), so by the time the frame callback
   * runs, an empty main region deterministically means no bundle
   * claimed the route.
   */
  _schedule_landing_state_check() {
    const schedule3 = typeof requestAnimationFrame === "function" ? requestAnimationFrame : (callback) => setTimeout(callback, 0);
    schedule3(() => {
      this._apply_landing_state();
    });
    return;
  }
  /**
   * Render the shell-owned landing state for routes no feature
   * bundle (and no server-rendered fragment) claimed: the home
   * view on the bare "/" route, the "Page not found" view on any
   * other unclaimed route. Never fires while the nav manifest is
   * unloaded (the degraded path owns that messaging), never
   * clobbers a mounted bundle, and leaves the no-access empty
   * state in place for zero-permission accounts. Pages served by
   * the legacy blueprints either inline a fragment (preserved
   * into the main region) or never load the shell document at
   * all, so neither can trip this.
   */
  _apply_landing_state() {
    if (this._main_region === null) {
      return;
    }
    if (this._nav_manifest_loaded === false) {
      return;
    }
    const perms = this._permission_cache.current();
    const visible_entry_count = this._sidebar_registry.visibleEntryCount(
      perms
    );
    if (visible_entry_count === 0) {
      return;
    }
    const previous_landing = this._main_region.querySelectorAll(
      ".pyc-site-shell__home, .pyc-site-shell__not-found"
    );
    if (_main_region_has_route_content(this._main_region) === true) {
      for (const stale of Array.from(previous_landing)) {
        stale.remove();
      }
      return;
    }
    for (const stale of Array.from(previous_landing)) {
      stale.remove();
    }
    const path = this._router !== null ? this._router.current().path : window.location.pathname;
    const brand_attr = this.getAttribute(ATTR_BRAND_LABEL);
    const brand_label = brand_attr !== null && brand_attr.length > 0 ? brand_attr : "Pychestrate";
    const visible_sidebar = this._sidebar_registry.visible(perms);
    if (path === "/") {
      const home_view = build_home_view({
        brand_label,
        visible_sidebar
      });
      this._main_region.appendChild(home_view);
      this._emit("pyc-site-shell-home-rendered", {});
    } else {
      const not_found_view = build_not_found_view({
        path,
        visible_sidebar
      });
      this._main_region.appendChild(not_found_view);
      document.title = "Page not found \xB7 " + brand_label;
      this._emit(
        "pyc-site-shell-not-found-rendered",
        { path }
      );
    }
    return;
  }
  /**
   * Reflect the active navigation entry into the browser tab
   * title as "<entry label> · <brand>", picked by longest route
   * prefix so "/admin/feature-flags" wins over "/admin". When no
   * entry matches, the server-rendered title is left untouched.
   */
  _update_document_title() {
    const current_brand = this.getAttribute(ATTR_BRAND_LABEL);
    const brand_only = current_brand !== null && current_brand.length > 0 ? current_brand : "Pychestrate";
    if (typeof document.title === "string" && document.title.length > 0 && document.title !== brand_only) {
      return;
    }
    if (this._nav_manifest_loaded === false) {
      return;
    }
    const path = this._router !== null ? this._router.current().path : window.location.pathname;
    const perms = this._permission_cache.current();
    const visible_sidebar = this._sidebar_registry.visible(perms);
    const all_entries = [];
    for (const entry of visible_sidebar.ungrouped) {
      all_entries.push(entry);
    }
    for (const bucket of visible_sidebar.groups) {
      for (const entry of bucket.entries) {
        all_entries.push(entry);
      }
    }
    let best_entry = null;
    for (const entry of all_entries) {
      const route = entry.route;
      const is_match = path === route || path.startsWith(route.endsWith("/") === true ? route : route + "/") === true;
      if (is_match === false) {
        continue;
      }
      if (best_entry === null || route.length > best_entry.route.length) {
        best_entry = entry;
      }
    }
    if (best_entry === null) {
      return;
    }
    const brand_attr = this.getAttribute(ATTR_BRAND_LABEL);
    const brand_label = brand_attr !== null && brand_attr.length > 0 ? brand_attr : "Pychestrate";
    document.title = best_entry.label + " \xB7 " + brand_label;
    return;
  }
  /**
   * Toggle the sidebar nav track open / collapsed and persist
   * the choice. <mj-app-shell> owns the actual collapse (the
   * nav-open attribute drives its grid track width and its
   * overlay behavior on narrow viewports).
   */
  /**
   * The vendored <mj-data-table> sorts a column only when its header cell is
   * clicked: its keyboard handling covers the arrows, Home, End and Escape,
   * so Enter and Space on a focused header did nothing and a keyboard user
   * could not sort (ORC-24). One document-level handler gives every table in
   * every bundle the standard behaviour: Enter or Space on a focused
   * sortable header cell does what a click does. It looks through the
   * table's shadow root with the event's composed path.
   */
  _install_sortable_header_keys() {
    if (document.documentElement.hasAttribute("data-pyc-sort-keys") === true) {
      return;
    }
    document.documentElement.setAttribute("data-pyc-sort-keys", "");
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      for (const node of path) {
        if (node instanceof HTMLElement && node.classList.contains("header-cell") === true) {
          if (node.getAttribute("data-sortable") === "true") {
            event.preventDefault();
            node.click();
          }
          return;
        }
      }
    });
    return;
  }
  _install_skip_link() {
    if (document.querySelector(".pyc-site-shell__skip-link") !== null) {
      return;
    }
    const link = document.createElement("a");
    link.href = "#pyc-main-content";
    link.classList.add("pyc-site-shell__skip-link");
    link.textContent = "Skip to main content";
    link.addEventListener("click", (event) => {
      const main = document.querySelector(".pyc-site-shell__main");
      if (main === null) {
        return;
      }
      event.preventDefault();
      if (main.id.length === 0) {
        main.id = "pyc-main-content";
      }
      main.setAttribute("tabindex", "-1");
      main.focus();
    });
    document.body.insertBefore(link, document.body.firstChild);
    return;
  }
  /**
   * Flip between the light and dark theme, starting from what is
   * on screen now -- the stored choice, or the OS preference when
   * nothing is stored -- so the first click after an OS-driven
   * load always changes the theme.
   */
  _toggle_theme() {
    const current = _read_effective_theme();
    const next = current === "dark" ? "light" : "dark";
    _apply_theme_preference(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch (error) {
    }
    this._sync_theme_control();
    return;
  }
  /*
   * Sign out the way the account menu does: a POST with the CSRF token, or the
   * confirmation page when the document carries none.
   */
  _sign_out() {
    const csrf_token = this._read_optional_attribute("csrf-token");
    if (csrf_token === null) {
      window.location.assign("/logout");
      return;
    }
    const form = document.createElement("form");
    form.method = "post";
    form.action = "/logout";
    form.hidden = true;
    const token_input = document.createElement("input");
    token_input.type = "hidden";
    token_input.name = "csrf_token";
    token_input.value = csrf_token;
    form.appendChild(token_input);
    document.body.appendChild(form);
    form.submit();
    return;
  }
  _sync_theme_control() {
    const button = this.querySelector(".pyc-site-shell__theme-toggle");
    if (button !== null) {
      update_theme_toggle(button, _read_effective_theme());
    }
    return;
  }
  /**
   * While no theme is stored the page follows the OS preference;
   * keep the theme control's label right when the OS flips.
   */
  _wire_color_scheme_listener() {
    if (this._color_scheme_listener !== null || typeof window.matchMedia !== "function") {
      return;
    }
    const query = window.matchMedia(DARK_SCHEME_QUERY);
    if (typeof query.addEventListener !== "function") {
      return;
    }
    const listener = () => {
      this._sync_theme_control();
    };
    query.addEventListener("change", listener);
    this._color_scheme_query = query;
    this._color_scheme_listener = listener;
    return;
  }
  _read_optional_attribute(name) {
    const value = this.getAttribute(name);
    if (value === null || value.length === 0) {
      return null;
    }
    return value;
  }
  _toggle_sidebar() {
    const layout = this._layout;
    if (layout === null) {
      return;
    }
    const next_open = layout.hasAttribute("nav-open") === false;
    const is_overlay = layout.getAttribute("nav-mode") === "overlay";
    if (next_open === true) {
      layout.setAttribute("nav-open", "");
    } else {
      layout.removeAttribute("nav-open");
    }
    if (is_overlay === false) {
      _write_nav_collapsed_preference(next_open === false);
    }
    const toggle_button = this.querySelector(
      ".pyc-site-shell__nav-toggle"
    );
    if (toggle_button !== null) {
      toggle_button.setAttribute(
        "aria-expanded",
        layout.hasAttribute("nav-open") === true ? "true" : "false"
      );
    }
    return;
  }
  _render_sidebar_and_empty_state() {
    const perms = this._permission_cache.current();
    const active_path = this._router !== null ? this._router.current().path : window.location.pathname;
    const render_started = typeof performance !== "undefined" ? performance.now() : 0;
    if (this._sidebar_renderer !== null && this._sidebar_region !== null) {
      this._sidebar_renderer.render(
        this._sidebar_registry,
        perms,
        active_path
      );
    }
    if (this._nav_manifest_failed === true && this._nav_manifest_loaded === false && this._sidebar_region !== null && this._sidebar_registry.visibleEntryCount(perms) === 0) {
      const failure_state = _build_sidebar_failure_state(() => {
        void this._retry_nav_manifest();
      });
      this._sidebar_region.appendChild(failure_state);
    }
    const render_finished = typeof performance !== "undefined" ? performance.now() : 0;
    this._metrics.observeHistogram(
      SHELL_METRICS.SIDEBAR_RENDER,
      (render_finished - render_started) / 1e3
    );
    const visible_entry_count = this._sidebar_registry.visibleEntryCount(
      perms
    );
    const perms_loaded = this._permission_cache !== null && this._permission_cache._last_success_at_ms !== null;
    const manifest_loaded = this._nav_manifest_loaded === true;
    if (this._main_region === null) {
      return;
    }
    const existing_empty_state = this._main_region.querySelector(
      ".pyc-site-shell__empty-state"
    );
    if (visible_entry_count === 0 && perms_loaded === true && manifest_loaded === true) {
      const preserved = [];
      for (const child of Array.from(this._main_region.children)) {
        if (child.classList.contains(
          "pyc-site-shell__degraded-banner"
        ) === true || child.classList.contains(
          "pyc-site-shell__session-toast"
        ) === true) {
          preserved.push(child);
        }
      }
      this._main_region.replaceChildren(...preserved, build_empty_state({
        admin_contact: this._read_optional_attribute("admin-contact"),
        user_login_name: this._read_optional_attribute("user-login-name")
      }));
      this._emit(
        "pyc-site-shell-empty-state-rendered",
        {}
      );
    } else if (existing_empty_state !== null) {
      existing_empty_state.remove();
    }
    return;
  }
  _emit(event_name, detail) {
    this.dispatchEvent(
      new CustomEvent(event_name, {
        bubbles: true,
        composed: true,
        detail
      })
    );
    return;
  }
  _emit_window_event(event_name, detail) {
    window.dispatchEvent(
      new CustomEvent(event_name, {
        bubbles: false,
        detail
      })
    );
    return;
  }
  get isReady() {
    const rtnval = this._ready;
    return rtnval;
  }
  /**
   * Test/diagnostic helper -- returns the current permission set.
   * Not part of the long-term public API surface (which goes
   * through DOM CustomEvents).
   */
  currentPermissions() {
    const rtnval = this._permission_cache.current();
    return rtnval;
  }
};
var SHELL_CHROME_CLASSES = [
  "pyc-site-shell__degraded-banner",
  "pyc-site-shell__session-toast",
  "pyc-site-shell__empty-state",
  "pyc-site-shell__home",
  "pyc-site-shell__not-found"
];
function _main_region_has_route_content(main_region) {
  for (const node of Array.from(main_region.childNodes)) {
    if (node.nodeType === Node.TEXT_NODE) {
      if (node.textContent.trim().length > 0) {
        return true;
      }
      continue;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) {
      continue;
    }
    const element = node;
    let is_shell_chrome = false;
    for (const chrome_class of SHELL_CHROME_CLASSES) {
      if (element.classList.contains(chrome_class) === true) {
        is_shell_chrome = true;
        break;
      }
    }
    if (is_shell_chrome === false) {
      return true;
    }
  }
  return false;
}
function _build_sidebar_failure_state(on_retry) {
  const panel = document.createElement("div");
  panel.classList.add("pyc-site-shell__sidebar-failure");
  panel.setAttribute("role", "status");
  const message = document.createElement("p");
  message.classList.add("pyc-site-shell__sidebar-failure-message");
  message.textContent = "Navigation could not be loaded.";
  panel.appendChild(message);
  const retry_button = document.createElement("mj-button");
  retry_button.setAttribute("type", "button");
  retry_button.setAttribute("variant", "secondary");
  retry_button.setAttribute("size", "sm");
  retry_button.classList.add("pyc-site-shell__sidebar-failure-retry");
  retry_button.textContent = "Retry";
  retry_button.addEventListener("click", () => {
    on_retry();
  });
  panel.appendChild(retry_button);
  return panel;
}
var THEME_STORAGE_KEY = "pychestrate.ui.theme";
function _read_stored_theme() {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "dark" || stored === "light") {
      return stored;
    }
  } catch (error) {
  }
  return null;
}
function _read_effective_theme() {
  const stored = _read_stored_theme();
  if (stored !== null) {
    return stored;
  }
  if (typeof window.matchMedia === "function" && window.matchMedia(DARK_SCHEME_QUERY).matches) {
    return "dark";
  }
  return "light";
}
function _apply_theme_preference(theme) {
  if (theme === "dark" || theme === "light") {
    document.documentElement.setAttribute("data-theme", theme);
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  return;
}
function _read_nav_collapsed_preference() {
  let rtnval = false;
  try {
    const stored = window.localStorage.getItem(
      NAV_COLLAPSED_STORAGE_KEY
    );
    rtnval = stored === "true";
  } catch (reason) {
    rtnval = false;
  }
  return rtnval;
}
function _write_nav_collapsed_preference(collapsed) {
  try {
    window.localStorage.setItem(
      NAV_COLLAPSED_STORAGE_KEY,
      collapsed === true ? "true" : "false"
    );
  } catch (reason) {
  }
  return;
}

// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/index.entry.js
var TAG_NAME = "pyc-site-shell";
if (typeof customElements !== "undefined") {
  if (customElements.get(TAG_NAME) === void 0) {
    customElements.define(TAG_NAME, PycSiteShell);
  }
}
export {
  DEFAULT_METRICS_ENDPOINT,
  DEFAULT_NAVIGATION_ENDPOINT,
  MetricsBeacon,
  NAVIGATION_PROVIDER_ID,
  PaletteDialog,
  PaletteRegistry,
  PermissionCache,
  PermissionSet,
  PycSiteShell,
  SHELL_METRICS,
  SidebarRegistry,
  apply_nav_manifest,
  attach_sidebar_keyboard,
  fetch_nav_manifest,
  initialize_sidebar_roving_tabindex,
  register_navigation_palette_provider
};
