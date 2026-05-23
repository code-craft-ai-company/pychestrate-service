const TYPE_TO_JUMP_RESET_MS = 1e3;
const NAVITEM_SELECTOR = ".pyc-site-shell__sidebar-navitem";
const ENTRY_SELECTOR = ".pyc-site-shell__sidebar-entry";
const POPUP_CLASS = "pyc-site-shell__sidebar-popup";
const GROUP_BUTTON_CLASS = "pyc-site-shell__sidebar-group-btn";
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
export {
  attach_sidebar_keyboard,
  initialize_sidebar_roving_tabindex
};
