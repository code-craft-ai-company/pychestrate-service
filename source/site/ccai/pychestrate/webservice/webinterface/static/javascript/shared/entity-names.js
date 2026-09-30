/*
 * Name the project and environment a record belongs to, not their ids (ORC-18).
 *
 * The build, provisioning-run and pipeline pages showed "Project  0f6c2c1e-..." and
 * "Environment  9a1b...": a value nobody chose and nobody can read. They now ask
 * for the names once and show them (the id stays in the hover text), falling back
 * to a short id when a name cannot be read, so a page never waits on, or breaks
 * because of, its labels.
 *
 * This file is bundled into each bundle by esbuild.
 */

const PROJECTS_URL = "/api/v1/projects?per_page=500";

async function fetch_items(url) {
  try {
    const response = await fetch(url, {
      method: "GET",
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    });
    if (response.ok === false) {
      return [];
    }
    const body = await response.json();
    if (Array.isArray(body) === true) {
      return body;
    }
    return body !== null && typeof body === "object" && Array.isArray(body.items) === true ? body.items : [];
  } catch (reason) {
    return [];
  }
}

/* { project_id: display name } for the projects the person can see ({} when they cannot be listed). */
export async function fetch_project_names() {
  const names = {};
  for (const item of await fetch_items(PROJECTS_URL)) {
    if (item !== null && typeof item === "object" && typeof item.project_id === "string") {
      const name = typeof item.display_name === "string" && item.display_name.length > 0 ? item.display_name : "";
      if (name.length > 0) {
        names[item.project_id] = name;
      }
    }
  }
  return names;
}

/* { environment_id: name } for one project's environments ({} when they cannot be listed). */
export async function fetch_environment_names(project_id) {
  const names = {};
  if (typeof project_id !== "string" || project_id.length === 0) {
    return names;
  }
  for (const item of await fetch_items("/api/v1/projects/" + encodeURIComponent(project_id) + "/environments")) {
    if (item !== null && typeof item === "object" && typeof item.environment_id === "string") {
      const name = typeof item.name === "string" && item.name.length > 0 ? item.name : "";
      if (name.length > 0) {
        names[item.environment_id] = name;
      }
    }
  }
  return names;
}

/*
 * What to call ``id``: its name from ``names``, else its first eight characters,
 * else a dash when there is no id.
 */
export function name_or_short(names, id) {
  if (typeof id !== "string" || id.length === 0) {
    return "—";
  }
  const known = names[id];
  if (typeof known === "string" && known.length > 0) {
    return known;
  }
  const dash = id.indexOf("-");
  return dash > 0 ? id.slice(0, dash) : id.slice(0, 8);
}
