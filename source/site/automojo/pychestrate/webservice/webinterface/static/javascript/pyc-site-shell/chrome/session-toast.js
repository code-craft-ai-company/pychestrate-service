const TOAST_MESSAGE = "Your session expired. Please sign in again.";
class SessionExpiredToast {
  _container;
  _element;
  /**
   * @param container Region the toast attaches to.
   */
  constructor(container) {
    this._container = container;
    this._element = null;
  }
  /**
   * Render the toast if not already visible.
   */
  show() {
    if (this._element !== null && this._element.parentNode !== null) {
      return;
    }
    const toast = document.createElement("div");
    toast.classList.add("pyc-site-shell__session-toast");
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    const message = document.createElement("span");
    message.classList.add("pyc-site-shell__session-toast-message");
    message.textContent = TOAST_MESSAGE;
    toast.appendChild(message);
    const link = document.createElement("a");
    link.classList.add("pyc-site-shell__session-toast-action");
    link.textContent = "Sign in";
    const current_path = window.location.pathname + window.location.search;
    const encoded = encodeURIComponent(current_path);
    link.href = "/login?next=" + encoded;
    toast.appendChild(link);
    this._element = toast;
    this._container.appendChild(toast);
    return;
  }
  /**
   * Remove the toast from the DOM.
   */
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
