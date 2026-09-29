/*
 * Build the no-permissions empty state as an <mj-empty-state>.
 * The heading attribute supplies the title; the description slot
 * carries the supplemental body copy. mj-empty-state owns the
 * surface, typography, and the actions slot so we do not
 * re-implement the layout.
 *
 * When the installation names an access contact (the ``admin-contact``
 * attribute, from PYCHESTRATE_ADMIN_CONTACT) the panel says whom to ask, and
 * when that is an email address it offers a message that is already written
 * (XC-21). Without a contact it says only what it always said.
 */

const EMAIL_PATTERN = /^[^\s@<>"']+@[^\s@<>"']+\.[^\s@<>"']+$/;

function build_request_link(contact, login_name) {
    const lines = ["Hello,", "", "Please give my Pychestrate account a role so I can use it."];
    if (login_name.length > 0) {
        lines.push("", "Account: " + login_name);
    }
    const link = document.createElement("a");
    link.setAttribute(
        "href",
        "mailto:" + contact + "?subject=" + encodeURIComponent("Pychestrate access request") + "&body=" + encodeURIComponent(lines.join("\n"))
    );
    link.setAttribute("data-role", "request-access");
    link.textContent = "Email " + contact + " to request access";
    return link;
}

function build_empty_state(options) {
    const settings = options !== null && typeof options === "object" ? options : {};
    const contact = typeof settings.admin_contact === "string" ? settings.admin_contact.trim() : "";
    const login_name = typeof settings.user_login_name === "string" ? settings.user_login_name.trim() : "";

    const panel = document.createElement("mj-empty-state");
    panel.setAttribute("heading", "Your account has no access yet");
    panel.setAttribute("role", "status");
    panel.setAttribute("heading-level", "1");
    panel.classList.add("pyc-site-shell__empty-state");

    const body = document.createElement("p");
    body.setAttribute("slot", "description");
    body.classList.add("pyc-site-shell__empty-state-body");
    body.textContent = "Ask an administrator to grant you a role so you can use Pychestrate.";
    panel.appendChild(body);

    if (contact.length > 0) {
        const who = document.createElement("p");
        who.setAttribute("slot", "description");
        who.classList.add("pyc-site-shell__empty-state-body");
        who.setAttribute("data-role", "admin-contact");
        if (EMAIL_PATTERN.test(contact) === true) {
            who.appendChild(build_request_link(contact, login_name));
        } else {
            who.textContent = "To ask for access, contact " + contact + ".";
        }
        panel.appendChild(who);
    }

    return panel;
}

export {
    build_empty_state
};
