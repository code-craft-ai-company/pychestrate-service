// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/confirm-delegate.js
//
// One delegated confirmation handler for every server-rendered form
// that carries data-confirm="...". Replaces the per-button
// onclick="return confirm(...)" handlers (28 of them across the
// fragments), which were CSP-hostile and broke on names containing
// quotes. The message comes from the attribute, so templates stay
// declarative:
//
//     <form method="post" action="..." data-confirm="Delete the project
//     &quot;alpha&quot;? This cannot be undone.">
//
// The handler prefers an <mj-dialog> when the component library
// exposes a confirm() helper; otherwise it uses window.confirm so the
// behaviour never silently degrades to "no confirmation".

const CONFIRM_ATTRIBUTE = "data-confirm";
const INSTALLED_FLAG = "__pycConfirmDelegateInstalled";

function resolve_confirm_message(form, submitter) {
    // A data-confirm on the submit button wins over one on the form,
    // so one form can carry two buttons with different messages.
    let raw = null;
    if (submitter !== null && submitter !== undefined && typeof submitter.getAttribute === "function") {
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

/*
 * The confirmation as a modal <dialog> in the site's own styling: the
 * message in full, Cancel focused (so a stray Enter does not delete
 * anything), the acting button named for what it does ("Delete",
 * "Deactivate"), and Escape means no. <dialog>.showModal() traps focus and
 * marks the rest of the page inert, which the browser's own confirm() box
 * does not let a page style or word (XC-15).
 */
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
    const dialog_ctor = typeof customElements !== "undefined"
        ? customElements.get("mj-dialog")
        : undefined;
    if (dialog_ctor !== undefined && typeof dialog_ctor.confirm === "function") {
        try {
            const result = await dialog_ctor.confirm({ message, confirmLabel: confirm_label, cancelLabel: "Cancel" });
            return result === true;
        } catch (error) {
            // Fall through to the page's own dialog.
        }
    }
    if (typeof HTMLDialogElement === "function" && typeof HTMLDialogElement.prototype.showModal === "function") {
        return ask_with_dialog(message, confirm_label);
    }
    return window.confirm(message);
}

/* What the button that will do the deed says: its own text, else "Continue". */
function resolve_confirm_label(submitter) {
    if (submitter !== null && submitter !== undefined && typeof submitter.textContent === "string") {
        const text = submitter.textContent.replace(/\s+/g, " ").trim();
        if (text.length > 0 && text.length <= 40) {
            return text;
        }
    }
    return "Continue";
}

function install_confirm_delegate(root) {
    const target = root !== undefined && root !== null ? root : document;
    if (target[INSTALLED_FLAG] === true) {
        return;
    }
    target[INSTALLED_FLAG] = true;
    target.addEventListener("submit", (event) => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) {
            return;
        }
        const submitter = event.submitter !== undefined ? event.submitter : null;
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
            // Re-submit from a fresh task, never from this microtask: when
            // the confirmation came from the synchronous window.confirm the
            // promise settles while the original submit event is still
            // being dispatched, and the browser silently ignores
            // requestSubmit() on a form whose submission events are still
            // firing. A zero-delay timeout runs after the dispatch ends.
            window.setTimeout(() => {
                form.dataset.pycConfirmed = "true";
                if (typeof form.requestSubmit === "function") {
                    form.requestSubmit(submitter !== null && submitter.form === form ? submitter : undefined);
                } else {
                    form.submit();
                }
            }, 0);
        });
    }, true);
    return;
}

export {
    CONFIRM_ATTRIBUTE,
    install_confirm_delegate
};
