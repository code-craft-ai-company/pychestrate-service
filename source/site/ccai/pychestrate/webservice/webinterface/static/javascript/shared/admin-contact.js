/*
 * Whom to ask for access, for a message that says "ask an administrator"
 * (XC-21). The installation names a contact in PYCHESTRATE_ADMIN_CONTACT and
 * the shell document carries it as the ``admin-contact`` attribute; a view
 * appends the sentence to what it says. Without a contact it returns "" so a
 * message never names someone the installation did not name.
 *
 * This file is bundled into each bundle by esbuild.
 */

/*
 * A permission message with the contact added: "You do not have permission to cancel
 * runs." becomes "... To ask for access, contact ops@lab.example." when the installation
 * names one. Any other message, one that already says whom to ask, and every message when
 * no contact is set, are returned as they are.
 */
export function with_access_request(message) {
  if (typeof message !== "string" || message.startsWith("You do not have permission") === false) {
    return message;
  }
  if (/administrator|contact/i.test(message) === true) {
    return message;
  }
  const sentence = access_request_sentence();
  return sentence.length > 0 ? message + " " + sentence : message;
}

/* ``To ask for access, contact <contact>.`` or "" when no contact is set. */
export function access_request_sentence() {
  if (typeof document === "undefined") {
    return "";
  }
  const shell = document.querySelector("pyc-site-shell");
  const contact = shell === null ? "" : (shell.getAttribute("admin-contact") || "").trim();
  return contact.length > 0 ? "To ask for access, contact " + contact + "." : "";
}
