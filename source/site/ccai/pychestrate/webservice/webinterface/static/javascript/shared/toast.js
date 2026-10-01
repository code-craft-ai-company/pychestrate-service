/*
 * One toast service for the bundle views (ORC-41).
 *
 * Every view built its own toast, in fourteen copies that disagreed: some
 * stacked up to a limit and some replaced, only two marked their region as a
 * live region (so a failure was never announced to a screen reader in the other
 * twelve), a message stayed on screen until dismissed, and it stayed when the
 * person moved to another tab. A view now calls ``show_toast``:
 *
 *  - one toast at a time: a new outcome replaces the last, so the region never
 *    holds a pile of stale notices;
 *  - the region is a polite live region, and an error toast is an ``alert`` (a
 *    success or neutral one is a ``status``), so outcomes are announced;
 *  - a plain success or neutral toast goes away by itself after a few seconds; an
 *    error, and a toast that carries a link, stay until dismissed or replaced;
 *  - ``clear_toasts`` empties the region when the view changes what it shows.
 *
 * The markup is what the views built before (a ``data-role`` and ``data-tone`` on the
 * toast, a message span, a dismiss button), so their stylesheets still apply.
 *
 * This file is bundled into each bundle by esbuild.
 */

import { with_access_request } from "./admin-contact.js";

const DEFAULT_AUTO_DISMISS_MS = 8000;

/*
 * Show ``message`` in ``region``.
 *
 * ``options``: ``class_prefix`` (the view's, "pyc-infra" gives ``pyc-infra__toast``),
 * ``data_role`` (default "toast"), ``dismiss_label`` (default "Dismiss"),
 * ``auto_dismiss_ms`` (0 turns it off), and ``link`` (``{href, text, data_role}``).
 */
export function show_toast(region, message, tone, options) {
  if (region === null || region === void 0) {
    return null;
  }
  const settings = options !== null && typeof options === "object" ? options : {};
  const prefix = typeof settings.class_prefix === "string" ? settings.class_prefix : "pyc";
  if (region.getAttribute("role") === null) {
    region.setAttribute("role", "status");
  }
  if (region.getAttribute("aria-live") === null) {
    region.setAttribute("aria-live", "polite");
  }
  const toast = document.createElement("div");
  toast.classList.add(prefix + "__toast");
  toast.setAttribute("data-role", typeof settings.data_role === "string" ? settings.data_role : "toast");
  toast.setAttribute("data-tone", tone);
  toast.setAttribute("role", tone === "error" ? "alert" : "status");
  const text = document.createElement("span");
  text.classList.add(prefix + "__toast-message");
  text.textContent = with_access_request(message);
  toast.appendChild(text);
  const link = settings.link !== null && typeof settings.link === "object" ? settings.link : null;
  if (link !== null) {
    const anchor = document.createElement("a");
    anchor.classList.add(prefix + "__toast-link");
    anchor.setAttribute("href", link.href);
    if (typeof link.data_role === "string") {
      anchor.setAttribute("data-role", link.data_role);
    }
    anchor.textContent = link.text;
    toast.appendChild(anchor);
  }
  const dismiss = document.createElement("mj-button");
  dismiss.classList.add(prefix + "__toast-dismiss");
  dismiss.setAttribute("type", "button");
  dismiss.setAttribute("aria-label", typeof settings.dismiss_label === "string" ? settings.dismiss_label : "Dismiss");
  dismiss.textContent = "\xD7";
  dismiss.addEventListener("click", () => {
    toast.remove();
  });
  toast.appendChild(dismiss);
  region.replaceChildren(toast);
  const delay = typeof settings.auto_dismiss_ms === "number" ? settings.auto_dismiss_ms : DEFAULT_AUTO_DISMISS_MS;
  if (tone !== "error" && link === null && delay > 0) {
    window.setTimeout(() => {
      // Only this toast: a newer one has already replaced it.
      if (toast.parentNode === region) {
        toast.remove();
      }
    }, delay);
  }
  return toast;
}

/* Empty the region (the view is about to show something else). */
export function clear_toasts(region) {
  if (region !== null && region !== void 0) {
    region.replaceChildren();
  }
}
