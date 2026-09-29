/*
 * Reaching a run's files from a page (ORC-12).
 *
 * A build's artifact manifest stores, for each file the pod uploaded, the file's
 * path in the run's result tree. The build page linked that path as it stood
 * ("output/app.tar.gz"), which the browser resolved against the page and which
 * opened nothing. The service serves the result tree at
 * ``/api/v1/runs/{run_id}/artifacts/{path}`` (the run page already uses it), so
 * a stored path becomes that address. An address with a scheme (``s3://...``,
 * ``oci://...``) names storage this service does not serve; a browser cannot
 * open it, so the page shows it as text instead of offering a link that fails.
 *
 * This file is bundled into each bundle by esbuild.
 */

const SCHEME_PATTERN = /^[a-z][a-z0-9+.-]*:\/\//i;

// Extensions the service renders in the browser (text and images); anything
// else it serves as a download.
const INLINE_EXTENSIONS = [".txt", ".log", ".jsos", ".json", ".yaml", ".yml", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"];

/*
 * The result-tree path an artifact entry names, or "" when it names other
 * storage. An entry whose ``storage_uri`` has a scheme (``s3://...``) says where
 * its bytes are, so it is never linked, even if its payload also records the
 * path it was uploaded from; otherwise the payload's ``relative_path`` (or the
 * stored path itself) is the file's place in the run's result tree.
 */
export function served_artifact_path(entry) {
  if (entry === null || typeof entry !== "object") {
    return "";
  }
  const uri = typeof entry.storage_uri === "string" ? entry.storage_uri : "";
  if (SCHEME_PATTERN.test(uri) === true) {
    return "";
  }
  const payload = entry.payload !== null && typeof entry.payload === "object" ? entry.payload : {};
  const stored = typeof payload.relative_path === "string" && payload.relative_path.length > 0 ? payload.relative_path : uri;
  if (stored.length === 0 || SCHEME_PATTERN.test(stored) === true || stored.startsWith("/") === true) {
    return "";
  }
  return stored;
}

/* The address the service serves ``artifact_path`` of run ``run_id`` at. */
export function run_artifact_url(run_id, artifact_path) {
  const encoded = artifact_path.split("/").map((segment) => encodeURIComponent(segment)).join("/");
  return "/api/v1/runs/" + encodeURIComponent(run_id) + "/artifacts/" + encoded;
}

/* True when the service shows this file in the browser rather than downloading it. */
export function opens_in_browser(artifact_path) {
  const lower = artifact_path.toLowerCase();
  return INLINE_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

/* "12.3 KB", "3 MB", or "" when the size is not a number. */
export function format_bytes(size) {
  if (typeof size !== "number" || Number.isFinite(size) === false || size < 0) {
    return "";
  }
  if (size < 1024) {
    return String(size) + " B";
  }
  const units = ["KB", "MB", "GB"];
  let value = size / 1024;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value = value / 1024;
    unit = unit + 1;
  }
  return String(Math.round(value * 10) / 10) + " " + units[unit];
}

/* The last ``count`` lines of ``text`` and whether anything before them was left out. */
export function tail_lines(text, count) {
  const lines = text.replace(/\r\n/g, "\n").replace(/\n$/, "").split("\n");
  if (lines.length <= count) {
    return { text: lines.join("\n"), cut: false, total: lines.length };
  }
  return { text: lines.slice(lines.length - count).join("\n"), cut: true, total: lines.length };
}
