// source/site/ccai/pychestrate/webservice/webinterface/static/javascript/pyc-site-shell/chrome/live-region.js
//
// Keeps a server-rendered region of a page current while the thing it
// shows is still active (a running job's status, duration, reason):
//
//   <div data-live-region="job" data-live-region-active="true"
//        data-live-region-refresh-seconds="10"> ... </div>
//
// While data-live-region-active is "true" the region re-fetches its own
// page every N seconds and swaps in the element with the same
// data-live-region name, then stops once the fresh copy says it is no
// longer active. The RPA job page used to show a job as running until
// the operator reloaded it (E2E-23). Same approach as the log viewer:
// no <meta http-equiv="refresh">, so the shell and scroll position stay.

const REGION_SELECTOR = "[data-live-region]";
const INSTALLED_FLAG = "__pycLiveRegionInstalled";
const DEFAULT_REFRESH_SECONDS = 10;

function is_active(region) {
    return region.getAttribute("data-live-region-active") === "true";
}

async function refresh_once(region) {
    const name = region.getAttribute("data-live-region") || "";
    let response;
    try {
        response = await fetch(window.location.href, { credentials: "same-origin", cache: "no-store", headers: { "Accept": "text/html" } });
    } catch (error) {
        return true;
    }
    if (response.ok !== true) {
        // A transient error keeps polling; a redirect to login or a
        // missing page does not recover by retrying.
        return response.status >= 500;
    }
    const html = await response.text();
    const parsed = new DOMParser().parseFromString(html, "text/html");
    let fresh = null;
    parsed.querySelectorAll(REGION_SELECTOR).forEach((candidate) => {
        if (fresh === null && candidate.getAttribute("data-live-region") === name) {
            fresh = candidate;
        }
    });
    if (fresh === null) {
        return false;
    }
    if (region.innerHTML !== fresh.innerHTML) {
        region.innerHTML = fresh.innerHTML;
    }
    const still_active = is_active(fresh);
    region.setAttribute("data-live-region-active", still_active ? "true" : "false");
    return still_active;
}

function schedule(region) {
    if (is_active(region) !== true) {
        return;
    }
    const seconds = Number.parseInt(region.getAttribute("data-live-region-refresh-seconds") || "", 10);
    const delay = Number.isFinite(seconds) && seconds > 0 ? seconds * 1000 : DEFAULT_REFRESH_SECONDS * 1000;
    window.setTimeout(() => {
        if (document.body.contains(region) === false) {
            return;
        }
        refresh_once(region).then((still_active) => {
            if (still_active === true) {
                schedule(region);
            }
        });
    }, delay);
    return;
}

function initialise_region(region) {
    if (region.dataset.pycLiveRegionInitialised === "true") {
        return;
    }
    region.dataset.pycLiveRegionInitialised = "true";
    schedule(region);
    return;
}

function install_live_region(root) {
    const target = root !== undefined && root !== null ? root : document;
    if (target[INSTALLED_FLAG] === true) {
        return;
    }
    target[INSTALLED_FLAG] = true;
    const scan = () => {
        target.querySelectorAll(REGION_SELECTOR).forEach((region) => { initialise_region(region); });
    };
    scan();
    if (typeof MutationObserver === "function" && target === document) {
        const observer = new MutationObserver(() => { scan(); });
        observer.observe(document.body, { childList: true, subtree: true });
    }
    return;
}

export {
    install_live_region
};
