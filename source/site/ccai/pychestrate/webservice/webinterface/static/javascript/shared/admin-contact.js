/*
 * Whom to ask for access, for a message that says "ask an administrator"
 * (XC-21). The installation names a contact in PYCHESTRATE_ADMIN_CONTACT and
 * the shell document carries it as the ``admin-contact`` attribute; a view
 * appends the sentence to what it says. Without a contact it returns "" so a
 * message never names someone the installation did not name.
 *
 * This file is bundled into each bundle by esbuild.
 */

/* ``To ask for access, contact <contact>.`` or "" when no contact is set. */
export function access_request_sentence() {
  if (typeof document === "undefined") {
    return "";
  }
  const shell = document.querySelector("pyc-site-shell");
  const contact = shell === null ? "" : (shell.getAttribute("admin-contact") || "").trim();
  return contact.length > 0 ? "To ask for access, contact " + contact + "." : "";
}
