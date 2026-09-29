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
 * what the confirming button says ("Delete SLO").
 */
export function confirm_action(source, message, confirm_label) {
  return new Promise((resolve) => {
    const request = new CustomEvent("pyc-confirm-request", {
      bubbles: true,
      composed: true,
      cancelable: true,
      detail: { message, confirm_label, resolve },
    });
    const answered_by_shell = source.dispatchEvent(request) === false;
    if (answered_by_shell === false) {
      resolve(window.confirm(message));
    }
  });
}
