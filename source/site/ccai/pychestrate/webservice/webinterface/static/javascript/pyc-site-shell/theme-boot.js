/*
 * theme-boot.js -- apply the stored theme before the first paint.
 *
 * Loaded by the shell document as a classic, render-blocking
 * <script> in <head> (not a module, which would run only after
 * the document has been parsed and painted). It pins data-theme
 * on <html> to the theme the user chose with the header's theme
 * control, so a page never flashes the OS-preferred palette first.
 * With no stored choice it does nothing and the design tokens
 * follow prefers-color-scheme.
 *
 * Kept as a file rather than inline so it works under a
 * script-src 'self' Content-Security-Policy. The storage key must
 * match THEME_STORAGE_KEY in pyc-site-shell.js.
 */
(function () {
    "use strict";
    var THEME_STORAGE_KEY = "pychestrate.ui.theme";
    try {
        var stored = window.localStorage.getItem(THEME_STORAGE_KEY);
        if (stored === "dark" || stored === "light") {
            document.documentElement.setAttribute("data-theme", stored);
        }
    } catch (error) {
        // Storage unavailable (privacy mode): follow the OS preference.
    }
}());
