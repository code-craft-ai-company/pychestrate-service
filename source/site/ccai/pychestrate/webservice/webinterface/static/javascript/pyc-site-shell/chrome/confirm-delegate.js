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

async function ask_confirmation(message) {
    const dialog_ctor = typeof customElements !== "undefined"
        ? customElements.get("mj-dialog")
        : undefined;
    if (dialog_ctor !== undefined && typeof dialog_ctor.confirm === "function") {
        try {
            const result = await dialog_ctor.confirm({ message, confirmLabel: "Continue", cancelLabel: "Cancel" });
            return result === true;
        } catch (error) {
            // Fall through to the native dialog.
        }
    }
    return window.confirm(message);
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
        ask_confirmation(message).then((accepted) => {
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
