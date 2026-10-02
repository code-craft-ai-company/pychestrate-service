/*
 * Put back what a person had typed when their sign-in or a form's token
 * expired (XC-11).
 *
 * The server keeps the fields of a form it had to refuse for ten minutes,
 * sends the person to sign in or back to the form with ``?draft=<token>``,
 * and, when the page is rendered for them, hands the draft over once as data
 * (``<script type="application/json" id="pyc-form-draft">``: never run, only
 * read). This fills the form on the page with it and says so.
 *
 * What is put back: text-like inputs, text areas, single-choice and several-choice
 * lists, tick boxes and radio buttons (a box the draft does not name was not
 * ticked when the form was sent, so it is unticked). Passwords, hidden fields and
 * files are left as they are (the server does not keep secret-looking fields at
 * all), and the notice says so when the form has a password or a file field.
 *
 * This file is bundled into the shell by esbuild.
 */

const DRAFT_ISLAND_ID = "pyc-form-draft";
const TEXT_INPUT_TYPES = ["", "text", "search", "url", "tel", "email", "number", "date", "datetime-local", "time", "month", "week"];
const NOT_RESTORED_TYPES = ["password", "file"];

/* The ``[name, value]`` pairs in the page's draft, or [] when there is none or it is not well formed. */
export function read_draft_pairs(doc) {
  const island = doc.getElementById(DRAFT_ISLAND_ID);
  if (island === null) {
    return [];
  }
  let parsed = null;
  try {
    parsed = JSON.parse(island.textContent);
  } catch (reason) {
    return [];
  }
  if (Array.isArray(parsed) === false) {
    return [];
  }
  return parsed.filter((pair) => Array.isArray(pair) === true && pair.length === 2 && typeof pair[0] === "string" && typeof pair[1] === "string");
}

function restorable(control) {
  const tag = control.tagName.toLowerCase();
  if (tag === "textarea") {
    return true;
  }
  if (tag === "select") {
    return true;
  }
  if (tag === "input") {
    const type = (control.getAttribute("type") || "").toLowerCase();
    return TEXT_INPUT_TYPES.indexOf(type) >= 0 || type === "checkbox" || type === "radio";
  }
  return false;
}

function is_choice(control) {
  const type = (control.getAttribute("type") || "").toLowerCase();
  return control.tagName.toLowerCase() === "input" && (type === "checkbox" || type === "radio");
}

/* Tick the boxes (or pick the radio button) whose value the draft names; returns whether anything matched. */
function set_choices(controls, values) {
  let changed = false;
  for (const control of controls) {
    const wanted = (control.getAttribute("type") || "").toLowerCase() === "radio"
      ? values.length > 0 && control.value === values[0]
      : values.indexOf(control.value) >= 0;
    if (control.checked !== wanted && (wanted === true || control.type === "checkbox")) {
      control.checked = wanted;
      control.dispatchEvent(new Event("input", { bubbles: true }));
      control.dispatchEvent(new Event("change", { bubbles: true }));
      changed = true;
    }
  }
  return changed;
}

/* Select the options of a several-choice list that the draft names. */
function set_selection(control, values) {
  let any = false;
  for (const option of Array.from(control.options)) {
    const wanted = values.indexOf(option.value) >= 0;
    if (option.selected !== wanted) {
      option.selected = wanted;
    }
    any = any || wanted;
  }
  control.dispatchEvent(new Event("input", { bubbles: true }));
  control.dispatchEvent(new Event("change", { bubbles: true }));
  return any;
}

function set_value(control, value) {
  if (control.tagName.toLowerCase() === "select") {
    const has_option = Array.from(control.options).some((option) => option.value === value);
    if (has_option === false) {
      return false;
    }
  }
  control.value = value;
  control.dispatchEvent(new Event("input", { bubbles: true }));
  control.dispatchEvent(new Event("change", { bubbles: true }));
  return true;
}

/*
 * Fill the form the draft belongs to (the first form that has a control for
 * one of its names). Returns ``{ form, restored, needs_choosing }`` or null
 * when the page has no draft or no such form.
 */
export function restore_form_draft(doc) {
  const pairs = read_draft_pairs(doc);
  if (pairs.length === 0) {
    return null;
  }
  const names = new Set(pairs.map((pair) => pair[0]));
  let target = null;
  for (const form of Array.from(doc.querySelectorAll("form"))) {
    if (Array.from(form.elements).some((control) => names.has(control.name) && restorable(control))) {
      target = form;
      break;
    }
  }
  if (target === null) {
    return null;
  }
  let restored = 0;
  const seen = new Set();
  for (const [name, value] of pairs) {
    if (seen.has(name)) {
      continue;
    }
    seen.add(name);
    const values = pairs.filter((pair) => pair[0] === name).map((pair) => pair[1]);
    const controls = Array.from(target.elements).filter((control) => control.name === name && restorable(control));
    if (controls.length === 0) {
      continue;
    }
    if (controls.every(is_choice) === true) {
      set_choices(controls, values);
      restored += 1;
    } else if (controls.length === 1 && controls[0].tagName.toLowerCase() === "select" && controls[0].multiple === true) {
      if (set_selection(controls[0], values) === true) {
        restored += 1;
      }
    } else if (controls.length === 1 && set_value(controls[0], value) === true) {
      restored += 1;
    }
  }
  // A tick box the draft does not name was not ticked when the form was sent.
  const ticked_names = new Set(pairs.map((pair) => pair[0]));
  for (const control of Array.from(target.elements)) {
    if ((control.getAttribute("type") || "").toLowerCase() === "checkbox" && ticked_names.has(control.name) === false && control.checked === true) {
      control.checked = false;
      control.dispatchEvent(new Event("input", { bubbles: true }));
      control.dispatchEvent(new Event("change", { bubbles: true }));
    }
  }
  const needs_choosing = Array.from(target.elements).some((control) => {
    const type = (control.getAttribute("type") || "").toLowerCase();
    return NOT_RESTORED_TYPES.indexOf(type) >= 0;
  });
  // The token was for this one visit: a reload must not go looking for it.
  try {
    const url = new URL(window.location.href);
    if (url.searchParams.has("draft") === true) {
      url.searchParams.delete("draft");
      window.history.replaceState(window.history.state, "", url.pathname + url.search + url.hash);
    }
  } catch (reason) {
    // No usable address: leave it.
  }
  return { form: target, restored, needs_choosing };
}

/* What the notice says. */
export function draft_notice_message(outcome) {
  let text = "Your session or the form had expired. What you had typed has been put back. Check it, then submit again.";
  if (outcome.needs_choosing === true) {
    text += " Passwords and files are not restored: enter them again.";
  }
  return text;
}
