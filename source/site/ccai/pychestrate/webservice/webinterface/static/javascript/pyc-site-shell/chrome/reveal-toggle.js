// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/reveal-toggle.js
//
// Show / hide toggles for password-style inputs in the server-rendered
// fragments (secret values, the setup unlock token, new passwords).
// Markup:
//
//     <input type="password" id="value" ...>
//     <button type="button" data-reveal-for="value" aria-pressed="false">Show</button>
//
// Delegated on the document so fragments swapped into the shell keep
// working without re-binding. Busy-state handling for long-running
// POSTs lives here too: a form with data-busy-label="Running…" gets
// its submit buttons disabled and relabelled on submit so a slow
// action (a health probe, a fetch) cannot be triggered twice.

const REVEAL_ATTRIBUTE = "data-reveal-for";
const BUSY_ATTRIBUTE = "data-busy-label";
const INSTALLED_FLAG = "__pycRevealToggleInstalled";

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
    const target = root !== undefined && root !== null ? root : document;
    if (target[INSTALLED_FLAG] === true) {
        return;
    }
    target[INSTALLED_FLAG] = true;
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
        // Defer so the browser serialises the submit buttons before
        // they are disabled.
        window.setTimeout(() => { mark_busy(form); }, 0);
    });
    return;
}

export {
    REVEAL_ATTRIBUTE,
    BUSY_ATTRIBUTE,
    install_reveal_toggle
};
