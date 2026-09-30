/*
 * Bring content a person just asked for into view and hand it the keyboard (ORC-41).
 *
 * A view that opens a form or a detail panel put it where the DOM had room: a form
 * above the list, a detail below it. Below the list it opened out of sight (choosing
 * "Show Published Release" on a long list changed nothing on the screen), and for a
 * keyboard or screen-reader user nothing said the new content was there, because focus
 * stayed on the button. ``reveal`` is called once the content is visible and rendered:
 *
 *  - it scrolls the region into view when it is not already (only then: a form that
 *    opened in view is not moved), starting at the top when it is taller than the
 *    window;
 *  - it moves focus into it: to ``options.focus`` (an element or a selector) when
 *    given, else the first form control, else the region's heading, else the region
 *    itself (given ``tabindex="-1"`` so it can take focus).
 *
 * Call it only for something the person just asked for, never for a refresh: focus
 * that jumps while someone is reading is worse than content below the fold.
 *
 * This file is bundled into each bundle by esbuild.
 */

const CONTROL_SELECTOR = [
  "mj-text-field",
  "mj-textarea",
  "mj-select",
  'input:not([type="hidden"]):not([disabled])',
  "select:not([disabled])",
  "textarea:not([disabled])"
].join(", ");

const HEADING_SELECTOR = "h1, h2, h3, h4";

/*
 * The element to focus in ``region``.
 */
function focus_target_for(region, wanted) {
  if (typeof wanted === "string") {
    const found = region.querySelector(wanted);
    return found;
  }
  if (wanted !== null && wanted !== void 0) {
    return wanted;
  }
  const control = region.querySelector(CONTROL_SELECTOR);
  if (control !== null) {
    return control;
  }
  const heading = region.querySelector(HEADING_SELECTOR);
  const target = heading !== null ? heading : region;
  if (target.hasAttribute("tabindex") === false) {
    target.setAttribute("tabindex", "-1");
  }
  return target;
}

/*
 * Scroll ``region`` into view if it is not, and focus its first useful element.
 *
 * ``options``: ``focus`` (an element or a selector inside the region to focus
 * instead of the default).
 *
 * Returns the element that took focus, or ``null`` when there was none.
 */
export function reveal(region, options) {
  if (region === null || region === void 0 || region.hidden === true || region.isConnected !== true) {
    return null;
  }
  const settings = options !== null && typeof options === "object" ? options : {};
  const target = focus_target_for(region, settings.focus);
  if (target !== null && target !== void 0 && typeof target.focus === "function") {
    target.focus();
  }
  const box = region.getBoundingClientRect();
  const height = window.innerHeight || document.documentElement.clientHeight;
  if (box.top < 0 || box.bottom > height) {
    region.scrollIntoView({ block: box.height > height ? "start" : "nearest", behavior: "auto" });
  }
  const focused = target !== null && target !== void 0 ? target : null;
  return focused;
}
