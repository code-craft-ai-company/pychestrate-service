/*
 * A list view's filters and page, kept in the address (ORC-27).
 *
 * The bundle lists held their filters only in memory: "?state=failed" was
 * ignored, "Back to ..." returned to the bare list, and a filtered view could
 * not be shared. A list now reads its state from the query string when it
 * loads and mirrors it back (without adding history entries) whenever it
 * refreshes, so the address always describes what is on screen.
 *
 * This file is bundled into each bundle by esbuild.
 */

/* The query-string value of ``name`` in the current address, or "". */
export function query_value(name) {
  if (typeof window === "undefined") {
    return "";
  }
  const value = new URLSearchParams(window.location.search).get(name);
  return value === null ? "" : value.trim();
}

/* ``allowed`` when the address names one of its values, else "". */
export function query_choice(name, allowed) {
  const value = query_value(name);
  return allowed.indexOf(value) >= 0 ? value : "";
}

/* The page number in the address (1 when absent or not a positive whole number). */
export function page_from_query() {
  const parsed = Number.parseInt(query_value("page"), 10);
  return Number.isFinite(parsed) && parsed >= 1 ? parsed : 1;
}

/*
 * Write ``values`` into the address: a value that is empty is removed, the
 * rest are set, everything else in the query string is left alone. The
 * history entry is replaced, not added, so Back leaves the page instead of
 * stepping through every filter change.
 */
export function mirror_to_query(values) {
  if (typeof window === "undefined" || typeof window.history === "undefined") {
    return;
  }
  const url = new URL(window.location.href);
  for (const name of Object.keys(values)) {
    const value = values[name];
    if (typeof value === "string" && value.length > 0) {
      url.searchParams.set(name, value);
    } else {
      url.searchParams.delete(name);
    }
  }
  const next = url.pathname + url.search + url.hash;
  if (next !== window.location.pathname + window.location.search + window.location.hash) {
    window.history.replaceState(window.history.state, "", next);
  }
}
