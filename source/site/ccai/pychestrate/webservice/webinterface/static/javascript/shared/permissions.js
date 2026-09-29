/*
 * What the viewer may do, so a view can leave out an action they cannot use
 * (ORC-33).
 *
 * The bundle views showed every write action to every viewer, and the missing
 * permission surfaced only after the form was submitted. The shell already
 * loads the viewer's permission keys (``/api/v1/me/permissions``) to decide
 * which sidebar entries to show; a view asks the same endpoint through
 * ``may`` and hides the action when the key is absent.
 *
 * This is a courtesy, not a boundary: the server still checks every request.
 * So when the answer cannot be had (the request fails, or the body has no
 * permission list) ``may`` says yes and the action stays where it was; a
 * wrongly hidden action is worse than one that is refused with a reason.
 *
 * This file is bundled into each bundle by esbuild; the answer is fetched
 * once per page load.
 */

const PERMISSIONS_URL = "/api/v1/me/permissions";

let held = null;

/* The set of permission keys the viewer holds, or null when it is not known. */
export function held_permissions() {
  if (held !== null) {
    return held;
  }
  held = (async () => {
    try {
      const response = await fetch(PERMISSIONS_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (response.ok !== true) {
        return null;
      }
      const body = await response.json();
      if (body === null || typeof body !== "object" || Array.isArray(body.permissions) === false) {
        return null;
      }
      return new Set(body.permissions.filter((key) => typeof key === "string"));
    } catch (reason) {
      return null;
    }
  })();
  return held;
}

/* True unless the viewer is known not to hold ``permission_key``. */
export async function may(permission_key) {
  const keys = await held_permissions();
  return keys === null ? true : keys.has(permission_key);
}
