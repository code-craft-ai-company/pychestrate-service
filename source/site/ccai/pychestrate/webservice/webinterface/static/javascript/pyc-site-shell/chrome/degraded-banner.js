/*
 * Degraded-state banner, built on <mj-alert>. The alert carries
 * severity=warning, owns the icon/surface/ARIA, and exposes its
 * own dismiss button when the dismissible attribute is present.
 * We listen for the alert's close event to record the dismissed
 * state so a subsequent failure does not bring the banner back
 * without user consent.
 *
 * Each instance owns one failure domain: the default message
 * covers the permissions-refresh path; callers may supply a
 * different message plus an optional action button (label +
 * callback, rendered into the alert's "actions" slot) -- the
 * navigation-manifest failure path uses that to offer a Retry
 * control.
 */

const BANNER_MESSAGE = "Permissions could not be refreshed. Using the last known set. Some controls may behave incorrectly.";

class DegradedBanner {
    constructor(container, options = null) {
        this._container = container;
        this._element = null;
        this._dismissed = false;
        this._message = BANNER_MESSAGE;
        this._action_label = null;
        this._on_action = null;
        if (options !== null && typeof options === "object") {
            if (typeof options.message === "string" && options.message.length > 0) {
                this._message = options.message;
            }
            if (typeof options.action_label === "string" && options.action_label.length > 0) {
                this._action_label = options.action_label;
            }
            if (typeof options.on_action === "function") {
                this._on_action = options.on_action;
            }
        }
    }

    show() {
        if (this._dismissed === true) {
            return;
        }
        if (this._element !== null && this._element.parentNode !== null) {
            return;
        }
        const banner = document.createElement("mj-alert");
        banner.setAttribute("severity", "warning");
        banner.setAttribute("dismissible", "");
        banner.setAttribute("open", "");
        banner.classList.add("pyc-site-shell__degraded-banner");

        const message = document.createElement("span");
        message.classList.add("pyc-site-shell__degraded-banner-message");
        message.textContent = this._message;
        banner.appendChild(message);

        if (this._action_label !== null && this._on_action !== null) {
            const action_button = document.createElement("mj-button");
            action_button.setAttribute("slot", "actions");
            action_button.setAttribute("type", "button");
            action_button.setAttribute("variant", "tertiary");
            action_button.setAttribute("size", "sm");
            action_button.classList.add(
                "pyc-site-shell__degraded-banner-action"
            );
            action_button.textContent = this._action_label;
            action_button.addEventListener("click", () => {
                this._on_action();
            });
            banner.appendChild(action_button);
        }

        banner.addEventListener("mj-alert-close", () => {
            this._dismissed = true;
            this._element = null;
        });

        this._element = banner;
        this._container.insertBefore(banner, this._container.firstChild);
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
    DegradedBanner
};
