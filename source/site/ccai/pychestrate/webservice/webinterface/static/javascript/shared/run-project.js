/*
 * Which project a build or provisioning run belongs to, from its id alone
 * (E2E-38).
 *
 * A build's id is also its run's id, and ``GET /api/v1/runs/{id}`` names the
 * project. The detail pages used to need ``?project_id=`` in the address, so a
 * link copied from anywhere but the list said "This link is missing its
 * project context". They now ask for the project when the address does not
 * carry it.
 *
 * This file is bundled into each bundle by esbuild.
 */

/* The run's project id, or "" when the run cannot be read (unknown id, no access, a failure). */
export async function project_of_run(run_id) {
  try {
    const response = await fetch("/api/v1/runs/" + encodeURIComponent(run_id), {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (response.ok === false) {
      return "";
    }
    const body = await response.json();
    return body !== null && typeof body === "object" && typeof body.project_id === "string" ? body.project_id : "";
  } catch (reason) {
    return "";
  }
}
