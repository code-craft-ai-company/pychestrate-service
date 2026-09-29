import { format_instant, parse_timestamp } from "../../shared/datetime.js";
/*
 * The shell-rendered landing view for the bare "/" route. No
 * feature bundle claims "/", so without this the main region
 * renders empty chrome.
 *
 * A first-time administrator used to land on a site map of 37 links
 * with nothing saying what to do first (LD-10). The view now leads
 * with a getting-started checklist driven by what exists (a project, a
 * pod that has enrolled, a run), then the newest runs once there are
 * some. The full list of sections stays one click away under
 * "All sections", and is open when the numbers cannot be read.
 *
 * Every step is offered only when the person can reach its page: a link
 * appears when the route is in their visible sidebar, so the checklist
 * follows their permissions and the deployment's UI profile without a
 * second permission model.
 */

const PROJECTS_URL = "/api/v1/projects?per_page=1";
const CLIENTS_URL = "/api/v1/clients?per_page=1";
const RUNS_URL = "/api/v1/runs?per_page=5";

const RECENT_RUN_LIMIT = 5;

function build_home_view(options) {
    const panel = document.createElement("section");
    panel.classList.add("pyc-site-shell__home");
    panel.setAttribute("aria-label", "Home");

    const heading = document.createElement("h1");
    heading.classList.add("pyc-site-shell__home-heading");
    heading.textContent = options.brand_label;
    panel.appendChild(heading);

    const subtitle = document.createElement("p");
    subtitle.classList.add("pyc-site-shell__home-subtitle");
    subtitle.textContent = "Checking what is set up…";
    panel.appendChild(subtitle);

    const status = document.createElement("div");
    status.classList.add("pyc-site-shell__home-status");
    status.setAttribute("aria-live", "polite");
    panel.appendChild(status);

    const sections = document.createElement("details");
    sections.classList.add("pyc-site-shell__home-sections");
    sections.setAttribute("data-role", "all-sections");
    const summary = document.createElement("summary");
    summary.textContent = "All sections";
    sections.appendChild(summary);
    sections.appendChild(build_nav_link_grid(options.visible_sidebar));
    panel.appendChild(sections);

    void hydrate_home_view(panel, subtitle, status, sections, options);
    return panel;
}

/*
 * Read the state the checklist depends on and render it. A request that
 * fails (a person without permission, a network error) leaves that
 * count unknown: its step is then shown without a done mark rather than
 * claiming it is not done.
 */
async function hydrate_home_view(panel, subtitle, status, sections, options) {
    const fetch_impl = typeof options.fetch_impl === "function" ? options.fetch_impl : window.fetch.bind(window);
    const routes = visible_routes(options.visible_sidebar);

    const wants_projects = routes.has("/projects");
    const wants_clients = routes.has("/clients");
    const wants_runs = routes.has("/runs");

    const [projects, clients, runs] = await Promise.all([
        wants_projects ? fetch_page(PROJECTS_URL, fetch_impl) : Promise.resolve(null),
        wants_clients ? fetch_page(CLIENTS_URL, fetch_impl) : Promise.resolve(null),
        wants_runs ? fetch_page(RUNS_URL, fetch_impl) : Promise.resolve(null)
    ]);

    const counts = {
        projects: total_of(projects),
        clients: total_of(clients),
        runs: total_of(runs)
    };
    const steps = build_steps(counts, routes);
    const readable = counts.projects !== null || counts.clients !== null || counts.runs !== null;

    status.textContent = "";
    if (readable === false) {
        subtitle.textContent = "Choose a destination to get started.";
        sections.open = true;
    } else if (all_done(steps) === true) {
        subtitle.textContent = "You are set up. Pick up where you left off.";
        sections.open = false;
    } else {
        subtitle.textContent = "Three steps to your first run.";
        status.appendChild(build_checklist(steps));
        sections.open = false;
    }

    if (runs !== null && Array.isArray(runs.items) === true && runs.items.length > 0) {
        status.appendChild(build_recent_runs(runs.items.slice(0, RECENT_RUN_LIMIT)));
    }

    panel.setAttribute("data-home-ready", "true");
    panel.dispatchEvent(new CustomEvent("pyc-site-shell-home-hydrated", { bubbles: true }));
    return;
}

async function fetch_page(url, fetch_impl) {
    let rtnval = null;
    try {
        const response = await fetch_impl(url, {
            method: "GET",
            credentials: "same-origin",
            headers: { Accept: "application/json" }
        });
        if (response.ok === true) {
            rtnval = await response.json();
        }
    } catch (reason) {
        console.warn("pychestrate.ui.shell.home_fetch_failed", { url, reason: String(reason) });
    }
    return rtnval;
}

function total_of(body) {
    let rtnval = null;
    if (Array.isArray(body) === true) {
        // The clients list answers a bare array, not {items, meta}.
        rtnval = body.length;
    } else if (body !== null && typeof body === "object") {
        if (body.meta !== undefined && body.meta !== null && typeof body.meta.total === "number") {
            rtnval = body.meta.total;
        } else if (Array.isArray(body.items) === true) {
            rtnval = body.items.length;
        }
    }
    return rtnval;
}

function visible_routes(visible_sidebar) {
    const rtnval = new Set();
    for (const entry of visible_sidebar.ungrouped) {
        rtnval.add(entry.route);
    }
    for (const bucket of visible_sidebar.groups) {
        for (const entry of bucket.entries) {
            rtnval.add(entry.route);
        }
    }
    return rtnval;
}

/*
 * The three setup steps. ``done`` is true, false, or null when the count
 * could not be read. ``actions`` are the links the person can follow.
 */
function build_steps(counts, routes) {
    const project_actions = [];
    if (routes.has("/projects") === true) {
        project_actions.push({ label: "Create a project", href: "/projects/create" });
    }

    const pod_actions = [];
    let pod_detail = "A pod is a machine that runs your jobs. Mint an enrollment token, then run the client on the machine.";
    if (routes.has("/admin/enrollment-tokens") === true) {
        pod_actions.push({ label: "Mint an enrollment token", href: "/admin/enrollment-tokens" });
    } else {
        pod_detail = "A pod is a machine that runs your jobs. Ask an administrator to enroll one.";
    }

    const run_actions = [];
    if (routes.has("/test-catalog") === true) {
        run_actions.push({ label: "Import tests", href: "/test-catalog" });
    }
    if (routes.has("/builds") === true) {
        run_actions.push({ label: "Start a build", href: "/builds" });
    }
    if (routes.has("/runs") === true) {
        run_actions.push({ label: "See runs", href: "/runs" });
    }

    const rtnval = [
        {
            id: "project",
            title: "Create a project",
            detail: "Projects organize your jobs, pods and resources.",
            done: done_from(counts.projects),
            actions: project_actions
        },
        {
            id: "pod",
            title: "Enroll a pod",
            detail: pod_detail,
            done: done_from(counts.clients),
            actions: pod_actions
        },
        {
            id: "run",
            title: "Run something",
            detail: "Add tests, a build or an RPA job to a project, then start a run.",
            done: done_from(counts.runs),
            actions: run_actions
        }
    ];
    return rtnval;
}

function done_from(count) {
    let rtnval = null;
    if (count !== null) {
        rtnval = count > 0;
    }
    return rtnval;
}

function all_done(steps) {
    let rtnval = true;
    for (const step of steps) {
        if (step.done !== true) {
            rtnval = false;
        }
    }
    return rtnval;
}

function build_checklist(steps) {
    const section = document.createElement("section");
    section.classList.add("pyc-site-shell__getting-started");
    section.setAttribute("data-role", "getting-started");
    section.setAttribute("aria-labelledby", "pyc-getting-started-heading");

    const heading = document.createElement("h2");
    heading.id = "pyc-getting-started-heading";
    heading.classList.add("pyc-site-shell__home-section-heading");
    heading.textContent = "Get started";
    section.appendChild(heading);

    const list = document.createElement("ol");
    list.classList.add("pyc-site-shell__checklist");
    for (const step of steps) {
        list.appendChild(build_step(step));
    }
    section.appendChild(list);
    return section;
}

function build_step(step) {
    const item = document.createElement("li");
    item.classList.add("pyc-site-shell__checklist-step");
    item.setAttribute("data-step", step.id);
    let state = "unknown";
    if (step.done === true) {
        state = "done";
    } else if (step.done === false) {
        state = "todo";
    }
    item.setAttribute("data-state", state);

    const mark = document.createElement("span");
    mark.classList.add("pyc-site-shell__checklist-mark");
    mark.setAttribute("aria-hidden", "true");
    mark.textContent = state === "done" ? "✓" : "";
    item.appendChild(mark);

    const body = document.createElement("div");
    body.classList.add("pyc-site-shell__checklist-body");

    const title = document.createElement("p");
    title.classList.add("pyc-site-shell__checklist-title");
    title.textContent = step.title;
    if (state === "done") {
        const hidden = document.createElement("span");
        hidden.classList.add("pyc-site-shell__visually-hidden");
        hidden.textContent = " (done)";
        title.appendChild(hidden);
    }
    body.appendChild(title);

    const detail = document.createElement("p");
    detail.classList.add("pyc-site-shell__checklist-detail");
    detail.textContent = step.detail;
    body.appendChild(detail);

    if (state !== "done" && step.actions.length > 0) {
        const actions = document.createElement("p");
        actions.classList.add("pyc-site-shell__checklist-actions");
        for (const action of step.actions) {
            const link = document.createElement("a");
            link.href = action.href;
            link.textContent = action.label;
            actions.appendChild(link);
        }
        body.appendChild(actions);
    }
    item.appendChild(body);
    return item;
}

const RUN_ERROR_STATES = ["failed", "dispatch_failed", "dispatch_lost", "needs_investigation"];
const RUN_WARN_STATES = ["progress_stalled", "dispatch_unconfirmed", "cancel_requested", "cancelling", "cancelled"];

function run_tone(run_state) {
    let rtnval = "neutral";
    if (run_state === "completed") {
        rtnval = "ok";
    } else if (RUN_ERROR_STATES.indexOf(run_state) >= 0) {
        rtnval = "error";
    } else if (RUN_WARN_STATES.indexOf(run_state) >= 0) {
        rtnval = "warn";
    }
    return rtnval;
}

function build_recent_runs(runs) {
    const section = document.createElement("section");
    section.classList.add("pyc-site-shell__recent-runs");
    section.setAttribute("data-role", "recent-runs");
    section.setAttribute("aria-labelledby", "pyc-recent-runs-heading");

    const heading = document.createElement("h2");
    heading.id = "pyc-recent-runs-heading";
    heading.classList.add("pyc-site-shell__home-section-heading");
    heading.textContent = "Recent runs";
    section.appendChild(heading);

    const list = document.createElement("ul");
    list.classList.add("pyc-site-shell__recent-runs-list");
    for (const run of runs) {
        const item = document.createElement("li");
        item.classList.add("pyc-site-shell__recent-run");

        const link = document.createElement("a");
        const run_id = String(run.run_id);
        link.href = "/runs/" + run_id;
        link.textContent = run_id.slice(0, 8);
        item.appendChild(link);

        const chip = document.createElement("mj-chip");
        chip.setAttribute("data-tone", run_tone(run.state));
        chip.textContent = String(run.state);
        item.appendChild(chip);

        const when = document.createElement("span");
        when.classList.add("pyc-site-shell__recent-run-time");
        const stamp = run.completed_at || run.started_at || run.created_at;
        const parsed = stamp ? parse_timestamp(stamp) : null;
        when.textContent = parsed !== null ? format_instant(parsed) : "";
        item.appendChild(when);
        list.appendChild(item);
    }
    section.appendChild(list);

    const all = document.createElement("p");
    all.classList.add("pyc-site-shell__recent-runs-all");
    const all_link = document.createElement("a");
    all_link.href = "/runs";
    all_link.textContent = "All runs";
    all.appendChild(all_link);
    section.appendChild(all);
    return section;
}

/*
 * Build a grid of navigation links from a visible-sidebar
 * structure ({ groups: [{ group, entries }], ungrouped: [] } --
 * the shape SidebarRegistry.visible returns). Shared between the
 * home view and the not-found view. Links are plain <a href> so
 * they perform the same full page navigation the sidebar does.
 */
function build_nav_link_grid(visible_sidebar) {
    const grid = document.createElement("nav");
    grid.classList.add("pyc-site-shell__nav-grid");
    grid.setAttribute("aria-label", "Site sections");

    if (visible_sidebar.ungrouped.length > 0) {
        const card = build_nav_grid_card(null, visible_sidebar.ungrouped);
        grid.appendChild(card);
    }

    for (const bucket of visible_sidebar.groups) {
        const card = build_nav_grid_card(bucket.group.label, bucket.entries);
        grid.appendChild(card);
    }

    return grid;
}

function build_nav_grid_card(group_label, entries) {
    const card = document.createElement("section");
    card.classList.add("pyc-site-shell__nav-grid-card");

    if (group_label !== null) {
        const heading = document.createElement("h2");
        heading.classList.add("pyc-site-shell__nav-grid-card-heading");
        heading.textContent = group_label;
        card.appendChild(heading);
    }

    const list = document.createElement("ul");
    list.classList.add("pyc-site-shell__nav-grid-list");
    for (const entry of entries) {
        const item = document.createElement("li");
        const link = document.createElement("a");
        link.href = entry.route;
        link.textContent = entry.label;
        link.classList.add("pyc-site-shell__nav-grid-link");
        item.appendChild(link);
        list.appendChild(item);
    }
    card.appendChild(list);

    return card;
}

export {
    build_home_view,
    build_nav_link_grid,
    build_steps,
    run_tone,
    total_of
};
