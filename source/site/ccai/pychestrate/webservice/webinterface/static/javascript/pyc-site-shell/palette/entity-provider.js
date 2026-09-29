/*
 * Palette providers beyond navigation (XC-17): projects by name, a run or
 * build by its id, and actions.
 *
 * The palette found only navigation entries, so "checkout", a project's name,
 * "create", "sign out" and "theme" all answered "No results". These providers
 * add what a person types into a palette to do: jump to a project, open a run
 * or build they were sent the id of, and run a common action.
 *
 * Every result is a destination or a callback the shell already has; nothing
 * here reaches an endpoint the person could not reach from the page. A source
 * that cannot answer (no permission to list projects, a failure) returns no
 * results instead of an error, so the palette never shows a source that
 * "is unavailable" for a permission the person simply does not hold.
 */

const PROJECTS_PROVIDER_ID = "shell.projects";
const RECORDS_PROVIDER_ID = "shell.records";
const ACTIONS_PROVIDER_ID = "shell.actions";
const PROJECTS_URL = "/api/v1/projects?per_page=500";
const PROJECTS_CACHE_MS = 60 * 1000;
const PROJECT_RESULT_LIMIT = 6;
const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/*
 * The actions a person types for: [label, extra words to match, route or
 * null, the permission-bearing route prefix that must be visible or null,
 * callback name or null]. An action that navigates is listed only when a
 * visible navigation entry lies under the same prefix, so a person is never
 * offered a destination they cannot open.
 */
const ACTIONS = [
  { label: "Create a project", words: "new add project", route: "/projects/create", needs: "/projects" },
  { label: "Register a device", words: "add new resource checkout check out lab", route: "/resource-pools", needs: "/resource-pools" },
  { label: "Run tests", words: "test catalog start", route: "/test-catalog", needs: "/test-catalog" },
  { label: "Trigger a build", words: "build start new", route: "/builds", needs: "/builds" },
  { label: "Define a pipeline", words: "pipeline create new", route: "/pipelines", needs: "/pipelines" },
  { label: "Create an API token", words: "token pyc cli new", route: "/account/api-tokens", needs: null },
  { label: "Preferences", words: "settings profile account", route: "/account/preferences", needs: null },
  { label: "Switch theme", words: "dark light mode appearance colour color", route: null, needs: null, callback: "toggle_theme" },
  { label: "Sign out", words: "log out logout leave", route: null, needs: null, callback: "sign_out" },
];

function normalise(text) {
  return typeof text === "string" ? text.trim().toLowerCase() : "";
}

/* Register the projects, records and actions providers on ``palette``. */
export function register_entity_palette_providers(palette, options) {
  let cached = null;
  let cached_at = 0;

  async function projects() {
    const now = Date.now();
    if (cached !== null && now - cached_at < PROJECTS_CACHE_MS) {
      return cached;
    }
    let found = [];
    try {
      const response = await fetch(PROJECTS_URL, {
        method: "GET",
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (response.ok === true) {
        const body = await response.json();
        const items = Array.isArray(body) ? body : body !== null && Array.isArray(body.items) ? body.items : [];
        found = items.filter((item) => item !== null && typeof item === "object" && typeof item.project_id === "string");
      }
    } catch (reason) {
      found = [];
    }
    cached = found;
    cached_at = now;
    return found;
  }

  palette.registerProvider({
    providerId: PROJECTS_PROVIDER_ID,
    label: "Projects",
    requiredPermissions: [],
    query: async (query) => {
      const wanted = normalise(query);
      if (wanted.length < 2) {
        return [];
      }
      const hits = [];
      for (const project of await projects()) {
        const name = normalise(project.display_name);
        const slug = normalise(project.slug);
        let score = 0;
        if (name.startsWith(wanted) || slug.startsWith(wanted)) {
          score = 2;
        } else if (name.includes(wanted) || slug.includes(wanted)) {
          score = 1;
        }
        if (score > 0) {
          hits.push({ score, project });
        }
      }
      hits.sort((left, right) => right.score - left.score);
      return hits.slice(0, PROJECT_RESULT_LIMIT).map(({ project }) => {
        const shown = typeof project.display_name === "string" && project.display_name.length > 0 ? project.display_name : project.slug;
        const slug = typeof project.slug === "string" && project.slug.length > 0 ? project.slug : project.project_id;
        return { id: "project:" + project.project_id, label: shown, description: "Project · " + slug, route: "/projects/" + encodeURIComponent(slug) };
      });
    },
  });

  palette.registerProvider({
    providerId: RECORDS_PROVIDER_ID,
    label: "Open by id",
    requiredPermissions: [],
    query: async (query) => {
      const text = typeof query === "string" ? query.trim() : "";
      if (UUID_PATTERN.test(text) === false) {
        return [];
      }
      const id = text.toLowerCase();
      return [
        { id: "run:" + id, label: "Run " + id.split("-")[0], description: "Open the run with this id", route: "/runs/" + id },
        { id: "build:" + id, label: "Build " + id.split("-")[0], description: "Open the build with this id", route: "/builds/" + id },
      ];
    },
  });

  palette.registerProvider({
    providerId: ACTIONS_PROVIDER_ID,
    label: "Actions",
    requiredPermissions: [],
    query: async (query) => {
      const wanted = normalise(query);
      if (wanted.length === 0) {
        return [];
      }
      const reachable = typeof options.get_visible_routes === "function" ? options.get_visible_routes() : [];
      const results = [];
      for (const action of ACTIONS) {
        const haystack = normalise(action.label + " " + action.words);
        if (haystack.includes(wanted) === false) {
          continue;
        }
        if (action.needs !== null && reachable.some((route) => route === action.needs || route.startsWith(action.needs + "/")) === false) {
          continue;
        }
        const result = { id: "action:" + action.label.toLowerCase().replace(/[^a-z]+/g, "-"), label: action.label, description: "Action" };
        if (action.route !== null) {
          result.route = action.route;
        } else if (typeof options[action.callback] === "function") {
          result.onActivate = () => options[action.callback]();
        } else {
          continue;
        }
        results.push(result);
      }
      return results;
    },
  });
}
