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
 * Only what can be restored without guessing is: text-like inputs, text areas
 * and single-choice lists. Passwords, hidden fields, files, tick boxes, radio
 * buttons and lists that take several values are left as they are (the server
 * does not keep secret-looking fields at all), and the notice says the person
 * must choose those again when the form has any.
 *
 * This file is bundled into the shell by esbuild.
 */

const DRAFT_ISLAND_ID = "pyc-form-draft";
const TEXT_INPUT_TYPES = ["", "text", "search", "url", "tel", "email", "number", "date", "datetime-local", "time", "month", "week"];
const NOT_RESTORED_TYPES = ["checkbox", "radio", "password", "file"];

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
    return control.multiple === false;
  }
  if (tag === "input") {
    return TEXT_INPUT_TYPES.indexOf((control.getAttribute("type") || "").toLowerCase()) >= 0;
  }
  return false;
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
    const controls = Array.from(target.elements).filter((control) => control.name === name && restorable(control));
    if (controls.length === 1 && set_value(controls[0], value) === true) {
      restored += 1;
    }
  }
  const needs_choosing = Array.from(target.elements).some((control) => {
    const type = (control.getAttribute("type") || "").toLowerCase();
    return NOT_RESTORED_TYPES.indexOf(type) >= 0 || (control.tagName.toLowerCase() === "select" && control.multiple === true);
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
    text += " Tick boxes, passwords and lists that take several choices are not restored: choose them again.";
  }
  return text;
}
