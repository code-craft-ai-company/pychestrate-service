/*
 * Session-expired notification, built on <mj-toast>. The toast
 * carries severity=warning, no auto-dismiss (the user needs to
 * see it long enough to act), and surfaces a "Sign in" link in
 * the actions slot. mj-toast handles the surface, icon, ARIA
 * live-region politeness, and dismiss control for us.
 */

const TOAST_HEADING = "Your session expired. Please sign in again.";

class SessionExpiredToast {
    constructor(container) {
        this._container = container;
        this._element = null;
    }

    show() {
        if (this._element !== null && this._element.parentNode !== null) {
            this._element.setAttribute("open", "");
            return;
        }
        const toast = document.createElement("mj-toast");
        toast.setAttribute("severity", "warning");
        toast.setAttribute("heading", TOAST_HEADING);
        toast.setAttribute("auto-dismiss", "0");
        toast.setAttribute("open", "");
        toast.classList.add("pyc-site-shell__session-toast");

        const action = document.createElement("a");
        action.setAttribute("slot", "actions");
        action.classList.add("pyc-site-shell__session-toast-action");
        action.textContent = "Sign in";
        const current_path = window.location.pathname + window.location.search;
        const encoded = encodeURIComponent(current_path);
        action.href = "/login?next=" + encoded;
        toast.appendChild(action);

        this._element = toast;
        this._container.appendChild(toast);
        return;
    }

    hide() {
        if (this._element !== null && this._element.parentNode !== null) {
            this._element.parentNode.removeChild(this._element);
        }
        this._element = null;
        return;
    }
}

export {
    SessionExpiredToast
};
