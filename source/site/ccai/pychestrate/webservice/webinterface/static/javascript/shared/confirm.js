/*
 * Ask before doing something that cannot be undone (XC-15).
 *
 * The bundle views used the browser's own confirm box, which a page cannot
 * word, style or focus safely. The site shell owns a modal dialog in the
 * product's styling (Cancel focused, the deed named on its button, Escape
 * means no); a view asks for it with a ``pyc-confirm-request`` event and the
 * shell answers. When nothing answers (the view runs outside the shell) the
 * browser's confirm box is used, so a confirmation never silently disappears.
 *
 * This file is bundled into each bundle by esbuild.
 */

/*
 * Resolves true when the person confirms. ``source`` is an element in the page
 * (the view itself), ``message`` says what will be lost, ``confirm_label`` is
 * what the confirming button says ("Delete SLO"). ``options.tone`` is "neutral"
 * for an action that is not destructive ("Run pipeline"): the confirming button
 * is then the primary colour, not the red of a delete. ``options.type`` is a text the person must
 * type before the confirming button turns on ("Delete pool lab-2": type ``lab-2``): for a deed
 * that cannot be undone and takes a lot with it. Outside the shell there is no field to type in,
 * so the browser's own box asks, as for every confirmation.
 */
export function confirm_action(source, message, confirm_label, options) {
  const tone = options !== null && options !== void 0 && options.tone === "neutral" ? "neutral" : "danger";
  const type_to_confirm = options !== null && options !== void 0 && typeof options.type === "string" ? options.type.trim() : "";
  return new Promise((resolve) => {
    const request = new CustomEvent("pyc-confirm-request", {
      bubbles: true,
      composed: true,
      cancelable: true,
      detail: { message, confirm_label, tone, type_to_confirm, resolve },
    });
    const answered_by_shell = source.dispatchEvent(request) === false;
    if (answered_by_shell === false) {
      resolve(window.confirm(message));
    }
  });
}

/*
 * What the confirming button should say when the action button that asked is at
 * hand: its own text ("Drain"), or ``fallback`` when it has none or a long one.
 */
export function label_from_button(button, fallback) {
  const text = button !== null && button !== void 0 && typeof button.textContent === "string" ? button.textContent.replace(/\s+/g, " ").trim() : "";
  return text.length > 0 && text.length <= 40 ? text : fallback;
}
