// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/log-viewer.js
//
// Behaviour for the shared log viewer the build / infrastructure / test
// log pages render (see the log_viewer macro in site_shell/_macros.html):
//
//   <div class="pyc-log-viewer" data-log-source="<same page URL>"
//        data-log-running="true" data-log-refresh-seconds="10">
//     <div class="pyc-log-viewer__toolbar"> ...Follow / Copy / Download... </div>
//     <pre class="pyc-log-viewer__output" tabindex="0">...</pre>
//   </div>
//
// While data-log-running is "true" the viewer re-fetches its own page
// every N seconds, swaps in the new <pre> text, and keeps the scroll
// pinned to the bottom when "Follow" is on. This replaces the
// <meta http-equiv="refresh"> that reloaded the entire shell every
// ten seconds and reset the user's scroll position. Copy uses the
// clipboard API; Download builds a Blob so the browser saves a .log.

const VIEWER_SELECTOR = ".pyc-log-viewer";
const OUTPUT_SELECTOR = ".pyc-log-viewer__output";
const INSTALLED_FLAG = "__pycLogViewerInstalled";
const DEFAULT_REFRESH_SECONDS = 10;

function is_following(viewer) {
    const toggle = viewer.querySelector("[data-log-follow]");
    if (toggle === null) {
        return true;
    }
    return toggle.checked === true;
}

function scroll_to_end(output) {
    output.scrollTop = output.scrollHeight;
    return;
}

async function refresh_once(viewer) {
    const source = viewer.getAttribute("data-log-source") || window.location.href;
    let response;
    try {
        response = await fetch(source, { credentials: "same-origin", cache: "no-store", headers: { "Accept": "text/html" } });
    } catch (error) {
        return false;
    }
    if (response.ok !== true) {
        return false;
    }
    const html = await response.text();
    const parsed = new DOMParser().parseFromString(html, "text/html");
    const fresh_viewer = parsed.querySelector(VIEWER_SELECTOR);
    const fresh_output = parsed.querySelector(OUTPUT_SELECTOR);
    const output = viewer.querySelector(OUTPUT_SELECTOR);
    if (fresh_output === null || output === null) {
        return false;
    }
    const follow = is_following(viewer);
    if (output.textContent !== fresh_output.textContent) {
        output.textContent = fresh_output.textContent;
        if (follow === true) {
            scroll_to_end(output);
        }
    }
    const still_running = fresh_viewer !== null && fresh_viewer.getAttribute("data-log-running") === "true";
    viewer.setAttribute("data-log-running", still_running ? "true" : "false");
    const status = viewer.querySelector("[data-log-status]");
    if (status !== null) {
        status.textContent = still_running ? "Live: refreshing while the job runs" : "Finished: log is complete";
    }
    return still_running;
}

function schedule(viewer) {
    if (viewer.getAttribute("data-log-running") !== "true") {
        return;
    }
    const seconds = Number.parseInt(viewer.getAttribute("data-log-refresh-seconds") || "", 10);
    const delay = Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : DEFAULT_REFRESH_SECONDS * 1000;
    window.setTimeout(() => {
        if (document.body.contains(viewer) === false) {
            return;
        }
        refresh_once(viewer).then((still_running) => {
            if (still_running === true) {
                schedule(viewer);
            }
        });
    }, delay);
    return;
}

function copy_output(viewer) {
    const output = viewer.querySelector(OUTPUT_SELECTOR);
    if (output === null || typeof navigator === "undefined" || !navigator.clipboard) {
        return;
    }
    navigator.clipboard.writeText(output.textContent).then(() => {
        const status = viewer.querySelector("[data-log-status]");
        if (status !== null) {
            const previous = status.textContent;
            status.textContent = "Copied to clipboard";
            window.setTimeout(() => { status.textContent = previous; }, 2000);
        }
    }).catch(() => { /* clipboard unavailable: nothing to do */ });
    return;
}

function download_output(viewer) {
    const output = viewer.querySelector(OUTPUT_SELECTOR);
    if (output === null) {
        return;
    }
    const name = viewer.getAttribute("data-log-filename") || "log.txt";
    const blob = new Blob([output.textContent], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => { URL.revokeObjectURL(url); }, 1000);
    return;
}

function initialise_viewer(viewer) {
    if (viewer.dataset.pycLogInitialised === "true") {
        return;
    }
    viewer.dataset.pycLogInitialised = "true";
    const output = viewer.querySelector(OUTPUT_SELECTOR);
    if (output !== null && is_following(viewer) === true) {
        scroll_to_end(output);
    }
    schedule(viewer);
    return;
}

function install_log_viewer(root) {
    const target = root !== undefined && root !== null ? root : document;
    if (target[INSTALLED_FLAG] === true) {
        return;
    }
    target[INSTALLED_FLAG] = true;
    target.addEventListener("click", (event) => {
        const origin = event.target;
        if (!(origin instanceof Element)) {
            return;
        }
        const action = origin.closest("[data-log-action]");
        if (action === null) {
            return;
        }
        const viewer = action.closest(VIEWER_SELECTOR);
        if (viewer === null) {
            return;
        }
        event.preventDefault();
        const kind = action.getAttribute("data-log-action");
        if (kind === "copy") {
            copy_output(viewer);
        } else if (kind === "download") {
            download_output(viewer);
        } else if (kind === "refresh") {
            refresh_once(viewer);
        }
    });
    const scan = () => {
        target.querySelectorAll(VIEWER_SELECTOR).forEach((viewer) => { initialise_viewer(viewer); });
    };
    scan();
    if (typeof MutationObserver === "function" && target === document) {
        const observer = new MutationObserver(() => { scan(); });
        observer.observe(document.body, { childList: true, subtree: true });
    }
    return;
}

export {
    install_log_viewer
};
