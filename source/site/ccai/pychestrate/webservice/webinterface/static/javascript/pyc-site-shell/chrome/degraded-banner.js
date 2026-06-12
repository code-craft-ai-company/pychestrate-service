/*
 * Permissions-degraded banner, built on <mj-alert>. The alert
 * carries severity=warning, owns the icon/surface/ARIA, and
 * exposes its own dismiss button when the dismissible attribute
 * is present. We listen for the alert's close event to record
 * the dismissed state so a subsequent permission failure does
 * not bring the banner back without user consent.
 */

const BANNER_MESSAGE = "Permissions could not be refreshed. Using the last known set. Some controls may behave incorrectly.";

class DegradedBanner {
    constructor(container) {
        this._container = container;
        this._element = null;
        this._dismissed = false;
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
        message.textContent = BANNER_MESSAGE;
        banner.appendChild(message);

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
